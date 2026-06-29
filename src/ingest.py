#!/usr/bin/env python3
"""
ingest.py
=========
Absorb a MANUALLY acquired PDF (institutional access, a colleague, etc.) into
the neubrain vault as a full library citizen — identified, deduped, given a
stem/citekey, recorded in the manifest, and logged — using the same conventions
as fetch_papers. It does NOT write a lit/ node; that stays make_nodes' job. The
new manifest entry is simply now ready for make_nodes to pick up.

    python ingest.py --vault /path/to/neubrain --project astro_atp \
        --file paper.pdf --doi 10.x/y [--grobid http://localhost:8070]
    python ingest.py --vault /path/to/neubrain --project astro_atp \
        --dir  inbox/ [--grobid http://localhost:8070]

IDENTITY (never guessed — if unsure, STOP and report):
    1. --doi if given;
    2. else a DOI scraped from the PDF's first page (regex 10.\\d{4,9}/...);
    3. else a Crossref bibliographic title search over the first-page text,
       accepted ONLY when the candidate title's words actually appear on the
       page (token overlap). Otherwise the file is left for a human to supply
       --doi. A DOI is confirmed by resolving its metadata; if neither Crossref
       nor OpenAlex knows it, that is "not confident" too.

PER PDF, once identified:
    - resolve metadata (title/first-author/year/venue) from the DOI;
    - assign the SAME stem scheme as fetch_papers (firstauthor+year, letter
      suffix on collision); if the DOI is already in the manifest, or the stem
      file already exists, it is reported and SKIPPED (one copy per paper);
    - copy the PDF to _library/<stem>.pdf;
    - recover cited_dois via Crossref, then GROBID if --grobid is set;
    - write the manifest entry (source_of_fulltext="manual", refs_source set,
      projects=[project], files=["<stem>.pdf"], fetched_at) and append a line
      to logs/fetch-log.md via FetchLog, marked manual.

--dir processes every *.pdf and prints a summary table (identified vs
needs-manual-doi vs skipped); one unidentifiable file never fails the batch.

Politeness: fixed inter-call delay + contact email in the User-Agent. Public
APIs only. Manifest stays the source of truth; metadata is never fabricated.

Requires: Python 3.10+, `requests`, and the `pdftotext` CLI (poppler) for DOI
scraping. Optional: a running GROBID server (--grobid).
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import requests  # pip install requests

# import sibling modules regardless of CWD, and reuse their tested helpers
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_papers import (Record, assign_stem, load_manifest,  # noqa: E402
                          manifest_lookup, manifest_register, save_manifest)
from log_writer import FetchLog  # noqa: E402
from refs import crossref_refs, grobid_refs, POLITE_DELAY, DEFAULT_EMAIL  # noqa: E402

CROSSREF = "https://api.crossref.org/works"
OPENALEX = "https://api.openalex.org/works"
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>]+", re.IGNORECASE)


# --------------------------------------------------------------------------- #
# PDF text + DOI scraping
# --------------------------------------------------------------------------- #
def pdf_first_page_text(pdf: Path) -> str:
    """First-page plain text via the poppler `pdftotext` CLI ('' if unavailable)."""
    if not shutil.which("pdftotext"):
        return ""
    r = subprocess.run(["pdftotext", "-f", "1", "-l", "1", str(pdf), "-"],
                       capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def scrape_doi(text: str) -> str | None:
    m = DOI_RE.search(text)
    if not m:
        return None
    # DOIs in body text pick up trailing punctuation/brackets — trim it off
    return m.group(0).rstrip(".,;:)>]}”\"'")


def _tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", s.lower()) if len(t) > 2}


def title_in_text(title: str, page_text: str, threshold: float = 0.6) -> bool:
    """True if most of the candidate title's words actually appear on the page."""
    tt = _tokens(title)
    if not tt:
        return False
    overlap = len(tt & _tokens(page_text)) / len(tt)
    return overlap >= threshold


