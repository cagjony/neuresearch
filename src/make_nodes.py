#!/usr/bin/env python3
"""
make_nodes.py  —  a TWO-PHASE lit/ node generator
==================================================
    conda run -n neuresearch python3 src/make_nodes.py propose \
        --vault /path/to/neubrain --project astro_atp
    conda run -n neuresearch python3 src/make_nodes.py wire \
        --vault /path/to/neubrain --project astro_atp

PHASE 1 ("propose"). For every manifest entry tagged with --project this:
  1. writes a literature NODE at lit/<stem>.md  (YAML frontmatter + a short,
     grounded claim summary + machine-owned section markers), and
  2. proposes candidate concepts into concepts/_proposed.md.
Then STOP so a human can edit concepts/_proposed.md.

PHASE 2 ("wire"), run AFTER a human curates concepts/_proposed.md:
  1. creates a minimal stub concepts/<name>.md for each proposed concept
     (existing concept notes are left untouched), and
  2. sets each node's machine-owned ## Concepts section to the [[links]] for
     that paper. Claim summaries and the ## Related marker are never touched.
Both phases are idempotent.

Vault rules it obeys (see <vault>/AGENTS.md):
  - The lit/ node is a SHORT note (metadata + claim summary + links), NEVER a
    conversion of the XML; the XML in _library/ stays the archive.
  - It never fabricates a [[link]] or a summary it cannot ground in the source.
    The claim summary is taken verbatim-ish from the paper's own abstract; if no
    abstract is available (PDF-only entries) the summary is left as an honest
    'pending' marker, not invented.
  - Concept candidates come ONLY from author keywords (<kwd>) actually present in
    the JATS — author-asserted, grounded signal. Indexing taxonomies (PLOS
    subject hierarchies, etc.) are treated as noise and skipped.

No network. No edits to fetch_papers.py, reconcile.py, the manifest, or stems.
Requires: Python 3.10+ (stdlib only).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

# machine-owned section markers — phase 2 / relate.py own everything below these
CONCEPTS_MARKER = "## Concepts"
CONCEPTS_NOTE = "<!-- wired in phase 2 from approved concepts -->"
RELATED_MARKER = "## Related"
RELATED_NOTE = "<!-- machine-owned: regenerated later by relate.py; leave empty -->"

NO_ABSTRACT = "<!-- no abstract available in source; summary pending (do not fabricate) -->"

PROPOSED_HEADER = """# Proposed concepts (phase 1)

<!--
Machine proposal from make_nodes.py 'propose'. Candidates below are author
keywords (<kwd>) extracted from the JATS in _library/ — the only grounded,
author-asserted concept signal available offline. Each line lists the papers
(citekeys) that would use the concept.

This file is YOURS to edit before phase 2: merge near-duplicates, rename to a
canonical phrase, ADD concepts the keywords missed, and delete noise. Phase 2
('wire') will read the approved version of this file; nothing in concepts/ has
been created yet.
-->
"""


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def text_of(el: ET.Element | None) -> str:
    """Flatten an element's text (incl. <sup>, <italic>, ...) and collapse spaces."""
    if el is None:
        return ""
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip()


def first_sentences(text: str, n: int = 3) -> str:
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", text)
    return " ".join(parts[:n]).strip()


def short_title(title: str, max_chars: int = 70) -> str:
    title = title.rstrip(". ")
    if len(title) <= max_chars:
        return title
    cut = title[:max_chars].rsplit(" ", 1)[0]
    return cut + "…"


def author_label(surname: str, stem: str) -> str:
    if surname:
        return surname
    # PDF-only / no XML: derive from the stem (alpha prefix), e.g. stobart2018 -> Stobart
    alpha = re.match(r"[a-zA-Z]+", stem)
    return alpha.group(0).capitalize() if alpha else stem


