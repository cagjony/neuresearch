#!/usr/bin/env python3
"""
triage_refs.py
==============
Build the reference triage table for a project: one row per DOI in papers.txt,
carrying the metadata needed to decide whether that reference stays in the
review, and where in the current draft it is actually used.

    python triage_refs.py --vault /path/to/neubrain --project alz-olf \
        --draft projects/alz-olf/archive/odor_alzheimer_v4.md \
        [--out PATH] [--email you@host] [--refresh]

WHY THIS EXISTS

A reference is kept or cut by the ROLE it plays, not by its age alone. A flat
"nothing older than five years" rule deletes the papers that introduced the mouse
lines, the psychophysical instruments and the staging schemes a review of this kind
has to cite — those are sources of record, and citing a recent review in their place
would be wrong, not modern. So the decision needs a human, and the human needs the
evidence in front of them. This script assembles that evidence; it decides nothing.

See projects/<project>/specs/2026-07-21-review-restructure-design.md for the tier
definitions and the policy this table serves.

WHAT IT DOES

    1. reads the project's papers.txt (one DOI per line);
    2. fetches per-DOI metadata from Crossref (year, first author, journal, title,
       times-cited), cached on disk so reruns are cheap;
    3. joins each DOI to the draft by first-author surname + a nearby year, and
       records which of the draft's numbered sections cite it;
    4. joins to the manifest for the citekey stem and whether a full text is held;
    5. proposes a tier from mechanical rules;
    6. writes a TSV whose last two columns are yours to fill in.

The proposal is a starting point, never a decision. `record` and `seminal` are
author judgements and are NEVER proposed — the script cannot know that a 1996 paper
is the one that introduced Tg2576.

REGENERATION IS SAFE. If the output file already exists, the `tier` and
`replacement_doi` columns are read back and carried over onto the new rows, keyed by
DOI. Re-running after adding papers to papers.txt will not cost you your decisions.

The manifest is read, never written: applying approved tiers to it is a separate
step, so that generating the table can never mutate the library.

Politeness: cached fetches, a fixed inter-call delay and a contact email in the
User-Agent, as Crossref etiquette asks. Public APIs only.

NOTE on the Crossref single-work route: /works/{doi} does NOT accept the `select`
parameter and answers HTTP 400 if given one. The error surfaces as a total fetch
failure that looks like a network problem, so we simply do not send it.

Requires: Python 3.10+, `requests`.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

import requests

CROSSREF = "https://api.crossref.org/works"
DEFAULT_EMAIL = "cagjony@gmail.com"
DELAY = 0.12  # seconds between live Crossref calls

COLUMNS = [
    "doi", "stem", "year", "first_author", "journal", "title",
    "draft_sections", "crossref_citations", "have_pdf",
    "proposed_tier", "tier", "replacement_doi", "note",
]
# Author-owned columns, preserved across regeneration. `note` records why a tier
# was chosen, so a decision can be checked without re-deriving it.
AUTHOR_COLUMNS = ("tier", "replacement_doi", "note")

DEFAULT_CURRENT_FROM = 2021  # "recent" boundary; pre-this is subject to the tiered policy


# --------------------------------------------------------------------------- #
# draft parsing
# --------------------------------------------------------------------------- #
# The draft is a Google-Docs/Word export, so its section headings are bold-numbered
# paragraphs ("**3\. Olfactory Dysfunction ...**") rather than ATX headings. Accept
# both, so this keeps working once the draft is rewritten as real markdown.
_HEADING_RE = re.compile(r"^(?:#+\s*|\*\*)(\d+)\\?\.\s", re.M)
_IMAGE_DATA_RE = re.compile(r"^\[image\d+\]:.*$", re.M)
# The bibliography must be cut off before matching. It sits INSIDE the last numbered
# section of this draft, so without this every reference matches its own entry in the
# reference list and appears to be cited by whatever section happens to contain it.
_BIBLIOGRAPHY_RE = re.compile(r"^\s*(?:#+\s*|\*\*)?References\b", re.M | re.I)

# Length-preserving normalisation, so character offsets stay valid for section
# lookup. Unicode hyphens and accented surnames otherwise fail to match the prose:
# Crossref returns "Cronin‐Golomb" and "Lehéricy" where the draft has
# "Cronin-Golomb" and, sometimes, "Lehericy".
_DASHES = "‐‑‒–—―−"


def _fold(s: str) -> str:
    """Casefold, flatten dash variants, and strip accents — one char in, one out."""
    import unicodedata
    out = []
    for ch in s:
        if ch in _DASHES:
            out.append("-")
            continue
        base = unicodedata.normalize("NFD", ch)[0]
        out.append((base if base.isascii() and base.isalpha() else ch).lower())
    return "".join(out)


def load_draft(path: Path) -> tuple[str, list[tuple[int, str]]]:
    """
    Draft prose (base64 image blobs stripped, bibliography truncated), folded for
    matching, plus (offset, section number) for each numbered heading.
    """
    text = _IMAGE_DATA_RE.sub("", path.read_text(encoding="utf-8"))
    bib = _BIBLIOGRAPHY_RE.search(text)
    if bib:
        text = text[:bib.start()]
    heads = [(m.start(), m.group(1)) for m in _HEADING_RE.finditer(text)]
    return _fold(text), heads


def section_at(heads: list[tuple[int, str]], pos: int) -> str | None:
    """The numbered section containing character offset `pos`, if any."""
    found = None
    for start, num in heads:
        if start <= pos:
            found = num
        else:
            break
    return found


def sections_citing(text: str, heads: list[tuple[int, str]],
                    surname: str, year: int | None) -> list[str]:
    """
    Draft sections that cite `surname` (year). Matches the surname followed, within
    a short window, by a 4-digit year — the shape of the draft's author-year
    citations, e.g. "(Rey et al., 2012a)". The year in the prose is allowed to differ
    from the Crossref year by one, since the reference list is inconsistent about
    online-first vs issue dates.
    """
    # Word boundaries rather than a minimum length: two-letter surnames are common
    # (Wu, Li, Lu, Yu, Hu, Su) and a length guard silently drops them, which shows up
    # as "cited nowhere" and would propose cutting a live reference.
    if len(surname) < 2:
        return []
    hits: set[str] = set()
    surname = _fold(surname)
    pattern = r"\b" + re.escape(surname) + r"\b[^)\]]{0,45}?\b((?:19|20)\d\d)"
    for m in re.finditer(pattern, text):
        if year and abs(int(m.group(1)) - year) > 1:
            continue
        sec = section_at(heads, m.start())
        if sec:
            hits.add(sec)
    return sorted(hits, key=int)


# --------------------------------------------------------------------------- #
# metadata
# --------------------------------------------------------------------------- #
def fetch_meta(doi: str, session: requests.Session) -> dict:
    """Crossref metadata for one DOI, reduced to the fields the table needs."""
    r = session.get(f"{CROSSREF}/{doi}", timeout=30)
    if r.status_code != 200:
        return {}
    msg = r.json().get("message")
    if not isinstance(msg, dict):
        return {}
    authors = msg.get("author") or []
    first = authors[0] if authors and isinstance(authors[0], dict) else {}
    parts = (msg.get("issued") or {}).get("date-parts") or [[]]
    year = parts[0][0] if parts and parts[0] else None
    return {
        "year": year,
        "first_author": first.get("family", "") or "",
        "journal": (msg.get("container-title") or [""])[0],
        "title": (msg.get("title") or [""])[0],
        "type": msg.get("type", ""),
        "crossref_citations": msg.get("is-referenced-by-count", 0),
    }


def load_cache(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


# --------------------------------------------------------------------------- #
# tiers
# --------------------------------------------------------------------------- #
def propose_tier(year: int | None, sections: list[str], cut_sections: set[str],
                 has_meta: bool = True, current_from: int = DEFAULT_CURRENT_FROM) -> str:
    """
    Mechanical proposal only. `record` and `seminal` are author judgements and are
    never proposed here — the point of the table is that a person makes those calls.
    """
    if not has_meta:
        # No Crossref record, so there was nothing to match on and "cited nowhere"
        # would be an artefact. Flag it instead of proposing a fate for it.
        return "unknown"
    if not sections:
        return "cut"          # cited nowhere in the prose: Zotero cruft
    if set(sections) <= cut_sections:
        return "cut"          # lives only in sections being removed
    if year and year >= current_from:
        return "current"
    return "replace"          # pre-2021 and still load-bearing: needs a substitute


# --------------------------------------------------------------------------- #
# existing decisions
# --------------------------------------------------------------------------- #
def read_decisions(path: Path) -> dict[str, dict[str, str]]:
    """Author-owned columns from a previous run, keyed by DOI, so reruns are safe."""
    if not path.exists():
        return {}
    out: dict[str, dict[str, str]] = {}
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            doi = (row.get("doi") or "").strip().lower()
            kept = {c: (row.get(c) or "").strip() for c in AUTHOR_COLUMNS}
            if doi and any(kept.values()):
                out[doi] = kept
    return out


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(
        description="Build the reference triage table for a project.")
    ap.add_argument("--vault", required=True, type=Path, help="neubrain vault root")
    ap.add_argument("--project", required=True, help="project name under projects/")
    ap.add_argument("--draft", required=True, type=Path,
                    help="the draft to join against (relative to --vault or absolute)")
    ap.add_argument("--out", default=None, type=Path,
                    help="output TSV (default: projects/<project>/refs-triage.tsv)")
    ap.add_argument("--papers", default=None, type=Path,
                    help="DOI list (default: projects/<project>/papers.txt)")
    ap.add_argument("--cut-sections", default="",
                    help="comma-separated draft section numbers being removed, so "
                         "references living only there are proposed 'cut' (e.g. 2,6)")
    ap.add_argument("--email", default=DEFAULT_EMAIL,
                    help="contact email placed in the polite Crossref User-Agent")
    ap.add_argument("--current-from", type=int, default=DEFAULT_CURRENT_FROM,
                    help="first year counted as 'recent'; earlier work is subject to "
                         f"the tiered policy (default {DEFAULT_CURRENT_FROM})")
    ap.add_argument("--refresh", action="store_true",
                    help="ignore the Crossref cache and refetch every DOI")
    args = ap.parse_args()

    proj_dir = args.vault / "projects" / args.project
    if not proj_dir.is_dir():
        sys.exit(f"no such project: {proj_dir}")

    papers = args.papers or proj_dir / "papers.txt"
    out = args.out or proj_dir / "refs-triage.tsv"
    draft = args.draft if args.draft.is_absolute() else args.vault / args.draft
    cache_path = proj_dir / ".triage-cache.json"

    for p, what in ((papers, "DOI list"), (draft, "draft")):
        if not p.exists():
            sys.exit(f"no {what} at {p}")

    cut_sections = {s.strip() for s in args.cut_sections.split(",") if s.strip()}
    dois = [ln.strip() for ln in papers.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")]
    seen: set[str] = set()
    dois = [d for d in dois if not (d.lower() in seen or seen.add(d.lower()))]

    text, heads = load_draft(draft)
    if not heads:
        print(f"warning: no numbered sections found in {draft.name}; "
              f"draft_sections will be empty for every row", file=sys.stderr)

    manifest = json.loads((args.vault / "_library" / "manifest.json")
                          .read_text(encoding="utf-8"))
    by_id = {k.lower(): v for k, v in manifest.get("by_id", {}).items()}
    entries = manifest.get("entries", {})

    decisions = read_decisions(out)
    cache = {} if args.refresh else load_cache(cache_path)

    session = requests.Session()
    session.headers["User-Agent"] = f"neuresearch/1.0 (mailto:{args.email})"

    rows = []
    n_fetched = n_cached = n_failed = 0
    for i, doi in enumerate(dois, 1):
        key = doi.lower()
        meta = cache.get(key)
        if meta is None:
            meta = fetch_meta(doi, session)
            cache[key] = meta
            time.sleep(DELAY)
            n_fetched += 1
            if i % 25 == 0 or i == len(dois):
                print(f"  ... {i}/{len(dois)}", flush=True)
        else:
            n_cached += 1
        if not meta:
            n_failed += 1

        year = meta.get("year")
        stem = by_id.get(key, "")
        entry = entries.get(stem, {}) if stem else {}
        sections = sections_citing(text, heads, meta.get("first_author", ""), year)

        row = {
            "doi": doi,
            "stem": stem,
            "year": year or "",
            "first_author": meta.get("first_author", ""),
            "journal": " ".join((meta.get("journal") or "").split()),
            "title": " ".join((meta.get("title") or "").split()),
            "draft_sections": ",".join(sections),
            "crossref_citations": meta.get("crossref_citations", ""),
            "have_pdf": "yes" if entry.get("files") else "no",
            "proposed_tier": propose_tier(year, sections, cut_sections, bool(meta),
                                          args.current_from),
            "tier": "",
            "replacement_doi": "",
            "note": "",
        }
        row.update(decisions.get(key, {}))
        rows.append(row)

    cache_path.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")

    # Sort so the rows needing attention come first: undecided before decided, then
    # oldest first, since the oldest are where the policy actually bites.
    rows.sort(key=lambda r: (bool(r["tier"]), int(r["year"] or 0), r["first_author"]))

    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, delimiter="\t",
                           quoting=csv.QUOTE_MINIMAL, extrasaction="ignore",
                           lineterminator="\n")  # csv defaults to CRLF; keep it clean for git
        w.writeheader()
        w.writerows(rows)

    # ----------------------------------------------------------------- report
    from collections import Counter
    proposed = Counter(r["proposed_tier"] for r in rows)
    decided = sum(1 for r in rows if r["tier"])
    pre = sum(1 for r in rows if r["year"] and int(r["year"]) < args.current_from)

    print(f"\nwrote {out}  ({len(rows)} rows)")
    print(f"  crossref: {n_fetched} fetched, {n_cached} cached"
          + (f", {n_failed} with no metadata" if n_failed else ""))
    print(f"  pre-{args.current_from}: {pre} | {args.current_from}+: {len(rows) - pre}")
    print("  proposed: " + ", ".join(f"{k}={v}" for k, v in sorted(proposed.items())))
    if decided:
        print(f"  carried over {decided} decision(s) from the previous table")

    todo = [r for r in rows if not r["tier"]]
    print(f"\n{len(todo)} row(s) still need a tier. Fill in the 'tier' column "
          f"(record | seminal | current | replace | cut);\n"
          f"'replace' also needs a replacement_doi. Rerunning this script preserves "
          f"whatever you have set.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
