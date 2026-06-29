#!/usr/bin/env python3
"""
refs.py
=======
Backfill `cited_dois` for papers ALREADY in the neubrain vault, without any
format conversion. Many manifest entries have no reference DOIs — either their
JATS carried no DOI-tagged refs, or they are PDF-only. This recovers the cited
DOIs from public metadata (Crossref first, GROBID optional) and keeps the
manifest and the lit/ nodes in sync.

    python refs.py --vault /path/to/neubrain [--project astro_atp] \
        [--grobid http://localhost:8070] [--only-empty] [--email you@host]

RESOLUTION ORDER (per entry, stop at first success that yields ≥1 DOI):
    (a) JATS XML in _library/  — re-parse the archived <ref-list> for tagged
        DOIs (same extraction make_nodes uses). Grounded, offline, free.
    (b) Crossref — GET https://api.crossref.org/works/{doi}, read the
        "reference" array, collect each ref's "DOI" (refs without a DOI skipped).
    (c) GROBID — ONLY if --grobid is given AND _library/<stem>.pdf exists:
        POST the PDF to processFulltextDocument, read DOIs from the TEI
        <listBibl>.
    (d) leave [] (refs_source = none).

WHAT IT WRITES (idempotent; read-only on the archived PDFs/XML):
    - the manifest entry: cited_dois + refs_source (jats|crossref|grobid|none)
    - the lit/<stem>.md node frontmatter: the SAME cited_dois + refs_source,
      so nodes and manifest never drift. Claim summaries and the machine-owned
      ## Concepts / ## Related markers are never touched.

It never fabricates references: a source that returns nothing leaves [] and an
honest refs_source of "none". The manifest stays the source of truth.

Politeness: a fixed inter-call delay and a contact email in the User-Agent, as
the Crossref/GROBID etiquette asks. Public APIs only.

Requires: Python 3.10+, `requests`. Optional: a running GROBID server (--grobid).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from xml.etree import ElementTree as ET

import requests  # pip install requests

# import sibling modules regardless of CWD, and reuse their tested helpers
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_papers import load_manifest, save_manifest  # noqa: E402
from make_nodes import parse_jats, split_frontmatter, _yaml_scalar  # noqa: E402

CROSSREF = "https://api.crossref.org/works"
POLITE_DELAY = 0.34  # seconds between external calls
DEFAULT_EMAIL = "cagjony@gmail.com"  # contact for the polite User-Agent; override with --email


# --------------------------------------------------------------------------- #
# reference recovery from each source
# --------------------------------------------------------------------------- #
def jats_refs(xml_path: Path) -> list[str]:
    """Cited DOIs from an archived JATS file (reuses make_nodes' grounded parse)."""
    return parse_jats(xml_path)["cited_dois"]


def crossref_refs(doi: str, session: requests.Session) -> list[str] | None:
    """Cited DOIs from Crossref's "reference" array, order kept, case-insensitive dedup.

    Returns None if the DOI is unknown to Crossref (404); [] if the work is known
    but exposes no DOI-bearing references. Refs without a DOI are skipped (Crossref
    often has only an unstructured string for older or non-indexed citations).
    """
    r = session.get(f"{CROSSREF}/{doi}", timeout=30)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    refs = r.json().get("message", {}).get("reference", []) or []
    return _dedup_dois(ref.get("DOI") for ref in refs)


def grobid_refs(pdf: Path, grobid_url: str, session: requests.Session) -> list[str]:
    """Cited DOIs from GROBID TEI <listBibl> <idno type="DOI">."""
    with pdf.open("rb") as fh:
        r = session.post(f"{grobid_url}/api/processFulltextDocument",
                         files={"input": fh}, timeout=300)
    r.raise_for_status()
    return tei_refs(r.content)


def tei_refs(tei_bytes: bytes) -> list[str]:
    try:
        root = ET.fromstring(tei_bytes)
    except ET.ParseError:
        return []
    dois = []
    for idno in root.findall(".//{*}listBibl//{*}idno"):
        if (idno.get("type") or "").lower() == "doi":
            dois.append((idno.text or "").strip())
    return _dedup_dois(dois)


def _dedup_dois(raw) -> list[str]:
    out, seen = [], set()
    for d in raw:
        if not d:
            continue
        d = d.strip()
        if d and d.lower() not in seen:
            seen.add(d.lower())
            out.append(d)
    return out


def resolve_refs(stem: str, entry: dict, library: Path, grobid: str | None,
                 session: requests.Session) -> tuple[list[str], str]:
    """Run the resolution order; return (cited_dois, refs_source)."""
    files = entry.get("files", [])

    # (a) archived JATS — DOI-tagged <ref-list>
    xmlf = next((f for f in files if f.endswith(".xml")), None)
    if xmlf and (library / xmlf).exists():
        dois = jats_refs(library / xmlf)
        if dois:
            return dois, "jats"

    # (b) Crossref reference array
    doi = entry.get("doi", "")
    if doi:
        time.sleep(POLITE_DELAY)
        cr = crossref_refs(doi, session)
        if cr:
            return cr, "crossref"

    # (c) GROBID over the archived PDF (opt-in)
    if grobid:
        pdf = library / f"{stem}.pdf"
        if not pdf.exists():
            pdff = next((f for f in files if f.endswith(".pdf")), None)
            pdf = library / pdff if pdff else pdf
        if pdf.exists():
            time.sleep(POLITE_DELAY)
            gr = grobid_refs(pdf, grobid, session)
            if gr:
                return gr, "grobid"

    # (d) nothing recovered — honest empty
    return [], "none"


# --------------------------------------------------------------------------- #
# node frontmatter sync (surgical: only cited_dois + refs_source)
# --------------------------------------------------------------------------- #
import re  # noqa: E402  (kept local to the frontmatter helpers)


def render_cited_block(cited: list[str]) -> str:
    if not cited:
        return "cited_dois: []"
    return "cited_dois:\n" + "\n".join(f"  - {_yaml_scalar(d)}" for d in cited)


def set_refs_source(fm: str, source: str) -> str:
    new, n = re.subn(r"(?m)^refs_source:.*$", f"refs_source: {source}", fm, count=1)
    if n:
        return new
    # absent (older node): insert just after the `source:` line, else before fence
    new, n = re.subn(r"(?m)^(source:.*)$", rf"\1\nrefs_source: {source}", fm, count=1)
    if n:
        return new
    return fm.rsplit("\n---", 1)[0] + f"\nrefs_source: {source}\n---"


def set_cited_dois(fm: str, cited: list[str]) -> str:
    block = render_cited_block(cited)
    pattern = r"(?m)^cited_dois:.*(?:\n[ ]+- .*)*"
    new, n = re.subn(pattern, lambda _m: block, fm, count=1)
    if n:
        return new
    return fm.rsplit("\n---", 1)[0] + f"\n{block}\n---"


def update_node(lit: Path, stem: str, cited: list[str], source: str) -> str:
    """Sync cited_dois + refs_source into lit/<stem>.md frontmatter. Body untouched."""
    path = lit / f"{stem}.md"
    if not path.exists():
        return "no-node"
    text = path.read_text()
    fm, body = split_frontmatter(text)
    if not fm:
        return "no-frontmatter"
    fm = set_refs_source(fm, source)
    fm = set_cited_dois(fm, cited)
    new = fm + body
    if new != text:
        path.write_text(new)
        return "updated"
    return "unchanged"


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def select_entries(manifest: dict, project: str | None, only_empty: bool) -> list[str]:
    stems = []
    for stem, entry in manifest.get("entries", {}).items():
        if project and project not in entry.get("projects", []):
            continue
        if only_empty and entry.get("cited_dois"):
            continue
        stems.append(stem)
    return sorted(stems)


def main() -> int:
    ap = argparse.ArgumentParser(description="Backfill cited_dois for existing vault papers.")
    ap.add_argument("--vault", required=True, type=Path, help="neubrain vault root")
    ap.add_argument("--project", default=None, help="restrict to papers tagged with this project")
    ap.add_argument("--grobid", default=None, help="GROBID base URL (optional fallback for PDFs)")
    ap.add_argument("--only-empty", action="store_true",
                    help="process only entries whose cited_dois is currently empty/absent")
    ap.add_argument("--email", default=DEFAULT_EMAIL,
                    help="contact email placed in the polite API User-Agent")
    args = ap.parse_args()

    library = args.vault / "_library"
    lit = args.vault / "lit"
    if not (library / "manifest.json").exists():
        sys.exit(f"no manifest under {library} — is this the vault root?")

    manifest = load_manifest(library)
    stems = select_entries(manifest, args.project, args.only_empty)
    if not stems:
        scope = f" for project '{args.project}'" if args.project else ""
        print(f"no entries to process{scope}"
              f"{' (none with empty cited_dois)' if args.only_empty else ''}.")
        return 0

    session = requests.Session()
    session.headers["User-Agent"] = f"neuresearch/1.0 (mailto:{args.email})"

    rows = []  # (stem, old_n, new_n, source, node_status)
    for stem in stems:
        entry = manifest["entries"][stem]
        old_n = len(entry.get("cited_dois", []) or [])
        cited, source = resolve_refs(stem, entry, library, args.grobid, session)
        entry["cited_dois"] = cited
        entry["refs_source"] = source
        node_status = update_node(lit, stem, cited, source)
        rows.append((stem, old_n, len(cited), source, node_status))
        print(f"[{source:<8}] {stem}: {old_n} -> {len(cited)} refs ({node_status})")

    save_manifest(library, manifest)

    # summary table
    w = max((len(r[0]) for r in rows), default=4)
    print()
    print(f"{'stem':<{w}}  {'old#':>4}  {'new#':>4}  source")
    print(f"{'-'*w}  {'-'*4}  {'-'*4}  {'-'*8}")
    for stem, old_n, new_n, source, _ in rows:
        print(f"{stem:<{w}}  {old_n:>4}  {new_n:>4}  {source}")

    by_src: dict[str, int] = {}
    recovered = 0
    for _, old_n, new_n, source, _ in rows:
        by_src[source] = by_src.get(source, 0) + 1
        if old_n == 0 and new_n > 0:
            recovered += 1
    tally = ", ".join(f"{k}={v}" for k, v in sorted(by_src.items()))
    print(f"\n{len(rows)} entries processed — {recovered} newly populated. Sources: {tally}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
