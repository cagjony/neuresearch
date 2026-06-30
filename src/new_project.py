#!/usr/bin/env python3
"""
new_project.py  —  the "start a project" protocol
==================================================
Scaffolds the front door for a new paper inside the neubrain vault. It does NOT
generate content — planyourscience provides that. It only SLOTS the files you
paste into, plus the folders the tools expect, and prints the next steps. It
fetches nothing and never touches the manifest (the manifest grows per-paper
later, when fetch_papers / ingest run).

    python new_project.py --vault /path/to/neubrain --name my_project

Creates (refusing to clobber an existing project):
    projects/<name>/plan.md         placeholder header — paste the PLAN export
    projects/<name>/manuscript.md   placeholder header — paste the MANUSCRIPT skeleton
    projects/<name>/references.bib  empty; DERIVED by build_bib.py (don't hand-edit)
    projects/<name>/papers.txt      optional, disposable intake list
    projects/<name>/archive/        dump zone for new PDFs/DOIs/ideas (+ README)

Then prints the ordered next steps (paste plan/manuscript → fetch → build nodes
→ build bib → reconcile citations → write).

Requires: Python 3.10+ (stdlib only).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Each file is a SLOT, not a template: a short header telling you what to paste,
# never invented scientific content. planyourscience supplies the plan and the
# manuscript skeleton; the tools own the derived files.

PLAN_PLACEHOLDER = """<!-- Paste your planyourscience PLAN export here (or write the plan directly).
     The Question and the Central contribution drive everything downstream — see
     the scientific-writing skill. Keep this file committed in git: build_bib.py
     and reconcile_citations.py treat a clean, committed plan.md as the backup
     (the undo is `git checkout -- plan.md`; no .bak is kept). -->

# {name} — plan
"""

MANUSCRIPT_PLACEHOLDER = """<!-- Paste your planyourscience MANUSCRIPT skeleton here, then draft and review
     it with the `scientific-writing` skill (drafting + review modes), grounded
     in [@carandini2022] and [@mensh2017]. Cite library papers by their vault
     citekey, e.g. [@stem] (Markdown) or \\cite{{stem}} (LaTeX); a [@citekey] with
     no .bib entry is an error to flag, not to invent. -->

# {name} — manuscript
"""

# references.bib is DERIVED. The comment char in BibTeX is '%'.
REFERENCES_PLACEHOLDER = """% references.bib — DERIVED FILE, do not hand-edit.
% Generated and refreshed by build_bib.py from the manifest (the source of truth):
%   python src/build_bib.py --vault <vault> --project {name} --email you@host
% Any manual edits here are overwritten on the next regenerate.
"""

PAPERS_PLACEHOLDER = """# {name} — intake list  (OPTIONAL, DISPOSABLE)
# A scratch queue of identifiers to fetch — one per line. DOI is preferred, but a
# PMID, PMCID, or a bare TITLE also works (a title falls back to a Europe PMC
# search). Lines starting with # are ignored.
#
# This file is just an intake queue: once papers are fetched, the MANIFEST is the
# source of truth, and you can clear or delete this file. New finds can also be
# dropped into archive/ for later processing instead of listed here.
# Example:
#   10.1371/journal.pcbi.1005619
#   29706581
#   PMC5640625
#   Astrocyte calcium waves propagate proximally by gap junction
"""

ARCHIVE_README = """# archive/ — capture & dump zone

Drop anything here that you want folded into the paper *later*: new PDFs, loose
DOIs, links, half-formed ideas, notes, screenshots. This is an inbox, not a
permanent store — nothing here is part of the library until you process it.

**To process it**, ask Claude Code:

> "Read projects/{name}/archive/, extract any DOIs to fetch, and surface ideas
>  relevant to the manuscript."

It will pull identifiers out (add them to ../papers.txt and run fetch_papers.py)
and summarize any notes/ideas against the current manuscript. There is no
dedicated tool — this is just a known folder plus a Claude Code habit.
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Scaffold a new paper project in the vault.")
    ap.add_argument("--vault", required=True, type=Path, help="neubrain vault root")
    ap.add_argument("--name", required=True, help="project name (folder under projects/)")
    args = ap.parse_args()

    if not args.vault.exists():
        sys.exit(f"vault not found: {args.vault}")
    if "/" in args.name or args.name.startswith("."):
        sys.exit(f"invalid project name: {args.name!r}")

    proj = args.vault / "projects" / args.name
    if proj.exists():
        print(f"WARN: project already exists: {proj}")
        print("      Refusing to clobber it. Pick another --name, or edit the "
              "existing files directly.")
        return 1

    proj.mkdir(parents=True)
    (proj / "plan.md").write_text(PLAN_PLACEHOLDER.format(name=args.name))
    (proj / "manuscript.md").write_text(MANUSCRIPT_PLACEHOLDER.format(name=args.name))
    (proj / "references.bib").write_text(REFERENCES_PLACEHOLDER.format(name=args.name))
    (proj / "papers.txt").write_text(PAPERS_PLACEHOLDER.format(name=args.name))

    archive = proj / "archive"
    archive.mkdir()
    (archive / ".gitkeep").write_text("")
    (archive / "README.md").write_text(ARCHIVE_README.format(name=args.name))

    print(f"Scaffolded project '{args.name}' at {proj}")
    print("  - plan.md         (paste the planyourscience PLAN export)")
    print("  - manuscript.md   (paste the planyourscience MANUSCRIPT skeleton)")
    print("  - references.bib  (empty — DERIVED by build_bib.py; don't hand-edit)")
    print("  - papers.txt      (optional, disposable intake list)")
    print("  - archive/        (dump zone for new PDFs/DOIs/ideas — see its README)")
    print()
    print("NEXT STEPS (in order):")
    print(f"  1) Paste your planyourscience PLAN into {proj/'plan.md'} and the")
    print(f"     MANUSCRIPT skeleton into {proj/'manuscript.md'}. Put the plan's")
    print(f"     reference identifiers into {proj/'papers.txt'} (or fetch directly).")
    print(f"  2) Fetch the literature (open access only):")
    print(f"       python src/fetch_papers.py {proj/'papers.txt'} \\")
    print(f"           --vault {args.vault} --project {args.name} --email you@host")
    print(f"  3) Build the linked library:")
    print(f"       python src/refs.py       --vault {args.vault} --project {args.name} --only-empty")
    print(f"       python src/make_nodes.py propose --vault {args.vault} --project {args.name}")
    print(f"       #   (curate concepts/_proposed.md, then:)")
    print(f"       python src/make_nodes.py wire    --vault {args.vault} --project {args.name}")
    print(f"       python src/relate.py     --vault {args.vault} --project {args.name}")
    print(f"  4) Build the bibliography, then wire the plan's citations:")
    print(f"       python src/build_bib.py  --vault {args.vault} --project {args.name} --email you@host")
    print(f"       python src/reconcile_citations.py --vault {args.vault} --project {args.name}")
    print(f"       #   review the report; commit plan.md; then re-run with --apply")
    print(f"  5) Drop new finds into {archive}/ anytime; ask Claude Code to process them.")
    print()
    print("Then draft & review manuscript.md with the scientific-writing skill.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
