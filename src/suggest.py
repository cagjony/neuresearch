#!/usr/bin/env python3
"""
suggest.py  —  propose NEW papers (not yet in the library) for a project
========================================================================
Read-only on the library, NO auto-fetch. It writes a sortable, tick-to-approve
review file; you decide what to actually fetch (with fetch_papers / ingest).
Public APIs only — OpenAlex is primary (free, no key); Semantic Scholar is an
optional supplement (--semantic-scholar). Polite: inter-call delay + contact
email in the User-Agent and OpenAlex `mailto`.

    conda run -n neuresearch python3 src/suggest.py \
        --vault /path/to/neubrain --project astro_atp \
        --email you@host --from both --limit 40 [--semantic-scholar]

INPUTS
  - existing seeds: manifest entries tagged with --project (their DOIs).
  - plan: projects/<project>/plan.md (if absent, mode A only — and it says so).

MODE A (existing papers, citation graph). For each seed DOI, ask OpenAlex for
  its references (works it cites) and its citers (works that cite it). Every
  neighbour is a candidate, ranked by how many of my seed papers it is connected
  to (frequency = relevance).

MODE B (plan, keywords). Extract ~5-10 query strings from plan.md (its title +
  the most frequent topical bigrams) — these are LISTED in the output for
  transparency — and pull OpenAlex search hits. Fuzzier; expect noise.

MERGE. Union A+B, deduped by DOI. DROP any candidate already in the manifest
  (by_id) and the seeds themselves. A DOI that won't resolve is skipped + counted.

OUTPUT: projects/<project>/suggestions.md — a Markdown TABLE with a leading
  approval checkbox, citation-graph hits ranked above keyword-only hits:
      | ✓ | year | first author | title | venue | cites | DOI | why | seed |
  Re-running PRESERVES your ticks: the old file is read first, checked DOIs are
  carried over, then rows are regenerated. Approvals are never wiped — an
  approved paper that drops out of the candidate set (and isn't yet in the
  library) is carried over verbatim.

This is relevance-ranked retrieval, not judgement: reviews and tangents will
appear; you filter them. Creates nothing but suggestions.md.

Requires: Python 3.10+, `requests`.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import requests  # pip install requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_papers import load_manifest  # noqa: E402

OPENALEX = "https://api.openalex.org/works"
S2_SEARCH = "https://api.semanticscholar.org/graph/v1/paper/search"
POLITE_DELAY = 0.34
MAX_INCOMING = 50     # top citers per seed (by citation count) — the rest are long-tail
MAX_OUTGOING = 200    # references per seed (one page is plenty in practice)
PER_QUERY = 25        # search hits kept per plan query


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def norm_doi(doi: str) -> str:
    if not doi:
        return ""
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi.strip(), flags=re.IGNORECASE)
    return doi.lower()


def surname(display_name: str) -> str:
    return display_name.split()[-1] if display_name else ""


def cell(s: str) -> str:
    """Make a value safe for a Markdown table cell."""
    return re.sub(r"\s+", " ", str(s or "")).replace("|", "\\|").strip()


@dataclass
class Cand:
    doi: str
    title: str = ""
    author: str = ""
    year: str = ""
    venue: str = ""
    cites: int = 0
    modes: set = field(default_factory=set)        # {"A", "B"}
    ref_by_seeds: set = field(default_factory=set)  # seeds that CITE this candidate
    cites_seeds: set = field(default_factory=set)   # seeds this candidate cites
    queries: list = field(default_factory=list)     # mode B matched query strings

    def merge_meta(self, w: dict) -> None:
        self.title = self.title or w.get("title") or ""
        if not self.author:
            auth = w.get("authorships") or []
            self.author = surname(auth[0]["author"]["display_name"]) if auth else ""
        self.year = self.year or str(w.get("publication_year") or "")
        if not self.venue:
            self.venue = ((w.get("primary_location") or {}).get("source") or {}).get("display_name", "") or ""
        self.cites = self.cites or int(w.get("cited_by_count") or 0)

    @property
    def seed_count(self) -> int:
        return len(self.ref_by_seeds | self.cites_seeds)

    def why(self) -> str:
        parts = []
        if self.ref_by_seeds:
            parts.append(f"cited by {len(self.ref_by_seeds)} of my papers")
        if self.cites_seeds:
            parts.append(f"cites {len(self.cites_seeds)} of my papers")
        if self.queries:
            qs = "; ".join(f'"{q}"' for q in self.queries[:3])
            parts.append(f"matched query {qs}")
        return "; ".join(parts)


OA_SELECT = "id,doi,title,authorships,publication_year,primary_location,cited_by_count"


def oa_works(session: requests.Session, email: str, **params) -> list[dict]:
    params = {"mailto": email, **params}
    r = session.get(OPENALEX, params=params, timeout=40)
    r.raise_for_status()
    return r.json().get("results", [])


def oa_resolve_id(session: requests.Session, email: str, doi: str) -> str | None:
    r = session.get(f"{OPENALEX}/https://doi.org/{doi}",
                    params={"select": "id", "mailto": email}, timeout=30)
    if r.status_code in (404, 400):
        return None
    r.raise_for_status()
    return r.json().get("id", "").split("/")[-1] or None


# --------------------------------------------------------------------------- #
# mode A — citation graph
# --------------------------------------------------------------------------- #
def add_candidate(cands: dict, w: dict) -> Cand | None:
    doi = norm_doi(w.get("doi") or "")
    if not doi:
        return None
    c = cands.get(doi)
    if c is None:
        c = cands[doi] = Cand(doi=doi)
    c.merge_meta(w)
    return c


def mode_a(session, email, seeds: dict, cands: dict, skipped: list) -> int:
    """seeds: {stem: doi}. Mutates cands. Returns #seeds successfully queried."""
    ok = 0
    for stem, doi in sorted(seeds.items()):
        try:
            time.sleep(POLITE_DELAY)
            wid = oa_resolve_id(session, email, doi)
            if not wid:
                skipped.append(f"{stem} (no OpenAlex match)")
                continue
            # outgoing: cited_by:{wid} == works cited BY the seed (its references).
            # The seed points to (references) the candidate -> "cited by my paper".
            time.sleep(POLITE_DELAY)
            for w in oa_works(session, email, filter=f"cited_by:{wid}",
                              select=OA_SELECT, per_page=str(MAX_OUTGOING)):
                c = add_candidate(cands, w)
                if c:
                    c.modes.add("A")
                    c.ref_by_seeds.add(stem)
            # incoming: cites:{wid} == works that CITE the seed -> candidate cites seed.
            time.sleep(POLITE_DELAY)
            for w in oa_works(session, email, filter=f"cites:{wid}", select=OA_SELECT,
                              sort="cited_by_count:desc", per_page=str(MAX_INCOMING)):
                c = add_candidate(cands, w)
                if c:
                    c.modes.add("A")
                    c.cites_seeds.add(stem)
            ok += 1
        except requests.exceptions.RequestException as e:
            skipped.append(f"{stem} ({type(e).__name__})")
    return ok