# --------------------------------------------------------------------------- #
# metadata + references from public APIs
# --------------------------------------------------------------------------- #
def crossref_work(doi: str, session: requests.Session) -> dict | None:
    """Metadata + reference DOIs from Crossref, or None if the DOI is unknown."""
    r = session.get(f"{CROSSREF}/{doi}", timeout=30)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    m = r.json().get("message", {})
    authors = m.get("author") or []
    family = (authors[0].get("family", "") if authors else "")
    year = ""
    for key in ("published-print", "published-online", "issued", "created"):
        dp = (m.get(key) or {}).get("date-parts") or []
        if dp and dp[0] and dp[0][0]:
            year = str(dp[0][0])
            break
    return {
        "doi": (m.get("DOI") or doi),
        "title": (m.get("title") or [""])[0],
        "family": family,
        "year": year,
        "venue": (m.get("container-title") or [""])[0],
    }


def openalex_work(doi: str, session: requests.Session) -> dict | None:
    """Fallback metadata from OpenAlex (no DOI-keyed refs, so none returned)."""
    r = session.get(f"{OPENALEX}/https://doi.org/{doi}", timeout=30)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    w = r.json()
    auth = w.get("authorships") or []
    dn = (auth[0].get("author", {}).get("display_name", "") if auth else "")
    family = dn.split()[-1] if dn else ""
    venue = ((w.get("primary_location") or {}).get("source") or {}).get("display_name", "")
    return {
        "doi": (w.get("doi") or "").replace("https://doi.org/", "") or doi,
        "title": w.get("title") or "",
        "family": family,
        "year": str(w.get("publication_year") or ""),
        "venue": venue or "",
    }


def resolve_metadata(doi: str, session: requests.Session) -> dict | None:
    time.sleep(POLITE_DELAY)
    meta = crossref_work(doi, session)
    if meta and meta.get("title"):
        return meta
    time.sleep(POLITE_DELAY)
    return openalex_work(doi, session)


def crossref_title_search(query: str, session: requests.Session) -> tuple[str, str] | None:
    params = {"query.bibliographic": query[:500], "rows": "1", "select": "DOI,title"}
    r = session.get(CROSSREF, params=params, timeout=30)
    r.raise_for_status()
    items = r.json().get("message", {}).get("items", [])
    if not items:
        return None
    it = items[0]
    return it.get("DOI", ""), (it.get("title") or [""])[0]


# --------------------------------------------------------------------------- #
# identify one PDF
# --------------------------------------------------------------------------- #
def identify(pdf: Path, explicit_doi: str | None, session: requests.Session) -> tuple[str | None, str]:
    """Return (doi, how). doi is None when identity is not confident."""
    if explicit_doi:
        return explicit_doi.strip(), "explicit"

    page = pdf_first_page_text(pdf)
    doi = scrape_doi(page)
    if doi:
        return doi, "scraped"

    if page.strip():
        time.sleep(POLITE_DELAY)
        hit = crossref_title_search(page, session)
        if hit and hit[0] and title_in_text(hit[1], page):
            return hit[0], "title-search"
    return None, "needs-manual-doi"


# --------------------------------------------------------------------------- #
# ingest one PDF -> manifest (no node)
# --------------------------------------------------------------------------- #
def ingest_one(pdf: Path, explicit_doi: str | None, args, manifest: dict,
               session: requests.Session, log: FetchLog) -> dict:
    """Process a single PDF. Returns a result row; never raises on bad identity."""
    library = args.vault / "_library"
    res = {"file": pdf.name, "stem": "", "doi": "", "status": ""}

    doi, how = identify(pdf, explicit_doi, session)
    if not doi:
        res["status"] = "needs-manual-doi"
        return res
    res["doi"] = doi

    meta = resolve_metadata(doi, session)
    if not meta or not meta.get("title"):
        # DOI did not resolve anywhere — refuse to invent metadata
        res["status"] = "unresolved-doi"
        return res

    rec = Record(raw=pdf.name, doi=meta["doi"], title=meta["title"],
                 authors=meta["family"], year=meta["year"])

    # dedup: already a citizen? (one copy per paper)
    existing = manifest_lookup(manifest, rec)
    if existing:
        res["stem"] = existing
        res["status"] = f"skip (already in library as {existing})"
        return res

    stem = assign_stem(rec, manifest)
    dest = library / f"{stem}.pdf"
    if dest.exists():
        res["stem"] = stem
        res["status"] = f"skip (file {dest.name} already exists)"
        return res

    # cited_dois via the same order as refs.py (Crossref -> GROBID-if-URL)
    refs, refs_source = recover_refs(rec.doi, dest, args.grobid, session, pdf)

    shutil.copy2(pdf, dest)
    manifest_register(manifest, rec, stem, [dest.name], "manual", args.project)
    entry = manifest["entries"][stem]
    entry["cited_dois"] = refs
    entry["refs_source"] = refs_source

    log.record(stem=stem, source="manual", title=rec.title, doi=rec.doi)

    res["stem"] = stem
    res["status"] = f"ingested ({how}; refs={len(refs)} via {refs_source})"
    return res


