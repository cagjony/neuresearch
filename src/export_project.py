#!/usr/bin/env python3
"""
export_project.py
=================
Materialise a project's papers OUT of the shared _library on demand.

    python export_project.py --vault /path/to/neubrain --project astro_atp \
        --out ./astro_atp_papers

Papers live ONCE in <vault>/_library/. A project "has" a paper by being listed
in that paper's manifest "projects" field — NOT by holding a copy. When you
actually need the files together (to zip for a collaborator, feed a tool, etc.)
this script copies them into --out.

It is READ-ONLY with respect to the library and the manifest: it only reads
_library/manifest.json + the archived files, and writes copies into --out. It
never edits, moves, or deletes anything under _library/.

Requires: Python 3.10+ (stdlib only).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


def load_manifest(library: Path) -> dict:
    f = library / "manifest.json"
    if not f.exists():
        sys.exit(f"no manifest at {f} — nothing to export")
    return json.loads(f.read_text())


def members(manifest: dict, project: str) -> list[tuple[str, list[str]]]:
    """(stem, files) for every entry whose 'projects' list contains `project`."""
    out = []
    for stem, entry in manifest.get("entries", {}).items():
        if project in entry.get("projects", []):
            out.append((stem, entry.get("files", [])))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Copy a project's library files into a folder on demand.")
    ap.add_argument("--vault", required=True, type=Path, help="neubrain vault root")
    ap.add_argument("--project", required=True, help="project name to export")
    ap.add_argument("--out", required=True, type=Path, help="destination folder for the copies")
    args = ap.parse_args()

    library = args.vault / "_library"
    if not library.exists():
        sys.exit(f"no _library/ under {args.vault} — is this the vault root?")

    manifest = load_manifest(library)
    entries = members(manifest, args.project)
    if not entries:
        print(f"no papers tagged with project '{args.project}' in the manifest.")
        return 0

    args.out.mkdir(parents=True, exist_ok=True)
    n_copied = n_missing = 0
    for stem, files in sorted(entries):
        if not files:
            print(f"[WARN]  {stem}: no files listed in manifest"); continue
        for fn in files:
            src = library / fn
            if not src.exists():
                print(f"[MISS]  {stem}: {fn} not in _library (run reconcile)"); n_missing += 1
                continue
            shutil.copy2(src, args.out / fn)  # read-only on the library
            n_copied += 1
            print(f"[COPY]  {fn}")

    print(f"\nExported {len(entries)} papers ({n_copied} files) for '{args.project}' "
          f"-> {args.out}" + (f"  [{n_missing} missing]" if n_missing else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