# --------------------------------------------------------------------------- #
# mode B — plan keywords
# --------------------------------------------------------------------------- #
STOP = set("""the a an and or of to in on for with by from as is are was were be been being this that these those
it its their our we you they he she his her them at into than then thus also can may might will would could should
not no nor but which who whom whose where when while how what why all any both each few more most other some such only
own same so too very s t just over under above below up down out off again further here there once during between within
without across about against among through per via using used use model models result results method methods figure
figures show shows shown found find data set sets value values number numbers paper study studies based across given
information missing analysis approach effect effects role roles""".split())


def extract_queries(plan_text: str, max_q: int = 8) -> list[str]:
    queries: list[str] = []
    seen = set()

    def push(q: str):
        q = re.sub(r"\s+", " ", q).strip()
        if q and q.lower() not in seen and len(q) > 3:
            seen.add(q.lower())
            queries.append(q)

    m = re.search(r"^#\s+(.+)$", plan_text, re.MULTILINE)
    if m:
        push(m.group(1))

    # frequent topical bigrams over the prose (drop the references list noise)
    prose = plan_text.split("## References")[0]
    toks = re.findall(r"[a-zA-Z][a-zA-Z\-]+", prose.lower())
    content = [(t, t not in STOP and len(t) > 2) for t in toks]
    bigrams: Counter = Counter()
    for (w1, ok1), (w2, ok2) in zip(content, content[1:]):
        if ok1 and ok2:
            bigrams[f"{w1} {w2}"] += 1
    for phrase, n in bigrams.most_common():
        if n < 2:
            break
        push(phrase)
        if len(queries) >= max_q:
            break
    return queries[:max_q]