# --------------------------------------------------------------------------- #
# JATS extraction (grounded, offline)
# --------------------------------------------------------------------------- #
def parse_jats(path: Path) -> dict:
    root = ET.parse(path).getroot()

    at = root.find(".//{*}article-meta//{*}article-title")
    if at is None:
        at = root.find(".//{*}article-title")
    title = text_of(at)

    # first author surname
    surname = ""
    for contrib in root.findall(".//{*}contrib-group//{*}contrib"):
        if contrib.get("contrib-type", "author") != "author":
            continue
        sn = contrib.find(".//{*}surname")
        if sn is not None and text_of(sn):
            surname = text_of(sn)
            break

    # abstract: prefer a plain <abstract> over typed ones (PLOS 'author summary')
    abstracts = root.findall(".//{*}article-meta//{*}abstract") or root.findall(".//{*}abstract")
    chosen = None
    for ab in abstracts:
        if ab.get("abstract-type") is None:
            chosen = ab
            break
    if chosen is None and abstracts:
        chosen = abstracts[0]
    if chosen is not None:
        paras = [text_of(p) for p in chosen.findall(".//{*}p")]
        abstract = " ".join(t for t in paras if t) or text_of(chosen)
    else:
        abstract = ""

    # full reference list: every cited DOI, dedup case-insensitively, order kept
    cited, seen = [], set()
    for pid in root.findall(".//{*}ref-list//{*}pub-id"):
        if pid.get("pub-id-type") == "doi":
            doi = text_of(pid)
            if doi and doi.lower() not in seen:
                seen.add(doi.lower())
                cited.append(doi)

    # author keywords only (grounded concept signal)
    keywords = []
    for kw in root.findall(".//{*}kwd-group//{*}kwd"):
        t = text_of(kw)
        if t:
            keywords.append(t)

    return {"title": title, "surname": surname, "abstract": abstract,
            "cited_dois": cited, "keywords": keywords}


# --------------------------------------------------------------------------- #
# node file: build + idempotent write
# --------------------------------------------------------------------------- #
def _yaml_scalar(v: str) -> str:
    return '"' + str(v).replace('"', '\\"') + '"'


def build_frontmatter(stem: str, doi: str, year: str, authors: str, source: str,
                      refs_source: str, projects: list[str], cited_dois: list[str]) -> str:
    doi_val = _yaml_scalar(doi) if doi else '""'
    year_val = _yaml_scalar(year) if year else '""'
    authors_val = _yaml_scalar(authors) if authors else '""'
    lines = ["---",
             f"citekey: {stem}",
             f"doi: {doi_val}",
             f"year: {year_val}",
             # plain first-author field so Dataview/library.md can show a column
             f"authors: {authors_val}",
             f"source: {source}",
             f"refs_source: {refs_source}"]
    lines.append("projects:" if projects else "projects: []")
    for p in projects:
        lines.append(f"  - {p}")
    if cited_dois:
        lines.append("cited_dois:")
        lines += [f"  - {_yaml_scalar(d)}" for d in cited_dois]
    else:
        lines.append("cited_dois: []")
    lines.append("---")
    return "\n".join(lines)


def split_frontmatter(text: str) -> tuple[str, str]:
    """Return (frontmatter_block, rest). frontmatter_block is '' if absent.

    The closing '---' fence is included in the block but the trailing newline is
    NOT consumed, so `rest` keeps the blank line/body separator. This makes
    `frontmatter + rest` round-trip cleanly (both new nodes and refreshes put
    exactly one newline after the closing fence).
    """
    if not text.startswith("---"):
        return "", text
    m = re.match(r"^---\n.*?\n---", text, re.DOTALL)
    if not m:
        return "", text
    return m.group(0), text[m.end():]


def new_node_body(label: str, year: str, title: str, abstract: str) -> str:
    summary = first_sentences(abstract) if abstract else NO_ABSTRACT
    return (f"\n# {label} {year} — {short_title(title)}\n\n"
            f"{summary}\n\n"
            f"{CONCEPTS_MARKER}\n{CONCEPTS_NOTE}\n\n"
            f"{RELATED_MARKER}\n{RELATED_NOTE}\n")


