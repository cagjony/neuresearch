#!/usr/bin/env python3
"""
build_bib.py
============
Turn the neubrain manifest into a `references.bib` that pandoc/CSL (or Overleaf)
can resolve, so that a `[@stem]` in a manuscript or a `\\cite{stem}` in LaTeX
actually points at a real, formatted reference.

    python build_bib.py --vault /path/to/neubrain [--project NAME] \
        [--out PATH] [--email you@host]

WHAT IT DOES (per manifest entry — all of them, or only those whose "projects"
field contains --project):

    (a) has a DOI  -> fetch a clean, publisher-grade BibTeX entry from Crossref:
            GET https://api.crossref.org/works/{doi}/transform/application/x-bibtex
        Crossref names the entry with its own citekey (e.g. @article{Fujii_2017,…});
        we REPLACE that key with OUR manifest stem so `\\cite{fujii2017}` resolves.

    (b) no DOI     -> build a minimal @article{stem, …} from the manifest metadata
        we actually hold (title / year, and author / journal if present). Unknown
        fields are left blank — never invented.

The manifest is the source of truth: this script reads it, never writes it, and
fabricates no bibliographic field or citation. Output is fully regenerated each
run (idempotent). Default --out is projects/<project>/references.bib when
--project is given, else the vault-root master neubrain/references.bib.

Politeness: a fixed inter-call delay and a contact email in the User-Agent, as
Crossref etiquette asks. Public APIs only.

Requires: Python 3.10+, `requests`.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import requests  # pip install requests

# import sibling modules regardless of CWD, and reuse their tested helpers
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_papers import load_manifest  # noqa: E402

CROSSREF = "https://api.crossref.org/works"
POLITE_DELAY = 0.34  # seconds between external calls
DEFAULT_EMAIL = "cagjony@gmail.com"  # contact for the polite User-Agent; override with --email

# matches the "@type{ORIGKEY," header of the first (and only) entry Crossref returns
_BIB_HEADER = re.compile(r"(@\w+\s*\{)[^,]*,")


# --------------------------------------------------------------------------- #
# entry construction
# --------------------------------------------------------------------------- #
def crossref_bibtex(doi: str, session: requests.Session) -> str | None:
    """Clean BibTeX for a DOI from Crossref's content-negotiation transform.

    Returns the entry text, or None if Crossref does not know the DOI (404).
    """
    url = f"{CROSSREF}/{doi}/transform/application/x-bibtex"
    r = session.get(url, headers={"Accept": "application/x-bibtex"}, timeout=30)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    r.encoding = "utf-8"  # Crossref serves UTF-8; requests can mis-guess for text/*
    text = r.text.strip()
    return text or None


def rekey(bibtex: str, stem: str) -> str:
    """Swap the entry's Crossref citekey for OUR manifest stem (header only)."""
    new, n = _BIB_HEADER.subn(rf"\g<1>{stem},", bibtex, count=1)
    return new if n else bibtex


# Crossref BibTeX can carry XML/MathML fragments, HTML entities, smart
# punctuation, and non-Latin symbols (e.g. Greek β) that pdflatex's utf8
# inputenc cannot typeset — so the generated .bib fails to compile under a plain
# pdflatex + bibtex workflow. Sanitize those. Latin accents (à, ü, ç, ś, …) are
# LEFT as UTF-8 on purpose: they typeset fine under T1/utf8 and are real names.
_TAG_RE = re.compile(r"<[^>]+>")
_ENTITIES = {"&amp;": r"\&", "&lt;": "<", "&gt;": ">", "&quot;": '"',
             "&apos;": "'", "&#39;": "'", "&nbsp;": " "}
_UNICODE = {
    # smart punctuation -> ASCII / LaTeX dashes
    "“": '"', "”": '"', "‘": "'", "’": "'",
    "‐": "-", "‑": "-", "–": "--", "—": "---",
    # Greek letters that show up in titles -> math mode
    "α": r"$\alpha$", "β": r"$\beta$", "γ": r"$\gamma$",
    "δ": r"$\delta$", "ε": r"$\epsilon$", "κ": r"$\kappa$",
    "λ": r"$\lambda$", "μ": r"$\mu$", "σ": r"$\sigma$",
    "τ": r"$\tau$", "ω": r"$\omega$", "Δ": r"$\Delta$",
    "Ω": r"$\Omega$",
    # misc symbols
    "°": r"$^\circ$", "±": r"$\pm$", "×": r"$\times$",
    "⋅": r"$\cdot$",
}


# The url/DOI fields carry raw underscores (e.g. book-chapter DOIs like
# .../978-3-030-00817-8_5). Style macros such as plainnat's \doi print them as
# plain text, where '_' triggers "Missing $ inserted" unless hyperref is loaded.
# Drop both fields — the DOI still lives in the manifest (the source of truth);
# the .bib is derived and only needs to typeset.
_URLDOI_RE = re.compile(r",?\s*(?:url|doi)\s*=\s*\{[^}]*\}", re.I)


