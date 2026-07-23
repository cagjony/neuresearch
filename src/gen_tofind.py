#!/usr/bin/env python3
"""
gen_tofind.py
=============
Regenerate a project's acquisition worklist (to-find.md) from its tiered triage
table, listing ONLY references that are kept AND still have no full text.

    python gen_tofind.py --vault /path/to/neubrain --project alz-olf [--out PATH]

WHY THIS EXISTS

The worklist and the triage table drift apart the moment a tier changes. A paper
cut by triage is not worth an interlibrary-loan request, and a paper acquired since
the last write is noise on the list. Both failures cost real effort — the first one
already did, when a PDF was hunted for a section that was about to be deleted. So
the worklist is derived, never hand-maintained: re-run this after any change to the
`tier` column.

Rows are grouped by tier, because the tiers carry different obligations. A source of
record must be cited and nothing can substitute for it; a `replace` row already has a
verified recent substitute recorded in `replacement_doi`, so fetching the original is
optional and only matters if the substitute turns out not to carry the claim.

Reads refs-triage.tsv only. Writes to-find.md only. Touches neither the manifest nor
papers.txt.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import sys
from collections import Counter
from pathlib import Path

# Ordered by how binding the obligation is, which is also the order to work in.
TIER_ORDER = {"record": 0, "seminal": 1, "replace": 2, "current": 3}

SECTIONS = [
    ("record", "Sources of record — age-exempt, must be cited",
     "The instruments, mouse lines and staging schemes the review argues about. "
     "A recent review cannot stand in for any of these."),
    ("seminal", "Seminal",
     "Field-defining work the argument leans on."),
    ("replace", "Replace — only if the substitute proves unusable",
     "Each already has a verified recent substitute in `replacement_doi`, so these "
     "are optional: fetch one only if you decide the substitute does not carry the claim."),
    ("current", "Current",
     "Recent work cited in a surviving section."),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[3],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vault", required=True, type=Path, help="neubrain vault root")
    ap.add_argument("--project", required=True, help="project name under projects/")
    ap.add_argument("--table", default=None, type=Path,
                    help="triage TSV (default: projects/<project>/refs-triage.tsv)")
    ap.add_argument("--out", default=None, type=Path,
                    help="output (default: projects/<project>/to-find.md)")
    args = ap.parse_args()

    proj = args.vault / "projects" / args.project
    if not proj.is_dir():
        sys.exit(f"no such project: {proj}")
    table = args.table or proj / "refs-triage.tsv"
    out = args.out or proj / "to-find.md"
    if not table.exists():
        sys.exit(f"no triage table at {table} — run triage_refs.py first")

    rows = list(csv.DictReader(table.open(newline="", encoding="utf-8"), delimiter="\t"))
    if not rows:
        sys.exit(f"{table} has no rows")
    undecided = sum(1 for r in rows if not r.get("tier"))
    if undecided:
        print(f"warning: {undecided} row(s) still have no tier and are omitted; "
              f"the worklist will be incomplete until they are decided", file=sys.stderr)

    need = [r for r in rows if r.get("tier") and r["tier"] != "cut" and r["have_pdf"] != "yes"]
    need.sort(key=lambda r: (TIER_ORDER.get(r["tier"], 9), r["year"] or "0", r["first_author"]))
    kept = sum(1 for r in rows if r.get("tier") and r["tier"] != "cut")
    have = sum(1 for r in rows if r.get("tier") and r["tier"] != "cut" and r["have_pdf"] == "yes")
    cut = sum(1 for r in rows if r.get("tier") == "cut")

    L = [
        f"# Acquisition worklist — {args.project}\n",
        f"> **STATUS ({datetime.date.today()}): {len(need)} papers still needed.**",
        f"> Derived from `refs-triage.tsv`, in which {len(rows) - undecided} of {len(rows)}",
        f"> references are tiered. The reference base is **{kept} kept** ({have} already in",
        f"> the library) and {cut} cut. **Papers cut by triage are not listed here** —",
        "> hunting them is the wasted effort this worklist exists to prevent.\n",
        "This file is GENERATED. Edit tiers in `refs-triage.tsv`, then re-run:\n",
        "```bash",
        f"python src/gen_tofind.py --vault …/neubrain --project {args.project}",
        "```\n",
        "**How to ingest each one you download:**\n",
        "```bash",
        "python src/ingest.py --vault …/neubrain --project "
        f"{args.project} \\\n    --file <downloaded>.pdf --doi <the DOI from the table>",
        "```",
        "Or drop them all in one folder and run `--dir <folder>` once.\n",
    ]

    for tier, title, blurb in SECTIONS:
        group = [r for r in need if r["tier"] == tier]
        if not group:
            continue
        L += [f"\n## {title} ({len(group)})\n", blurb + "\n",
              "| # | Author, year | Title | Journal | DOI |",
              "| - | ------------ | ----- | ------- | --- |"]
        for i, r in enumerate(group, 1):
            t = r["title"][:68] + ("…" if len(r["title"]) > 68 else "")
            # pipes would break the table; journal names from Crossref carry entities
            t = t.replace("|", "\\|")
            j = r["journal"][:32].replace("|", "\\|").replace("&amp;", "&")
            L.append(f"| {i} | {r['first_author']} {r['year']} | {t} | {j} | `{r['doi']}` |")
            if tier == "replace" and r.get("replacement_doi"):
                L.append(f"|   | ↳ substitute | *already chosen — fetch only if this "
                         f"does not carry the claim* | | `{r['replacement_doi']}` |")

    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {out} — {len(need)} still needed of {kept} kept")
    if need:
        print("  by tier: " + ", ".join(
            f"{k}={v}" for k, v in sorted(Counter(r["tier"] for r in need).items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
