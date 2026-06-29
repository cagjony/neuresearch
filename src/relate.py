#!/usr/bin/env python3
"""
relate.py  —  the ## Related layer (bibliographic coupling)
===========================================================
Pure-local, no network. Reads the cited_dois already in every lit/ node and
draws "related paper" edges from two simple, grounded signals:

  - bibliographic coupling: how many cited DOIs two papers SHARE, and
  - direct citation: one paper's own DOI appearing in another's cited_dois.

    python relate.py --vault /path/to/neubrain [--project astro_atp] [--min-shared 2]

It (re)writes ONLY the machine-owned ## Related section of each node, fully
overwriting it each run. The claim summary and the ## Concepts section are never
touched (see <vault>/AGENTS.md). A node is only ever linked to another node that
actually exists — links are never fabricated.

    ## Related
    [[manninen2018]] (12 shared refs)
    [[musotto2025]] (7 shared refs) · cites this

Only pairs sharing >= --min-shared references are listed (default 2), sorted by
shared count. Idempotent: the section is regenerated from scratch every run.

Requires: Python 3.10+ (stdlib only).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_nodes import split_frontmatter  # noqa: E402

RELATED_MARKER = "## Related"
EMPTY_NOTE = "<!-- machine-owned by relate.py: no coupled papers at the current threshold -->"


# --------------------------------------------------------------------------- #
# minimal node frontmatter parse (fixed format written by make_nodes/refs)
# --------------------------------------------------------------------------- #
def _unquote(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] == '"':
        return v[1:-1].replace('\\"', '"')
    return v


def parse_node(path: Path) -> dict | None:
    """Pull citekey/doi/projects/cited_dois from a lit/ node. None if no frontmatter."""
    fm, _ = split_frontmatter(path.read_text())
    if not fm:
        return None
    citekey = path.stem
    doi = ""
    projects: list[str] = []
    cited: list[str] = []
    current = None  # which list block we are inside
    for line in fm.splitlines():
        item = re.match(r"^\s+-\s+(.*)$", line)
        if item and current is not None:
            current.append(_unquote(item.group(1)))
            continue
        current = None
        m = re.match(r"^([A-Za-z_]+):\s*(.*)$", line)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        if key == "citekey":
            citekey = _unquote(val) or citekey
        elif key == "doi":
            doi = _unquote(val)
        elif key == "projects":
            projects = [] if val in ("", "[]") else projects
            current = projects if val == "" else None
        elif key == "cited_dois":
            cited = [] if val in ("", "[]") else cited
            current = cited if val == "" else None
    return {"stem": citekey, "doi": doi.lower(), "projects": projects,
            "cited_set": {d.lower() for d in cited if d}}


# --------------------------------------------------------------------------- #
# section rewrite (machine-owned, overwrite fully)
# --------------------------------------------------------------------------- #
def render_related(edges: list[tuple[str, int, str]]) -> str:
    """edges: (other_stem, shared_count, direct_note) already sorted."""
    if not edges:
        body = EMPTY_NOTE
    else:
        lines = []
        for other, shared, note in edges:
            tail = f" · {note}" if note else ""
            lines.append(f"[[{other}]] ({shared} shared refs){tail}")
        body = "\n".join(lines)
    return f"{RELATED_MARKER}\n{body}\n"


def set_related(text: str, section: str) -> str:
    """Replace from '## Related' to EOF; leave everything above it untouched."""
    idx = text.find("\n" + RELATED_MARKER)
    if idx == -1:
        sep = "" if text.endswith("\n") else "\n"
        return text + sep + "\n" + section
    return text[:idx + 1] + section


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="Draw the ## Related layer from cited_dois.")
    ap.add_argument("--vault", required=True, type=Path, help="neubrain vault root")
    ap.add_argument("--project", default=None, help="restrict to nodes tagged with this project")
    ap.add_argument("--min-shared", type=int, default=2,
                    help="minimum shared cited DOIs to draw an edge (default 2)")
    args = ap.parse_args()

    lit = args.vault / "lit"
    if not lit.is_dir():
        sys.exit(f"no lit/ under {args.vault} — is this the vault root?")

    nodes = {}
    for path in sorted(lit.glob("*.md")):
        data = parse_node(path)
        if data is None:
            continue
        if args.project and args.project not in data["projects"]:
            continue
        data["path"] = path
        nodes[data["stem"]] = data

    if len(nodes) < 2:
        print(f"need >=2 nodes to relate (found {len(nodes)}); nothing to do.")
        return 0

    # per-node accumulator of (other, shared, direct_note)
    related: dict[str, list[tuple[str, int, str]]] = {s: [] for s in nodes}
    stems = sorted(nodes)
    edges_drawn = 0

    for i, a in enumerate(stems):
        for b in stems[i + 1:]:
            na, nb = nodes[a], nodes[b]
            shared = len(na["cited_set"] & nb["cited_set"])
            if shared < args.min_shared:
                continue
            edges_drawn += 1
            # direct citation, from each node's own perspective
            a_cites_b = bool(nb["doi"]) and nb["doi"] in na["cited_set"]
            b_cites_a = bool(na["doi"]) and na["doi"] in nb["cited_set"]
            related[a].append((b, shared, "cites this" if b_cites_a else
                               ("cited here" if a_cites_b else "")))
            related[b].append((a, shared, "cites this" if a_cites_b else
                               ("cited here" if b_cites_a else "")))

    nodes_written = 0
    for stem in stems:
        edges = sorted(related[stem], key=lambda e: (-e[1], e[0]))
        section = render_related(edges)
        path = nodes[stem]["path"]
        text = path.read_text()
        new = set_related(text, section)
        if new != text:
            path.write_text(new)
            nodes_written += 1

    scope = f" in project '{args.project}'" if args.project else ""
    print(f"relate: {edges_drawn} edges drawn across {len(nodes)} nodes{scope} "
          f"(min-shared={args.min_shared}); {nodes_written} ## Related sections updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