def write_node(lit: Path, stem: str, frontmatter: str, label: str, year: str,
               title: str, abstract: str) -> str:
    """Write/refresh lit/<stem>.md idempotently. Returns 'new' or 'refreshed'."""
    path = lit / f"{stem}.md"
    if path.exists():
        # refresh ONLY the frontmatter; preserve the human-written body verbatim
        _, body = split_frontmatter(path.read_text())
        path.write_text(frontmatter + body)
        return "refreshed"
    path.write_text(frontmatter + new_node_body(label, year, title, abstract))
    return "new"


# --------------------------------------------------------------------------- #
# concept proposal
# --------------------------------------------------------------------------- #
def render_proposed(concept_to_papers: dict[str, list[str]]) -> str:
    # sort by #papers desc, then concept name
    items = sorted(concept_to_papers.items(), key=lambda kv: (-len(kv[1]), kv[0].lower()))
    lines = [PROPOSED_HEADER]
    if not items:
        lines.append("_No author keywords were present in any tagged paper's JATS; "
                     "add concepts here by hand before phase 2._\n")
    for concept, papers in items:
        lines.append(f"- [[{concept}]]  <- {', '.join(sorted(set(papers)))}")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# concept wiring (phase 2)
# --------------------------------------------------------------------------- #
def parse_proposed(path: Path) -> list[tuple[str, list[str]]]:
    """Parse '- [[concept]]  <- stemA, stemB' lines from concepts/_proposed.md."""
    out = []
    for line in path.read_text().splitlines():
        m = re.match(r"^-\s*\[\[(.+?)\]\]\s*<-\s*(.+?)\s*$", line)
        if not m:
            continue
        concept = m.group(1).strip()
        stems = [s.strip() for s in m.group(2).split(",") if s.strip()]
        out.append((concept, stems))
    return out


def write_concept_stub(concepts_dir: Path, name: str) -> bool:
    """Create concepts/<name>.md (title + empty body) if missing. True if created.

    Idempotent: an existing concept note is left untouched (it may have human text).
    """
    path = concepts_dir / f"{name}.md"
    if path.exists():
        return False
    path.write_text(f"# {name}\n")
    return True


def set_concepts_section(text: str, concepts: list[str]) -> str:
    """Replace a node's machine-owned ## Concepts section; leave summary + ## Related alone."""
    body = "\n".join(f"- [[{c}]]" for c in concepts) if concepts else CONCEPTS_NOTE
    block = f"{CONCEPTS_MARKER}\n{body}\n\n{RELATED_MARKER}"
    pattern = re.escape(CONCEPTS_MARKER) + r"\n.*?\n" + re.escape(RELATED_MARKER)
    new, n = re.subn(pattern, lambda _m: block, text, count=1, flags=re.DOTALL)
    return new if n else text


# --------------------------------------------------------------------------- #
# main + phase dispatch
# --------------------------------------------------------------------------- #
def _load(args) -> tuple[Path, dict, dict, Path, Path]:
    library = args.vault / "_library"
    if not (library / "manifest.json").exists():
        sys.exit(f"no manifest under {library} — is this the vault root?")
    manifest = json.loads((library / "manifest.json").read_text())
    entries = {s: e for s, e in manifest.get("entries", {}).items()
               if args.project in e.get("projects", [])}
    return library, manifest, entries, args.vault / "lit", args.vault / "concepts"