def latex_sanitize(bibtex: str) -> str:
    """Make a Crossref BibTeX entry safe for a pdflatex + bibtex build."""
    s = _TAG_RE.sub(" ", bibtex)                 # drop <mml:...> etc. (pad w/ space)
    s = _URLDOI_RE.sub("", s)                     # drop url/DOI (underscore landmines)
    for k, v in _ENTITIES.items():
        s = s.replace(k, v)
    for k, v in _UNICODE.items():
        s = s.replace(k, v)
    return re.sub(r"[ \t]{2,}", " ", s)          # collapse spaces the strip introduced


def minimal_entry(stem: str, entry: dict) -> str:
    """A bare @article built ONLY from manifest metadata; unknowns left blank.

    The current manifest schema carries title and year (and may carry author /
    journal); anything absent is emitted as an empty field, never guessed.
    """
    def field(name: str, value: str) -> str:
        return f"  {name} = {{{(value or '').strip()}}},"

    lines = [
        f"@article{{{stem},",
        field("title", entry.get("title", "")),
        field("author", entry.get("author", "")),
        field("year", entry.get("year", "")),
        field("journal", entry.get("journal", "")),
        "}",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# selection / output
# --------------------------------------------------------------------------- #
def select_entries(manifest: dict, project: str | None) -> list[str]:
    stems = []
    for stem, entry in manifest.get("entries", {}).items():
        if project and project not in entry.get("projects", []):
            continue
        # Novelty-screen papers are the 2024-26 prior-art corpus (see neubrain/
        # AGENTS.md, "Library superset of bibliography"): kept in the library but
        # NEVER citeable, so they are excluded from references.bib entirely. This
        # is belt-and-suspenders — BibTeX already omits uncited entries — and keeps
        # the .bib to citeable papers only.
        if entry.get("role") == "novelty_screen":
            continue
        stems.append(stem)
    return sorted(stems)


def novelty_screen_stems(manifest: dict, project: str | None) -> list[str]:
    """Stems excluded from the .bib because role == novelty_screen (for reporting)."""
    return sorted(
        stem for stem, entry in manifest.get("entries", {}).items()
        if (not project or project in entry.get("projects", []))
        and entry.get("role") == "novelty_screen"
    )


def default_out(vault: Path, project: str | None) -> Path:
    if project:
        return vault / "projects" / project / "references.bib"
    return vault / "references.bib"


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="Build references.bib from the neubrain manifest.")
    ap.add_argument("--vault", required=True, type=Path, help="neubrain vault root")
    ap.add_argument("--project", default=None,
                    help="restrict to papers whose manifest 'projects' contains this name")
    ap.add_argument("--out", default=None, type=Path,
                    help="output .bib path (default: projects/<project>/references.bib, "
                         "else <vault>/references.bib)")
    ap.add_argument("--email", default=DEFAULT_EMAIL,
                    help="contact email placed in the polite Crossref User-Agent")
    args = ap.parse_args()

    library = args.vault / "_library"
    if not (library / "manifest.json").exists():
        sys.exit(f"no manifest under {library} — is this the vault root?")

    manifest = load_manifest(library)
    stems = select_entries(manifest, args.project)
    excluded = novelty_screen_stems(manifest, args.project)
    if excluded:
        print(f"excluding {len(excluded)} novelty_screen paper(s) from the .bib: "
              f"{', '.join(excluded)}")
    if not stems:
        scope = f" for project '{args.project}'" if args.project else ""
        print(f"no entries to build{scope}.")
        return 0

    out = args.out or default_out(args.vault, args.project)

    session = requests.Session()
    session.headers["User-Agent"] = f"neuresearch/1.0 (mailto:{args.email})"

    blocks: list[str] = []
    n_crossref = n_minimal = n_skipped = 0
    for stem in stems:
        entry = manifest["entries"][stem]
        doi = (entry.get("doi") or "").strip()
        block: str | None = None
        if doi:
            time.sleep(POLITE_DELAY)
            try:
                bib = crossref_bibtex(doi, session)
            except requests.RequestException as e:
                bib = None
                print(f"[warn] {stem}: Crossref error ({e}); falling back to minimal", file=sys.stderr)
            if bib:
                block = rekey(bib, stem)
                n_crossref += 1
                print(f"[crossref] {stem}  <-  {doi}")
            else:
                # known to us (we have a DOI + metadata) but Crossref gave nothing:
                # emit minimal from manifest data rather than drop a real paper
                block = minimal_entry(stem, entry)
                n_minimal += 1
                print(f"[minimal ] {stem}  (Crossref had no BibTeX for {doi})")
        else:
            block = minimal_entry(stem, entry)
            n_minimal += 1
            print(f"[minimal ] {stem}  (no DOI)")

        if block:
            blocks.append(latex_sanitize(block).rstrip())
        else:
            n_skipped += 1
            print(f"[skip    ] {stem}")

    header = (f"% references.bib — generated by build_bib.py from the neubrain manifest\n"
              f"% project: {args.project or 'ALL (master)'} | {len(blocks)} entries | "
              f"do not hand-edit, regenerate instead\n\n")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(header + "\n\n".join(blocks) + "\n")

    print(f"\n{len(blocks)} written -> {out}")
    print(f"  {n_crossref} via Crossref, {n_minimal} minimal, {n_skipped} skipped.")

    # eyeball the first few entries
    preview = "\n\n".join(blocks[:3])
    print("\n--- first entries (eyeball the format) " + "-" * 30)
    print(preview)
    print("-" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
