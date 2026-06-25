#!/usr/bin/env python3
"""
reconcile.py
============
READ-ONLY integrity check for the paper subsystem of the neubrain vault.

    python reconcile.py --vault /path/to/neubrain

What it does:
  - reads  _library/manifest.json        (what SHOULD exist)
  - scans  _library/*.xml | *.tei.xml    (what IS on disk)
  - scans  lit/*.md                       (which papers have a node)
  - scans  projects/*/papers/             (symlinks into _library)
  - classifies any drift and WRITES THE REPORT to logs/library-status.md

What it never does (by design — you chose "report only"):
  - it does not delete, move, re-download, relink, or edit anything
  - it touches NOTHING outside the paper subsystem: collaborators/, meetings/,
    plans/, etc. are never read or written
  - the ONLY file it writes is logs/library-status.md

Exit code is 0 when clean, 1 when any drift is found (handy for scripting),
but the on-disk state is identical either way.

Requires: Python 3.10+ (stdlib only).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path


# --------------------------------------------------------------------------- #
# data model
# --------------------------------------------------------------------------- #
@dataclass
class Findings:
    n_manifest: int = 0
    n_xml_on_disk: int = 0
    n_nodes: int = 0
    n_projects: int = 0
    n_symlinks: int = 0

    missing_files: list[str] = field(default_factory=list)      # in manifest, not on disk
    orphan_xml: list[str] = field(default_factory=list)         # on disk, not in manifest
    missing_nodes: list[str] = field(default_factory=list)      # have file, no lit/ note
    orphan_nodes: list[str] = field(default_factory=list)       # lit/ note, not in manifest
    broken_links: list[str] = field(default_factory=list)       # symlink target missing
    pdf_only: list[str] = field(default_factory=list)           # stored as PDF, no XML yet

    def is_clean(self) -> bool:
        return not any([self.missing_files, self.orphan_xml, self.missing_nodes,
                        self.orphan_nodes, self.broken_links])


# --------------------------------------------------------------------------- #
# scan (pure reads)
# --------------------------------------------------------------------------- #
def load_manifest(library: Path) -> dict:
    f = library / "manifest.json"
    if not f.exists():
        # an empty/absent manifest is itself a finding, not a crash
        return {"by_id": {}, "entries": {}}
    return json.loads(f.read_text())


def scan(vault: Path) -> Findings:
    library = vault / "_library"
    lit = vault / "lit"
    projects = vault / "projects"

    f = Findings()
    manifest = load_manifest(library)
    entries = manifest.get("entries", {})
    f.n_manifest = len(entries)

    # files actually present in the archive
    xml_stems = {p.name.removesuffix(".tei.xml").removesuffix(".xml")
                 for p in library.glob("*.xml")}
    pdf_stems = {p.stem for p in library.glob("*.pdf")}
    f.n_xml_on_disk = len(xml_stems)

    # nodes present in lit/
    node_stems = {p.stem for p in lit.glob("*.md")} if lit.exists() else set()
    f.n_nodes = len(node_stems)

    # cross-checks: manifest <-> disk
    for stem, meta in entries.items():
        has_xml = stem in xml_stems
        has_pdf = stem in pdf_stems
        if not has_xml and not has_pdf:
            f.missing_files.append(stem)
        elif not has_xml and has_pdf:
            f.pdf_only.append(stem)        # expected interim state, not an error
        if stem not in node_stems:
            f.missing_nodes.append(stem)

    for stem in xml_stems:
        if stem not in entries:
            f.orphan_xml.append(stem)

    for stem in node_stems:
        if stem not in entries:
            f.orphan_nodes.append(stem)

    # symlinks in each project's papers/ folder
    if projects.exists():
        for proj in sorted(p for p in projects.iterdir() if p.is_dir()):
            papers = proj / "papers"
            if not papers.exists():
                continue
            f.n_projects += 1
            for link in papers.iterdir():
                if not link.is_symlink():
                    continue
                f.n_symlinks += 1
                # resolve relative to the symlink's own directory
                target = (papers / os.readlink(link))
                if not target.exists():
                    f.broken_links.append(f"{proj.name}/papers/{link.name}")

    return f


# --------------------------------------------------------------------------- #
# report (writes ONLY logs/library-status.md)
# --------------------------------------------------------------------------- #
def _section(title: str, items: list[str], ok_msg: str) -> str:
    if not items:
        return f"### {title}\n\n- {ok_msg}\n"
    body = "\n".join(f"- `{x}`" for x in sorted(items))
    return f"### {title}  ({len(items)})\n\n{body}\n"


def render(f: Findings) -> str:
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    status = "CLEAN ✅" if f.is_clean() else "DRIFT DETECTED ⚠️"
    lines = [
        "# Library status",
        "",
        "> Generated by `reconcile.py` — do not hand-edit. Read-only check; "
        "nothing on disk was changed.",
        "",
        f"**Last run:** {now}  ",
        f"**Status:** {status}",
        "",
        "## Counts",
        "",
        f"- Manifest entries: **{f.n_manifest}**",
        f"- XML files on disk: **{f.n_xml_on_disk}**",
        f"- Literature nodes (`lit/`): **{f.n_nodes}**",
        f"- Projects with a `papers/` folder: **{f.n_projects}**",
        f"- Project symlinks: **{f.n_symlinks}**",
        "",
        "## Integrity",
        "",
        _section("Missing files (in manifest, absent from disk)",
                 f.missing_files, "none — every manifest entry has a file"),
        _section("Orphan XML (on disk, not in manifest)",
                 f.orphan_xml, "none — no untracked archive files"),
        _section("Missing nodes (file present, no `lit/` note yet)",
                 f.missing_nodes, "none — every paper has a node"),
        _section("Orphan nodes (`lit/` note with no manifest entry)",
                 f.orphan_nodes, "none — every node maps to a tracked paper"),
        _section("Broken symlinks (project link target missing)",
                 f.broken_links, "none — all project links resolve"),
    ]
    if f.pdf_only:
        lines.append(_section("PDF-only (awaiting XML conversion — informational)",
                              f.pdf_only, ""))
    if not f.is_clean():
        lines += [
            "## Suggested next step",
            "",
            "This report changed nothing. To act on the drift above, run the "
            "relevant repair deliberately (re-fetch a missing paper, generate a "
            "missing node, or clear a stale manifest entry). Reconcile will not "
            "do it for you.",
            "",
        ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Read-only integrity check for the paper subsystem.")
    ap.add_argument("--vault", required=True, type=Path, help="path to the neubrain vault root")
    args = ap.parse_args()

    if not (args.vault / "_library").exists():
        sys.exit(f"no _library/ under {args.vault} — is this the vault root?")

    f = scan(args.vault)

    logs = args.vault / "logs"
    logs.mkdir(exist_ok=True)
    (logs / "library-status.md").write_text(render(f))

    print(f"reconcile: {'clean' if f.is_clean() else 'DRIFT'} — "
          f"wrote {logs / 'library-status.md'}")
    return 0 if f.is_clean() else 1


if __name__ == "__main__":
    raise SystemExit(main())
