#!/usr/bin/env python3
"""
new_project.py  —  the "start a project" protocol
==================================================
Scaffolds the front door for a new paper inside the neubrain vault. It only
creates the project's input files and prints the next steps — it does NOT fetch
anything or touch the manifest. The manifest grows per-paper later, when
fetch_papers / ingest run.

    python new_project.py --vault /path/to/neubrain --name my_project

Creates (refusing to clobber an existing project):
    projects/<name>/plan.md         planyourscience-shaped template
    projects/<name>/papers.txt      empty, with the identifier-format header
    projects/<name>/manuscript.md   stub with the central-contribution line

Then prints the ordered next steps (paste plan → fetch → build nodes → discover).

Requires: Python 3.10+ (stdlib only).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PLAN_TEMPLATE = """<!-- Replace this with your planyourscience export, or fill in directly.
     This is a planyourscience-shaped template: keep the headers, replace the
     placeholder text under each. The Question and Central contribution drive
     everything downstream (see the scientific-writing skill). -->

# {name} — working title

## Question
_The specific question(s) this paper answers. These are the pillars: pose them
here, answer them in Results, discuss them in Discussion._

## Central contribution
_One sentence: "This paper shows that ___." Everything else serves this._

## Hypotheses
_The competing/leading hypotheses this work tests._

## Introduction
_Funnel: field gap → subfield gap → the specific untested gap you fill → a final
line on what the paper does._

## Methods
_How the work was/will be done._

## Results
_The ordered sequence of claims (each a declarative header) that support the
central contribution._

## Discussion
_How the gap was filled, the limitations, and how this advances the field._

## References
_Paste the plan's references here; put their identifiers (DOI/PMID/PMCID/title)
into papers.txt so fetch_papers.py can acquire them._
"""

PAPERS_TEMPLATE = """# {name} — supporting literature
# One identifier per line. DOI preferred; PMID, PMCID, or a bare TITLE also work
# (a title falls back to a Europe PMC search). Lines starting with # are ignored.
# Example:
#   10.1371/journal.pcbi.1005619
#   29706581
#   PMC5640625
#   Astrocyte calcium waves propagate proximally by gap junction
"""

MANUSCRIPT_TEMPLATE = """# {name} — manuscript

**Central contribution (one sentence):** _This paper shows that ___._

<!-- Draft and review this with the `scientific-writing` skill (drafting + review
     modes), grounded in [@carandini2022] and [@mensh2017]. Cite library papers
     by their vault citekey, e.g. [@stem]; a [@citekey] with no .bib entry is an
     error to flag, not to invent. -->
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
    (proj / "plan.md").write_text(PLAN_TEMPLATE.format(name=args.name))
    (proj / "papers.txt").write_text(PAPERS_TEMPLATE.format(name=args.name))
    (proj / "manuscript.md").write_text(MANUSCRIPT_TEMPLATE.format(name=args.name))

    print(f"Scaffolded project '{args.name}' at {proj}")
    print("  - plan.md         (planyourscience-shaped template)")
    print("  - papers.txt      (identifier list — empty)")
    print("  - manuscript.md   (stub)")
    print()
    print("NEXT STEPS (in order):")
    print(f"  1) Paste your planyourscience export into {proj/'plan.md'},")
    print(f"     and put its references' identifiers into {proj/'papers.txt'}.")
    print(f"  2) Fetch the literature:")
    print(f"       python src/fetch_papers.py {proj/'papers.txt'} \\")
    print(f"           --vault {args.vault} --project {args.name} --email you@host")
    print(f"  3) Build the linked library:")
    print(f"       python src/refs.py --vault {args.vault} --project {args.name} --only-empty")
    print(f"       python src/make_nodes.py propose --vault {args.vault} --project {args.name}")
    print(f"       #   (curate concepts/_proposed.md, then:)")
    print(f"       python src/make_nodes.py wire    --vault {args.vault} --project {args.name}")
    print(f"       python src/relate.py  --vault {args.vault} --project {args.name}")
    print(f"  4) Discover more papers, then review/approve them:")
    print(f"       python src/suggest.py --vault {args.vault} --project {args.name} \\")
    print(f"           --email you@host --from both")
    print(f"       #   review {proj/'suggestions.md'}, tick ✓ to keep")
    print()
    print("Then draft & review manuscript.md with the scientific-writing skill.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
