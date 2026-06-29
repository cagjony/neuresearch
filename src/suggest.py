#!/usr/bin/env python3
"""
suggest.py — propose NEW candidate papers for a project, as a reviewable table
=============================================================================
    conda run -n neuresearch python3 src/suggest.py \
        --vault /path/to/neubrain --project astro_atp --email you@kuleuven.be

For every paper already in the project (a "seed" = manifest entry tagged with
--project that has a DOI), this queries OpenAlex for:
  - incoming citations  (works that CITE the seed; `filter=cites:<id>`), and
  - outgoing references (works the seed CITES; its `referenced_works`).
Candidates are pooled, de-duplicated by DOI, and any paper already in the
library is dropped. They are ranked by how many seeds connect to them (then by
citation count) and written to projects/<project>/suggestions.md as a Markdown
table, one row per candidate with a leading `approve` checkbox.

CRITICAL — approvals are sticky: on a re-run the previous suggestions.md is read
first and every DOI you ticked ([x]) is carried over. Candidate rows are
regenerated fresh from the APIs, but your approvals are NEVER wiped.

Note: a `[x]` inside a table cell is plain text (Markdown task-list checkboxes
are only interactive outside tables); tick by editing the cell to `[x]`.

Scope: OpenAlex only, no key needed (uses the polite pool via --email). The
manifest stays the source of truth for "what we already have". Read-only w.r.t.
_library/ and the manifest; the only file written is suggestions.md.

Requires: Python 3.10+, requests.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests

OPENALEX = "https://api.openalex.org"
DELAY = 0.2  # polite pause between OpenAlex calls


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def norm_doi(doi: str | None) -> str:
    if not doi:
        return ""
    d = doi.strip().lower()
    d = re.sub(r"^https?://(dx\.)?doi\.org/", "", d)
    return d


def oa_id(url: str) -> str:
    return url.rsplit("/", 1)[-1] if url else ""


def surname(display_name: str | None) -> str:
    if not display_name:
        return ""
    return display_name.strip().split(" ")[-1]


def cell(s: str | None) -> str:
    """Make a value safe for a Markdown table cell."""
    if s is None:
        return ""
    return re.sub(r"\s+", " ", str(s)).replace("|", r"\|").strip()


def clip(s: str, n: int) -> str:
    s = s.strip()
    return s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + "…"


# --------------------------------------------------------------------------- #
# OpenAlex
# --------------------------------------------------------------------------- #
def oa_get(session: requests.Session, path: str, params: dict, email: str) -> dict | None:
    p = {**params, "mailto": email}
    for attempt in range(4):
        time.sleep(DELAY)
        r = session.get(f"{OPENALEX}{path}", params=p, timeout=40)
        if r.status_code == 404:
            return None
        if r.status_code == 429:                      # rate limited -> back off and retry
            wait = float(r.headers.get("Retry-After", 2 ** attempt))
            time.sleep(min(wait, 10))
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()   # exhausted retries on 429 -> raise the last one
    return None


def record_meta(rec: dict) -> dict:
    src = (rec.get("primary_location") or {}).get("source") or {}
    auth = rec.get("authorships") or []
    first = surname(auth[0]["author"]["display_name"]) if auth else ""
    return {
        "year": rec.get("publication_year") or "",
        "first_author": first,
        "title": rec.get("title") or rec.get("display_name") or "",
        "venue": src.get("display_name") or "",
        "citations": rec.get("cited_by_count") or 0,
    }


# --------------------------------------------------------------------------- #
# preserve approvals from a previous suggestions.md
# --------------------------------------------------------------------------- #
def read_approvals(path: Path) -> set[str]:
    """Return the set of DOIs whose `approve` cell was ticked in an old table."""
    if not path.exists():
        return set()
    approved: set[str] = set()
    approve_i = doi_i = None
    for line in path.read_text().splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        low = [c.lower() for c in cells]
        if approve_i is None:
            if "approve" in low and "doi" in low:   # header row
                approve_i, doi_i = low.index("approve"), low.index("doi")
            continue
        if set("".join(cells)) <= set("-: "):        # separator row
            continue
        if max(approve_i, doi_i) < len(cells):
            if "x" in low[approve_i]:
                d = norm_doi(cells[doi_i])
                if d:
                    approved.add(d)
    return approved


# --------------------------------------------------------------------------- #
# render
# --------------------------------------------------------------------------- #
def render(project: str, rows: list[dict], approved: set[str],
           plan: dict) -> str:
    out = [
        f"# Suggestions — {project}",
        "",
        f"_Generated {time.strftime('%Y-%m-%d %H:%M')} from OpenAlex. Review and tick "
        "`approve` ([x]) to keep a paper; ticks are preserved across re-runs._",
        "",
        "**Plan / queries**",
        "",
        f"- Seeds: **{plan['n_seeds']}** project papers with a DOI "
        f"(of {plan['n_tagged']} tagged '{project}').",
        f"- Per seed: OpenAlex `cites:` (incoming, top {plan['per_cite']} by citations) "
        f"+ `referenced_works` (outgoing, up to {plan['max_refs']}).",
        f"- Raw hits: {plan['n_raw']}; after dedup + dropping "
        f"{plan['n_lib']} library papers: **{plan['n_cand']}** candidates.",
        f"- Showing top **{len(rows)}** by #seeds then citation count.",
        f"- Approvals carried over from previous file: **{plan['n_carried']}**.",
    ]
    if plan["skipped_seeds"]:
        out.append(f"- Seeds skipped (API error/no match): {', '.join(plan['skipped_seeds'])}.")
    out += [
        "",
        "| approve | year | first author | title | venue | citations | DOI | why | seed |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        tick = "[x]" if r["doi"] in approved else "[ ]"
        out.append("| " + " | ".join([
            tick, cell(r["year"]), cell(r["first_author"]),
            cell(clip(r["title"], 90)), cell(clip(r["venue"], 40)),
            cell(r["citations"]), cell(r["doi"]), cell(r["why"]),
            cell(", ".join(sorted(r["seeds"]))),
        ]) + " |")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="Suggest new candidate papers for a project (OpenAlex).")
    ap.add_argument("--vault", required=True, type=Path, help="neubrain vault root")
    ap.add_argument("--project", required=True, help="project to suggest papers for")
    ap.add_argument("--email", required=True, help="contact email (OpenAlex polite pool)")
    ap.add_argument("--limit", type=int, default=50, help="max candidate rows to write")
    ap.add_argument("--per-seed-citing", type=int, default=25, help="citing works fetched per seed")
    ap.add_argument("--max-refs", type=int, default=50, help="references inspected per seed")
    args = ap.parse_args()

    library = args.vault / "_library"
    if not (library / "manifest.json").exists():
        sys.exit(f"no manifest under {library} — is this the vault root?")
    manifest = json.loads((library / "manifest.json").read_text())
    entries = manifest.get("entries", {})

    library_dois = {norm_doi(e.get("doi")) for e in entries.values() if e.get("doi")}
    seeds = {s: norm_doi(e.get("doi")) for s, e in entries.items()
             if args.project in e.get("projects", []) and e.get("doi")}
    n_tagged = sum(1 for e in entries.values() if args.project in e.get("projects", []))
    if not seeds:
        sys.exit(f"no seed papers with a DOI tagged '{args.project}'")

    session = requests.Session()
    session.headers["User-Agent"] = f"neuresearch/1.0 (mailto:{args.email})"

    candidates: dict[str, dict] = {}   # norm_doi -> {meta..., cites_seeds, ref_seeds}
    n_raw = 0
    skipped: list[str] = []

    def add(rec: dict, seed_stem: str, direction: str) -> None:
        nonlocal n_raw
        d = norm_doi(rec.get("doi"))
        if not d or d in library_dois:
            return
        n_raw += 1
        c = candidates.get(d)
        if c is None:
            c = {"doi": d, **record_meta(rec), "cites_seeds": set(), "ref_seeds": set()}
            candidates[d] = c
        (c["cites_seeds"] if direction == "cites" else c["ref_seeds"]).add(seed_stem)

    for stem in sorted(seeds):
        doi = seeds[stem]
        try:
            work = oa_get(session, f"/works/doi:{doi}", {}, args.email)
            if not work:
                skipped.append(f"{stem} (no OpenAlex match)"); continue
            wid = oa_id(work["id"])

            citing = oa_get(session, "/works", {
                "filter": f"cites:{wid}", "per-page": args.per_seed_citing,
                "sort": "cited_by_count:desc"}, args.email) or {}
            for rec in citing.get("results", []):
                add(rec, stem, "cites")

            refs = [oa_id(x) for x in work.get("referenced_works", [])][:args.max_refs]
            for i in range(0, len(refs), 50):
                chunk = refs[i:i + 50]
                got = oa_get(session, "/works", {
                    "filter": f"openalex_id:{'|'.join(chunk)}", "per-page": 50}, args.email) or {}
                for rec in got.get("results", []):
                    add(rec, stem, "ref")
        except requests.exceptions.RequestException as e:
            skipped.append(f"{stem} ({e.__class__.__name__})")
            print(f"[WARN]  {stem}: OpenAlex query failed: {e}")

    # finalise rows
    rows = []
    for c in candidates.values():
        seeds_all = c["cites_seeds"] | c["ref_seeds"]
        why = []
        if c["cites_seeds"]:
            why.append("cites " + ", ".join(sorted(c["cites_seeds"])))
        if c["ref_seeds"]:
            why.append("cited by " + ", ".join(sorted(c["ref_seeds"])))
        rows.append({**c, "seeds": seeds_all, "why": "; ".join(why)})
    rows.sort(key=lambda r: (-len(r["seeds"]), -int(r["citations"] or 0),
                             -int(r["year"] or 0)))
    rows = rows[:args.limit]

    out_dir = args.vault / "projects" / args.project
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "suggestions.md"
    approved = read_approvals(out_path)

    plan = {"n_seeds": len(seeds), "n_tagged": n_tagged, "per_cite": args.per_seed_citing,
            "max_refs": args.max_refs, "n_raw": n_raw, "n_lib": len(library_dois),
            "n_cand": len(candidates), "n_carried": len(approved),
            "skipped_seeds": skipped}
    out_path.write_text(render(args.project, rows, approved, plan))

    print(f"suggest: {len(seeds)} seeds -> {len(candidates)} candidates "
          f"({len(rows)} shown); {len(approved)} approvals carried over.")
    print(f"  wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