def recover_refs(doi: str, dest_pdf: Path, grobid: str | None,
                 session: requests.Session, src_pdf: Path) -> tuple[list[str], str]:
    """Crossref reference array first, then GROBID over the PDF if a URL is given."""
    time.sleep(POLITE_DELAY)
    cr = crossref_refs(doi, session)
    if cr:
        return cr, "crossref"
    if grobid:
        time.sleep(POLITE_DELAY)
        gr = grobid_refs(src_pdf, grobid, session)  # read the source PDF (dest not copied yet)
        if gr:
            return gr, "grobid"
    return [], "none"


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="Ingest a manually acquired PDF into the vault.")
    ap.add_argument("--vault", required=True, type=Path, help="neubrain vault root")
    ap.add_argument("--project", required=True, help="project to tag the ingested paper with")
    ap.add_argument("--file", type=Path, help="a single PDF to ingest")
    ap.add_argument("--doi", default=None, help="DOI for --file (skips identification)")
    ap.add_argument("--dir", type=Path, help="a folder of PDFs to ingest")
    ap.add_argument("--grobid", default=None, help="GROBID base URL (optional refs fallback)")
    ap.add_argument("--email", default=DEFAULT_EMAIL,
                    help="contact email placed in the polite API User-Agent")
    args = ap.parse_args()

    if bool(args.file) == bool(args.dir):
        sys.exit("give exactly one of --file or --dir")
    if args.dir and args.doi:
        sys.exit("--doi applies to a single --file, not --dir")

    library = args.vault / "_library"
    if not (library / "manifest.json").exists():
        sys.exit(f"no manifest under {library} — is this the vault root?")
    library.mkdir(parents=True, exist_ok=True)

    if args.file:
        if not args.file.exists():
            sys.exit(f"file not found: {args.file}")
        pdfs = [args.file]
    else:
        if not args.dir.is_dir():
            sys.exit(f"directory not found: {args.dir}")
        pdfs = sorted(args.dir.glob("*.pdf"))
        if not pdfs:
            sys.exit(f"no *.pdf files in {args.dir}")

    manifest = load_manifest(library)
    session = requests.Session()
    session.headers["User-Agent"] = f"neuresearch/1.0 (mailto:{args.email})"
    log = FetchLog(vault=args.vault)

    rows = []
    for pdf in pdfs:
        explicit = args.doi if args.file else None
        try:
            row = ingest_one(pdf, explicit, args, manifest, session, log)
        except requests.exceptions.RequestException as e:
            # a transient network/API error on one file must not abort a batch
            row = {"file": pdf.name, "stem": "", "doi": "", "status": f"error: {e}"}
        rows.append(row)
        print(f"[{row['status'].split()[0]:<12}] {pdf.name}"
              f"{('  -> ' + row['stem']) if row['stem'] else ''}")

    save_manifest(library, manifest)
    log.flush(project=args.project)

    # summary table
    fw = max((len(r["file"]) for r in rows), default=4)
    sw = max((len(r["stem"]) for r in rows), default=4)
    print()
    print(f"{'file':<{fw}}  {'stem':<{sw}}  status")
    print(f"{'-'*fw}  {'-'*sw}  {'-'*6}")
    for r in rows:
        print(f"{r['file']:<{fw}}  {r['stem'] or '-':<{sw}}  {r['status']}")

    ingested = sum(r["status"].startswith("ingested") for r in rows)
    needs = sum(r["status"] == "needs-manual-doi" for r in rows)
    print(f"\n{len(rows)} PDF(s): {ingested} ingested, {needs} need a manual --doi, "
          f"{len(rows) - ingested - needs} skipped/other. "
          f"Log: {args.vault / 'logs' / 'fetch-log.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