def do_propose(args) -> int:
    library, manifest, entries, lit, concepts_dir = _load(args)
    if not entries:
        print(f"no papers tagged with project '{args.project}'."); return 0
    lit.mkdir(parents=True, exist_ok=True)
    concepts_dir.mkdir(parents=True, exist_ok=True)

    n_new = n_refreshed = 0
    concept_to_papers: dict[str, list[str]] = {}      # display-form concept -> [stems]
    concept_canon: dict[str, str] = {}                # casefold -> display form (first seen)

    for stem in sorted(entries):
        entry = entries[stem]
        files = entry.get("files", [])
        xmlf = next((f for f in files if f.endswith(".xml")), None)
        if xmlf and (library / xmlf).exists():
            data = parse_jats(library / xmlf)
            refs_source = "jats"   # cited DOIs (if any) came from the JATS <ref-list>
        else:
            # PDF-only / non-JATS: metadata only, no grounded abstract offline
            data = {"title": entry.get("title", ""), "surname": "",
                    "abstract": "", "cited_dois": [], "keywords": []}
            refs_source = "none"   # no JATS; Crossref/GROBID fallback not yet implemented

        year = entry.get("year", "")
        label = author_label(data["surname"], stem)
        fm = build_frontmatter(stem, entry.get("doi", ""), year, label,
                               entry.get("source_of_fulltext", ""), refs_source,
                               entry.get("projects", []), data["cited_dois"])
        status = write_node(lit, stem, fm, label, year, data["title"], data["abstract"])
        n_new += status == "new"
        n_refreshed += status == "refreshed"
        for kw in data["keywords"]:
            disp = concept_canon.setdefault(kw.casefold(), kw)
            concept_to_papers.setdefault(disp, []).append(stem)

    # _proposed.md is human-curated after first generation — NEVER clobber it on a
    # re-run (e.g. a frontmatter refresh). Write only if it does not exist yet.
    proposed_path = concepts_dir / "_proposed.md"
    if proposed_path.exists():
        proposed_state = f"preserved existing {proposed_path.name} (delete it to regenerate)"
    else:
        proposed_path.write_text(render_proposed(concept_to_papers))
        proposed_state = f"wrote {proposed_path.name} ({len(concept_to_papers)} candidate concepts)"

    print(f"propose: {n_new} nodes written, {n_refreshed} refreshed; {proposed_state}.")
    print(f"  nodes      -> {lit}/<stem>.md ({len(entries)} papers tagged '{args.project}')")
    print(f"  proposals  -> {proposed_path}")
    print("STOP: phase 1 complete. Edit concepts/_proposed.md, then run phase 2 ('wire').")
    return 0


def do_wire(args) -> int:
    library, manifest, entries, lit, concepts_dir = _load(args)
    proposed_path = concepts_dir / "_proposed.md"
    if not proposed_path.exists():
        sys.exit(f"no {proposed_path} — run 'propose' (phase 1) first")
    concepts_dir.mkdir(parents=True, exist_ok=True)

    proposals = parse_proposed(proposed_path)
    n_concepts_new = 0
    stem_to_concepts: dict[str, list[str]] = {}
    for concept, stems in proposals:
        if "/" in concept:
            print(f"[SKIP]  '{concept}' contains '/', not a safe filename"); continue
        n_concepts_new += write_concept_stub(concepts_dir, concept)
        for s in stems:
            stem_to_concepts.setdefault(s, []).append(concept)

    n_wired = 0
    for stem in sorted(entries):
        path = lit / f"{stem}.md"
        if not path.exists():
            print(f"[MISS]  no node lit/{stem}.md to wire"); continue
        text = path.read_text()
        new = set_concepts_section(text, stem_to_concepts.get(stem, []))
        if new != text:
            path.write_text(new)
        n_wired += 1

    # citekeys named in the proposal that are not nodes in this project -> flag,
    # never invent a node or a link for them
    for s in sorted(set(stem_to_concepts) - set(entries)):
        print(f"[WARN]  proposal references '{s}', not a node in project "
              f"'{args.project}' — skipped")

    print(f"wire: {len(proposals)} concepts "
          f"({n_concepts_new} stubs created, {len(proposals) - n_concepts_new} existed); "
          f"{n_wired} nodes wired.")
    print(f"  concepts -> {concepts_dir}/<name>.md")
    print(f"  nodes    -> {lit}/<stem>.md  (## Concepts sections set; summaries + ## Related untouched)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Two-phase lit/ node generator.")
    ap.add_argument("phase", choices=["propose", "wire"],
                    help="propose = phase 1 (nodes + concept proposals); "
                         "wire = phase 2 (create concept stubs + link them into nodes)")
    ap.add_argument("--vault", required=True, type=Path, help="neubrain vault root")
    ap.add_argument("--project", required=True, help="project whose tagged papers to process")
    args = ap.parse_args()
    return do_propose(args) if args.phase == "propose" else do_wire(args)


if __name__ == "__main__":
    raise SystemExit(main())