def mode_b(session, email, queries: list[str], cands: dict) -> None:
    for q in queries:
        try:
            time.sleep(POLITE_DELAY)
            for w in oa_works(session, email, search=q, select=OA_SELECT,
                              per_page=str(PER_QUERY)):
                c = add_candidate(cands, w)
                if c:
                    c.modes.add("B")
                    if q not in c.queries:
                        c.queries.append(q)
        except requests.exceptions.RequestException:
            continue  # one noisy query must not abort the rest


def mode_b_s2(session, email, queries: list[str], cands: dict) -> None:
    """Optional Semantic Scholar keyword supplement (best-effort, never fatal)."""
    fields = "title,year,externalIds,citationCount,authors,venue"
    for q in queries:
        try:
            time.sleep(POLITE_DELAY)
            r = session.get(S2_SEARCH, params={"query": q, "fields": fields, "limit": "20"},
                            timeout=40)
            if r.status_code != 200:
                continue
            for p in r.json().get("data", []) or []:
                doi = norm_doi((p.get("externalIds") or {}).get("DOI") or "")
                if not doi:
                    continue
                c = cands.get(doi) or cands.setdefault(doi, Cand(doi=doi))
                c.modes.add("B")
                c.title = c.title or p.get("title") or ""
                c.year = c.year or str(p.get("year") or "")
                c.venue = c.venue or p.get("venue") or ""
                c.cites = c.cites or int(p.get("citationCount") or 0)
                if not c.author:
                    auth = p.get("authors") or []
                    c.author = surname(auth[0].get("name", "")) if auth else ""
                if q not in c.queries:
                    c.queries.append(q)
        except requests.exceptions.RequestException:
            continue


# --------------------------------------------------------------------------- #
# preserve approvals across runs
# --------------------------------------------------------------------------- #
DOI_IN_TEXT = re.compile(r"10\.\d{4,9}/\S+")


def parse_old(path: Path) -> tuple[set[str], dict[str, list[str]]]:
    """Return (approved DOIs, {doi: full old row cells}) from a previous file."""
    approved: set[str] = set()
    rows: dict[str, list[str]] = {}
    if not path.exists():
        return approved, rows
    for line in path.read_text().splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 9:
            continue
        if cells[1].lower() == "year":                       # header row
            continue
        if all(set(c) <= set("-: ") for c in cells):         # separator row
            continue
        doi = ""
        for c in cells:
            mm = DOI_IN_TEXT.search(c)
            if mm:
                doi = norm_doi(mm.group(0).rstrip(").]"))
                break
        if not doi:
            continue
        rows[doi] = cells
        if "[x]" in cells[0].lower():
            approved.add(doi)
    return approved, rows


# --------------------------------------------------------------------------- #
# render + main
# --------------------------------------------------------------------------- #
HEADER_ROW = "| ✓ | year | first author | title | venue | cites | DOI | why | seed |"
SEP_ROW = "|---|---|---|---|---|---|---|---|---|"


def row_for(c: Cand, approved: set[str]) -> str:
    tick = "[x]" if c.doi in approved else "[ ]"
    modes = "+".join(sorted(c.modes))
    return (f"| {tick} | {cell(c.year)} | {cell(c.author)} | {cell(c.title)} | "
            f"{cell(c.venue)} | {c.cites} | {cell(c.doi)} | {cell(c.why())} | {modes} |")


