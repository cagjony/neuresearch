#!/usr/bin/env python3
"""
fetch_papers.py
===============
Resolve a list of papers to open-access full-text XML, store each one ONCE in
the vault's _library, symlink the requested ones into a per-project folder, and
log every action to the vault's logs/ as Markdown.

    python fetch_papers.py papers.txt --vault /path/to/neubrain --project astro_atp \
        --email you@kuleuven.be [--grobid http://localhost:8070] [--also-md]

INPUT (papers.txt): one identifier per line; blank lines and '#' comments
ignored. Each line is auto-classified: DOI (10.x/y), PMID (digits),
PMCID (PMCxx...), or free-text TITLE.

LAYOUT (derived from --vault):
    <vault>/_library/         archive: <stem>.xml  +  manifest.json (ledger)
    <vault>/lit/              nodes (created later by Claude, not here)
    <vault>/projects/<p>/papers/   symlinks into _library
    <vault>/logs/fetch-log.md       append-only history (written here)

STEM = CITEKEY CONVENTION
    A paper's archive filename, its future lit/ node filename, and its citekey
    all share ONE stem, e.g. fujii2017 -> _library/fujii2017.xml,
    lit/fujii2017.md, [@fujii2017]. Collisions get a letter suffix
    (fujii2017, fujii2017a, ...). reconcile.py relies on this 1:1 stem mapping.

SCOPE / HONEST LIMITS  (open-access only, in priority order)
    1. Europe PMC full-text JATS XML   (publisher-structured)
    2. Unpaywall -> legal OA PDF        (fallback; optional GROBID -> TEI XML)
    Paywalled papers with no legal OA copy are NOT downloaded; they are logged
    as gaps for you to fetch via institutional access. No stub is ever written.

DESIGN (ephys-pipeline-invariants)
    - "not open access" is an expected RESULT (logged as a gap), not an error.
    - HTTP 5xx, malformed XML, bad config raise loudly with context.
    - fetched XML is validated (parses + <article> root) BEFORE writing, so a
      file in _library is always real. The manifest is the source of truth for
      dedup; the Markdown log is a human/Claude-readable projection of it.

Requires: Python 3.10+, `requests`. Optional: `pandoc` (--also-md),
a running GROBID server (--grobid).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import string
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

import requests  # pip install requests

# import the sibling log writer regardless of CWD
sys.path.insert(0, str(Path(__file__).resolve().parent))
from log_writer import FetchLog  # noqa: E402

EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
UNPAYWALL = "https://api.unpaywall.org/v2"
POLITE_DELAY = 0.34  # seconds between external calls


# --------------------------------------------------------------------------- #
# identifier classification + resolution
# --------------------------------------------------------------------------- #
def classify(token: str) -> tuple[str, str]:
    t = token.strip()
    if re.fullmatch(r"PMC\d+", t, re.IGNORECASE):
        return "pmcid", t.upper()
    if re.fullmatch(r"\d+", t):
        return "pmid", t
    if t.lower().startswith("10.") and "/" in t:
        return "doi", t
    return "title", t


def epmc_query(kind: str, value: str) -> str:
    if kind == "doi":
        return f'DOI:"{value}"'
    if kind == "pmid":
        return f"EXT_ID:{value} AND SRC:MED"
    if kind == "pmcid":
        return f"PMCID:{value}"
    return f'TITLE:"{value}"'


@dataclass
class Record:
    raw: str
    source: str = ""
    pmid: str = ""
    pmcid: str = ""
    doi: str = ""
    title: str = ""
    authors: str = ""
    year: str = ""
    is_oa: bool = False
    in_epmc: bool = False


def resolve(raw: str, session: requests.Session) -> Record | None:
    kind, value = classify(raw)
    params = {"query": epmc_query(kind, value),
              "format": "json", "pageSize": "1", "resultType": "core"}
    r = session.get(f"{EPMC}/search", params=params, timeout=30)
    r.raise_for_status()                       # 5xx -> loud
    hits = r.json().get("resultList", {}).get("result", [])
    if not hits:
        return None
    h = hits[0]
    return Record(
        raw=raw, source=h.get("source", ""), pmid=h.get("pmid", ""),
        pmcid=h.get("pmcid", ""), doi=h.get("doi", ""), title=h.get("title", ""),
        authors=h.get("authorString", ""), year=str(h.get("pubYear", "")),
        is_oa=(h.get("isOpenAccess") == "Y"), in_epmc=(h.get("inEPMC") == "Y"),
    )


# --------------------------------------------------------------------------- #
# stem / citekey assignment
# --------------------------------------------------------------------------- #
def base_stem(rec: Record) -> str:
    first = (rec.authors.split(",")[0] if rec.authors else "anon").split(" ")[0]
    first = re.sub(r"[^a-z0-9]", "", first.lower()) or "anon"
    return f"{first}{rec.year or '0000'}"


def assign_stem(rec: Record, manifest: dict) -> str:
    """Clean citekey-style stem, letter-suffixed on collision with a different paper."""
    taken = set(manifest.get("entries", {}).keys())
    base = base_stem(rec)
    if base not in taken:
        return base
    for suffix in string.ascii_lowercase:
        cand = base + suffix
        if cand not in taken:
            return cand
    return f"{base}{len(taken)}"


# --------------------------------------------------------------------------- #
# manifest (ledger)
# --------------------------------------------------------------------------- #
def load_manifest(library: Path) -> dict:
    f = library / "manifest.json"
    return json.loads(f.read_text()) if f.exists() else {"by_id": {}, "entries": {}}


def save_manifest(library: Path, manifest: dict) -> None:
    (library / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))


def manifest_lookup(manifest: dict, rec: Record) -> str | None:
    for key in (rec.doi, rec.pmid, rec.pmcid):
        if key and key in manifest["by_id"]:
            return manifest["by_id"][key]
    return None


def manifest_register(manifest: dict, rec: Record, stem: str, files: list[str], src: str) -> None:
    for key in (rec.doi, rec.pmid, rec.pmcid):
        if key:
            manifest["by_id"][key] = stem
    manifest["entries"][stem] = {
        "title": rec.title, "doi": rec.doi, "pmid": rec.pmid, "pmcid": rec.pmcid,
        "year": rec.year, "source_of_fulltext": src, "files": files,
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


# --------------------------------------------------------------------------- #
# fetchers
# --------------------------------------------------------------------------- #
def fetch_epmc_xml(rec: Record, session: requests.Session) -> bytes:
    r = session.get(f"{EPMC}/{rec.source}/{rec.pmcid}/fullTextXML", timeout=60)
    r.raise_for_status()
    return r.content


def validate_jats(xml_bytes: bytes) -> bool:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return False
    return root.tag.split("}")[-1].lower() == "article"


def unpaywall_pdf_url(doi: str, email: str, session: requests.Session) -> str | None:
    r = session.get(f"{UNPAYWALL}/{doi}", params={"email": email}, timeout=30)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    data = r.json()
    if not data.get("is_oa"):
        return None
    best = data.get("best_oa_location") or {}
    return best.get("url_for_pdf") or best.get("url")


def download(url: str, dest: Path, session: requests.Session) -> None:
    r = session.get(url, timeout=120, stream=True)
    r.raise_for_status()
    with dest.open("wb") as fh:
        for chunk in r.iter_content(chunk_size=1 << 15):
            fh.write(chunk)


def grobid_tei(pdf: Path, grobid_url: str, session: requests.Session) -> bytes:
    with pdf.open("rb") as fh:
        r = session.post(f"{grobid_url}/api/processFulltextDocument",
                         files={"input": fh}, timeout=300)
    r.raise_for_status()
    return r.content


def jats_to_md(xml_path: Path, md_path: Path) -> bool:
    import shutil, subprocess
    if not shutil.which("pandoc"):
        return False
    subprocess.run(["pandoc", "-f", "jats", "-t", "gfm",
                    "-o", str(md_path), str(xml_path)], check=True)
    return True


def symlink_into_project(src: Path, project_papers: Path) -> None:
    project_papers.mkdir(parents=True, exist_ok=True)
    link = project_papers / src.name
    if link.is_symlink() or link.exists():
        return
    link.symlink_to(os.path.relpath(src, project_papers))


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch OA full-text XML for a list of papers.")
    ap.add_argument("list", type=Path, help="text file, one identifier per line")
    ap.add_argument("--vault", required=True, type=Path, help="neubrain vault root")
    ap.add_argument("--project", required=True, help="project name under <vault>/projects")
    ap.add_argument("--email", required=True, help="contact email (required by Unpaywall)")
    ap.add_argument("--grobid", default=None, help="GROBID base URL (optional)")
    ap.add_argument("--also-md", action="store_true",
                    help="also render JATS XML -> Markdown (needs pandoc; usually unnecessary)")
    args = ap.parse_args()

    if not args.list.exists():
        sys.exit(f"input list not found: {args.list}")          # bad config -> loud
    if not args.vault.exists():
        sys.exit(f"vault not found: {args.vault}")

    library = args.vault / "_library"
    library.mkdir(parents=True, exist_ok=True)
    project_papers = args.vault / "projects" / args.project / "papers"

    tokens = [ln.strip() for ln in args.list.read_text().splitlines()
              if ln.strip() and not ln.lstrip().startswith("#")]

    session = requests.Session()
    session.headers["User-Agent"] = f"neuresearch/1.0 (mailto:{args.email})"
    manifest = load_manifest(library)
    log = FetchLog(vault=args.vault)
    n_new = n_linked = n_gap = 0

    for raw in tokens:
        time.sleep(POLITE_DELAY)
        rec = resolve(raw, session)
        if rec is None:
            log.gap(raw, "unresolved (no Europe PMC match)"); n_gap += 1
            print(f"[MISS]  {raw}"); continue

        # already in library -> ensure symlink, log a relink
        stem = manifest_lookup(manifest, rec)
        if stem and (library / f"{stem}.xml").exists():
            xmlp = library / f"{stem}.xml"
            symlink_into_project(xmlp, project_papers)
            if args.also_md and (library / f"{stem}.md").exists():
                symlink_into_project(library / f"{stem}.md", project_papers)
            log.relink(stem, args.project); n_linked += 1
            print(f"[HAVE]  {stem}"); continue

        stem = assign_stem(rec, manifest)
        xmlp = library / f"{stem}.xml"
        src_label = ""

        # --- source 1: Europe PMC JATS XML --- #
        if rec.in_epmc and rec.pmcid:
            time.sleep(POLITE_DELAY)
            xml = fetch_epmc_xml(rec, session)
            if not validate_jats(xml):
                raise RuntimeError(f"{stem}: Europe PMC returned non-JATS for "
                                   f"{rec.pmcid} (refusing to write a stub)")
            xmlp.write_bytes(xml)
            src_label = "europepmc-jats"

        # --- source 2: Unpaywall OA PDF (optional GROBID -> TEI) --- #
        elif rec.doi:
            time.sleep(POLITE_DELAY)
            pdf_url = unpaywall_pdf_url(rec.doi, args.email, session)
            if not pdf_url:
                log.gap(raw, "no legal OA copy (paywalled)"); n_gap += 1
                print(f"[GAP]   {stem}: paywalled"); continue
            pdf = library / f"{stem}.pdf"
            download(pdf_url, pdf, session)
            if args.grobid:
                tei = grobid_tei(pdf, args.grobid, session)
                if not (validate_jats(tei) or b"<TEI" in tei[:200]):
                    raise RuntimeError(f"{stem}: GROBID returned unexpected content")
                xmlp = library / f"{stem}.tei.xml"
                xmlp.write_bytes(tei)
                src_label = "unpaywall-pdf+grobid-tei"
            else:
                xmlp = pdf
                src_label = "unpaywall-pdf"
        else:
            log.gap(raw, "no DOI and not in Europe PMC"); n_gap += 1
            print(f"[GAP]   {raw}: no DOI / not in EPMC"); continue

        # --- optional Markdown rendering (JATS only) --- #
        files = [xmlp.name]
        if args.also_md and src_label == "europepmc-jats":
            mdp = library / f"{stem}.md"
            if jats_to_md(xmlp, mdp):
                files.append(mdp.name)
                symlink_into_project(mdp, project_papers)

        manifest_register(manifest, rec, stem, files, src_label)
        symlink_into_project(xmlp, project_papers)
        log.record(stem=stem, source=src_label, title=rec.title, doi=rec.doi)
        n_new += 1
        print(f"[OK]    {stem}  <-  {src_label}")

    save_manifest(library, manifest)
    log.flush(project=args.project)

    print(f"\nDone: {n_new} fetched, {n_linked} re-linked, {n_gap} gaps. "
          f"Log: {args.vault / 'logs' / 'fetch-log.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