def main() -> int:
    ap = argparse.ArgumentParser(description="Suggest new papers for a project (review file).")
    ap.add_argument("--vault", required=True, type=Path)
    ap.add_argument("--project", required=True)
    ap.add_argument("--email", required=True, help="contact email for the polite API User-Agent")
    ap.add_argument("--from", dest="mode", choices=["A", "B", "both"], default="both")
    ap.add_argument("--limit", type=int, default=40, help="max rows to write")
    ap.add_argument("--semantic-scholar", action="store_true",
                    help="also query Semantic Scholar for the plan keywords (optional)")
    args = ap.parse_args()

    library = args.vault / "_library"
    if not (library / "manifest.json").exists():
        sys.exit(f"no manifest under {library} — is this the vault root?")
    manifest = load_manifest(library)
    by_id_norm = {norm_doi(k) for k in manifest.get("by_id", {}) if k.lower().startswith("10.")}

    seeds = {}  # stem -> doi
    for stem, e in manifest.get("entries", {}).items():
        if args.project in e.get("projects", []) and e.get("doi"):
            seeds[stem] = e["doi"]
    if not seeds:
        sys.exit(f"no seed papers with a DOI tagged '{args.project}'.")

    plan_path = args.vault / "projects" / args.project / "plan.md"
    plan_present = plan_path.exists()
    queries: list[str] = []
    run_a = args.mode in ("A", "both")
    run_b = args.mode in ("B", "both") and plan_present
    note = ""
    if args.mode in ("B", "both") and not plan_present:
        note = f"plan.md not found at {plan_path} — ran mode A only."
        if args.mode == "B":
            sys.exit(note)
    if run_b:
        queries = extract_queries(plan_path.read_text())

    session = requests.Session()
    session.headers["User-Agent"] = f"neuresearch/1.0 (mailto:{args.email})"

    cands: dict[str, Cand] = {}
    skipped_seeds: list[str] = []
    seeds_ok = 0
    if run_a:
        print(f"mode A: querying OpenAlex citation graph for {len(seeds)} seeds…")
        seeds_ok = mode_a(session, args.email, seeds, cands, skipped_seeds)
    if run_b:
        print(f"mode B: {len(queries)} plan queries via OpenAlex search"
              f"{' + Semantic Scholar' if args.semantic_scholar else ''}…")
        mode_b(session, args.email, queries, cands)
        if args.semantic_scholar:
            mode_b_s2(session, args.email, queries, cands)

    raw = len(cands)
    for doi in list(cands):                # drop anything already in the library
        if doi in by_id_norm:
            del cands[doi]
    n_after = len(cands)
    n_dropped = raw - n_after

    # rank: citation-graph hits first, then by #seeds, then citation count
    ranked = sorted(cands.values(),
                    key=lambda c: (0 if "A" in c.modes else 1, -c.seed_count, -c.cites))
    shown = ranked[:args.limit]

    sugg_path = args.vault / "projects" / args.project / "suggestions.md"
    approved, old_rows = parse_old(sugg_path)
    present = {c.doi for c in shown}

    # never wipe approvals: carry over ticked DOIs that fell out of the candidate
    # set AND are not yet in the library (those in the library were acted upon).
    carried = [old_rows[d] for d in sorted(approved)
               if d not in present and d not in by_id_norm and d in old_rows]

    out: list[str] = []
    ts = time.strftime("%Y-%m-%d %H:%M")
    src = "OpenAlex" + (" + Semantic Scholar" if args.semantic_scholar else "")
    out.append(f"# Suggestions — {args.project}")
    out.append("")
    out.append(f"_Generated {ts} from {src}. Read-only on the library; nothing was fetched. "
               f"Tick ✓ (`[x]`) to keep a paper — ticks are preserved across re-runs._")
    out.append("")
    if note:
        out.append(f"> {note}")
        out.append("")
    out.append("**Plan queries used (mode B):**")
    out.append("")
    if queries:
        out += [f"- \"{q}\"" for q in queries]
    else:
        out.append("- _(none — mode A only)_")
    out.append("")
    out.append(f"**Counts:** {len(seeds)} existing seeds (with DOI; {seeds_ok} resolved on OpenAlex) · "
               f"{len(queries)} plan queries · {n_after} candidates after dedup · "
               f"{n_dropped} dropped (already in library) · {len(carried)} carried-over approvals.")
    if skipped_seeds:
        out.append("")
        out.append(f"_Seeds skipped (API error / no match): {', '.join(skipped_seeds)}._")
    out.append("")
    out.append(HEADER_ROW)
    out.append(SEP_ROW)
    for c in shown:
        out.append(row_for(c, approved))
    for cells in carried:
        cells = list(cells)
        cells[0] = "[x]"
        out.append("| " + " | ".join(cells) + " |")
    out.append("")

    sugg_path.write_text("\n".join(out))

    print(f"\nWrote {sugg_path}")
    print(f"  {n_after} candidates (showing {len(shown)}), {n_dropped} already in library, "
          f"{len(carried)} approvals carried over, {len(skipped_seeds)} seeds skipped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
