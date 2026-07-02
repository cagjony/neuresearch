#!/usr/bin/env python3
r"""
reconcile_citations.py
======================
Wire the citations in a project's plan (or draft) to the neubrain library, so an
informal `[Author Year]` plan can become a `[@stem]` manuscript that pandoc/CSL
can resolve — without ever guessing a citekey or inventing a match.

    python reconcile_citations.py --vault /path/to/neubrain --project astro_atp [--apply]
    python reconcile_citations.py --vault ... --project astro_atp --manuscript      # .tex
    python reconcile_citations.py --vault ... --project theta-pac --manuscript-md   # .md

WHAT IT READS (markdown plan, default):
    projects/<project>/plan.md, INCLUDING its trailing "## References" section.
    From the body it pulls in-text citations (author-year tokens inside [...],
    bare DOIs); from the reference list it pulls each entry's first author, year,
    DOI, and title. The two are joined on (surname, year).

WHAT IT READS (--manuscript-md, a Markdown draft):
    projects/<project>/manuscript.md — same shape as a plan (author-year tokens in
    [...] + a trailing "## References" list), for projects that draft in Markdown and
    have no separate plan.md. Report-only -> manuscript-citation-reconcile.md; the
    MISSING list IS the fetch list (each carries the reference's DOI).

WHAT IT READS (--manuscript, a LaTeX draft):
    projects/<project>/manuscript.tex. In-text \cite/\citep/\citet keys (counted)
    and the \begin{thebibliography} list. Each cited work is keyed by its LaTeX
    cite key — which is meant to BE the library stem — so the strongest match is an
    exact cite-key == stem hit; \bibitem author/year/DOI provide the fallback.
    Report only (no --apply): swapping thebibliography → \bibliography{references.bib}
    is a manual step done once every cite key resolves.

HOW IT MATCHES each citation to a library paper (manifest = source of truth):
    1. by DOI            — the ref entry's DOI, normalized, found in the manifest.
    2. by author + year  — the manifest stem IS surname+year (e.g. fujii2017), so
       a (surname, year) hit is a strong candidate; a lone candidate is accepted,
       several is reported AMBIGUOUS.
    Anything else is MISSING (a fetch candidate for papers.txt / suggest.py).

REPORT-ONLY by default -> projects/<project>/citation-reconcile.md:
    MATCHED   plan citation -> [@stem]            (confident: wire these)
    MISSING   cited in plan, NOT in the library   (DOI/title -> go fetch)
    AMBIGUOUS weak / multi-candidate match        (you confirm before wiring)

With --apply: rewrite plan.md in place, converting ONLY confident matches to
[@stem]; missing/ambiguous citations are left as written but flagged with a ⚠ so
nothing is silently mis-cited. (Read the report first; run --apply after.)
--apply REFUSES unless plan.md is committed and clean in git: git IS the backup,
so `git checkout -- plan.md` is the one-step undo for a rewrite you dislike. No
separate .bak is kept.

Requires: Python 3.10+ (standard library only).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

# import sibling helpers regardless of CWD
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_papers import load_manifest  # noqa: E402

DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>)\]}]+", re.I)
STEM_RE = re.compile(r"^([a-z]+)(\d{4})([a-z]?)$")
# an author-year token: capitalized name word(s) then a 4-digit year (opt. a/b suffix)
AUTHOR_YEAR_RE = re.compile(
    r"^\s*([A-Za-zÀ-ɏ][A-Za-zÀ-ɏ'’.\-]*"
    r"(?:\s+(?:and|&|et\s+al\.?|[A-Za-zÀ-ɏ][A-Za-zÀ-ɏ'’.\-]*))*?)"
    r"\s+(\d{4})[a-z]?\s*$"
)
BRACKET_RE = re.compile(r"\[([^\[\]]+)\]")
REFS_HEADING_RE = re.compile(r"^#{1,6}\s*references\b", re.I | re.M)


# --------------------------------------------------------------------------- #
# normalization
# --------------------------------------------------------------------------- #
def strip_diacritics(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def norm_surname(name: str) -> str:
    """First alphabetic word, de-accented, lowercased — matches the stem convention
    (fetch_papers builds a stem from the first author's first name token)."""
    m = re.search(r"[A-Za-zÀ-ɏ]+", name)
    return strip_diacritics(m.group(0)).lower() if m else ""


def norm_doi(doi: str | None) -> str:
    if not doi:
        return ""
    return doi.strip().rstrip(".").lower()


def title_tokens(title: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{4,}", strip_diacritics(title or "").lower())}


# --------------------------------------------------------------------------- #
# library index (from the manifest)
# --------------------------------------------------------------------------- #
class Library:
    def __init__(self, manifest: dict):
        self.entries = manifest.get("entries", {})
        self.doi2stem: dict[str, str] = {}
        self.ay2stems: dict[tuple[str, str], list[str]] = {}
        for key, stem in manifest.get("by_id", {}).items():
            if key.startswith("10."):
                self.doi2stem[norm_doi(key)] = stem
        for stem, entry in self.entries.items():
            d = norm_doi(entry.get("doi"))
            if d:
                self.doi2stem.setdefault(d, stem)
            m = STEM_RE.match(stem)
            if m:
                self.ay2stems.setdefault((m.group(1), m.group(2)), []).append(stem)

    def title_for(self, stem: str) -> str:
        return self.entries.get(stem, {}).get("title", "")


# --------------------------------------------------------------------------- #
# plan parsing
# --------------------------------------------------------------------------- #
class Citation:
    """One distinct cited work, keyed by (surname, year), enriched from the ref list."""
    def __init__(self, surname: str, year: str, display: str):
        self.surname = surname
        self.year = year
        self.display = display          # e.g. "Fujii 2017" for the report
        self.key: str | None = None     # LaTeX \bibitem/\cite key, when reconciling a .tex
        self.doi: str | None = None     # from the reference list, if present
        self.title: str = ""            # from the reference list, if present
        self.in_reflist = False
        self.intext = 0                 # in-text occurrences
        self.unverified = False         # ref entry carried an "[Unable to verify]" flag
        # classification, filled later
        self.status = ""                # MATCHED | MISSING | AMBIGUOUS
        self.stem: str | None = None
        self.method = ""
        self.note = ""


def split_plan(text: str) -> tuple[str, str]:
    """Return (body, reference_section_text). Reference section starts at the last
    '## References' heading; empty string if there is none."""
    matches = list(REFS_HEADING_RE.finditer(text))
    if not matches:
        return text, ""
    cut = matches[-1]
    return text[: cut.start()], text[cut.end():]


def parse_reflist(ref_text: str) -> list[dict]:
    """Each blank-line-separated block -> {surname, year, doi, title, unverified}."""
    out = []
    for block in re.split(r"\n\s*\n", ref_text):
        block = block.strip()
        if not block:
            continue
        unverified = "unable to verify" in block.lower()
        # drop the flag line(s) so they do not pollute author/title parsing
        lines = [ln for ln in block.splitlines() if "unable to verify" not in ln.lower()]
        joined = " ".join(lines).strip()
        if not joined:
            continue
        ym = re.search(r"\((\d{4})[a-z]?\)", joined)
        year = ym.group(1) if ym else ""
        doim = DOI_RE.search(joined)
        doi = doim.group(0).rstrip(".") if doim else None
        surname = norm_surname(joined)
        # title = sentence after the (year). — up to the next period, best-effort
        title = ""
        if ym:
            after = joined[ym.end():].lstrip(" .")
            tm = re.match(r"([^.]+)\.", after)
            title = tm.group(1).strip() if tm else after.split(".")[0].strip()
        out.append({"surname": surname, "year": year, "doi": doi,
                    "title": title, "unverified": unverified})
    return out


def looks_like_citation_group(content: str) -> bool:
    """True if a [...] group holds citation tokens (author-year or DOI), not math/ranges."""
    parts = [p.rstrip(" ⚠").strip() for p in content.split(";")]
    return any(AUTHOR_YEAR_RE.match(p) or DOI_RE.search(p) for p in parts)


def parse_intext(body: str) -> dict[tuple[str, str], int]:
    """(surname, year) -> occurrence count, from author-year tokens inside [...]."""
    counts: dict[tuple[str, str], int] = {}
    for m in BRACKET_RE.finditer(body):
        content = m.group(1)
        if not looks_like_citation_group(content):
            continue
        for part in content.split(";"):
            am = AUTHOR_YEAR_RE.match(part.rstrip(" ⚠").strip())
            if am:
                key = (norm_surname(am.group(1)), am.group(2))
                if key[0] and key[1]:
                    counts[key] = counts.get(key, 0) + 1
    return counts


# --------------------------------------------------------------------------- #
# LaTeX manuscript parsing (--manuscript)
# --------------------------------------------------------------------------- #
CITE_RE = re.compile(r"\\cite[tp]?\*?(?:\[[^\]]*\])*\{([^}]*)\}")
BIBITEM_RE = re.compile(
    r"\\bibitem(?:\[[^\]]*\])?\{([^}]*)\}(.*?)"
    r"(?=\\bibitem|\\end\{thebibliography\})", re.S)
YEAR_RE = re.compile(r"\b(1[89]\d{2}|20\d{2})\b")


def strip_latex(s: str) -> str:
    """Best-effort de-TeX for author/title parsing: accents, braces, commands."""
    s = re.sub(r"\\[`'^\"~=.]\{?([A-Za-z])\}?", r"\1", s)   # \^e \`a \'{e} -> e a e
    s = re.sub(r"\\emph\{([^}]*)\}", r"\1", s)
    s = re.sub(r"\\[A-Za-z]+\*?", " ", s)                    # drop remaining commands
    s = s.replace("~", " ").replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", s).strip()


def latex_first_surname(authors: str) -> str:
    """First author's surname from a '\\bibitem' author list ('F.M.~Surname, ...').
    Drops leading initials so 'M.B.~Ahrens' -> 'ahrens', 'W.~M\\^eme' -> 'meme'."""
    first = strip_latex(authors.split(",")[0])
    tokens = [t for t in first.split()
              if not re.fullmatch(r"[A-Z]\.?(?:[A-Z]\.?)*", t)]
    return norm_surname(" ".join(tokens) if tokens else first)


def parse_tex_cites(text: str) -> dict[str, int]:
    """cite key -> in-text occurrence count, from \\cite/\\citep/\\citet groups."""
    counts: dict[str, int] = {}
    for m in CITE_RE.finditer(text):
        for key in m.group(1).split(","):
            key = key.strip()
            if key:
                counts[key] = counts.get(key, 0) + 1
    return counts


def parse_tex_bibitems(text: str) -> dict[str, dict]:
    """cite key -> {surname, year, doi, title} from the \\bibitem list."""
    out: dict[str, dict] = {}
    for m in BIBITEM_RE.finditer(text):
        key = m.group(1).strip()
        block = m.group(2)
        doim = DOI_RE.search(block)
        # publication year = the LAST year in the entry (key year may be stale)
        years = YEAR_RE.findall(block)
        year = years[-1] if years else ""
        em = re.search(r"\\emph\{(.*?)\}", block, re.S)
        title = strip_latex(em.group(1)) if em else ""
        # author list = text before the \emph{title}
        authors = block[: em.start()] if em else block
        out[key] = {"surname": latex_first_surname(authors), "year": year,
                    "doi": doim.group(0).rstrip(".") if doim else None,
                    "title": title}
    return out


def build_tex_citations(cites: dict[str, int],
                        bibitems: dict[str, dict]) -> list[Citation]:
    """One Citation per cite key (key = identity); enriched from its \\bibitem."""
    cits: list[Citation] = []
    for key in sorted(set(cites) | set(bibitems)):
        bib = bibitems.get(key, {})
        c = Citation(bib.get("surname", ""), bib.get("year", ""), key)
        c.key = key
        c.intext = cites.get(key, 0)
        c.in_reflist = key in bibitems
        c.doi = bib.get("doi")
        c.title = bib.get("title", "")
        cits.append(c)
    return cits


# --------------------------------------------------------------------------- #
# matching
# --------------------------------------------------------------------------- #
def classify(cit: Citation, lib: Library) -> None:
    # 0) an exact cite-key == stem hit (LaTeX manuscripts): stem IS the citekey
    if cit.key and cit.key in lib.entries:
        cit.status, cit.stem, cit.method = "MATCHED", cit.key, "key"
        return
    # 1) DOI is the strongest signal
    nd = norm_doi(cit.doi)
    if nd and nd in lib.doi2stem:
        cit.status, cit.stem, cit.method = "MATCHED", lib.doi2stem[nd], "doi"
        return
    # 2) author + year against the stem index
    cands = lib.ay2stems.get((cit.surname, cit.year), [])
    if len(cands) == 1:
        stem = cands[0]
        # if we have both titles, sanity-check the overlap before trusting it
        if cit.title and lib.title_for(stem):
            shared = title_tokens(cit.title) & title_tokens(lib.title_for(stem))
            if not shared:
                cit.status, cit.stem, cit.method = "AMBIGUOUS", stem, "author-year"
                cit.note = "author+year match but no title-word overlap"
                return
        cit.status, cit.stem, cit.method = "MATCHED", stem, "author-year"
        return
    if len(cands) > 1:
        cit.status, cit.method = "AMBIGUOUS", "author-year"
        cit.note = "several library papers share this author+year: " + ", ".join(cands)
        return
    # 3) nothing in the library
    cit.status = "MISSING"


def build_citations(intext: dict[tuple[str, str], int],
                    reflist: list[dict]) -> list[Citation]:
    cits: dict[tuple[str, str], Citation] = {}

    def get(surname: str, year: str, display: str) -> Citation:
        key = (surname, year)
        if key not in cits:
            cits[key] = Citation(surname, year, display)
        return cits[key]

    for ref in reflist:
        if not ref["surname"] or not ref["year"]:
            continue
        disp = f"{ref['surname'].capitalize()} {ref['year']}"
        c = get(ref["surname"], ref["year"], disp)
        c.in_reflist = True
        c.doi = c.doi or ref["doi"]
        c.title = c.title or ref["title"]
        c.unverified = c.unverified or ref["unverified"]

    for (surname, year), n in intext.items():
        c = get(surname, year, f"{surname.capitalize()} {year}")
        c.intext += n

    return sorted(cits.values(), key=lambda c: (c.surname, c.year))


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #
def render_report(project: str, plan_rel: str, lib: Library,
                  cits: list[Citation], n_refs: int) -> str:
    matched = [c for c in cits if c.status == "MATCHED"]
    missing = [c for c in cits if c.status == "MISSING"]
    ambig = [c for c in cits if c.status == "AMBIGUOUS"]
    n_proj = sum(1 for e in lib.entries.values() if project in e.get("projects", []))

    L = []
    L.append(f"# Citation reconcile — {project}")
    L.append("")
    L.append(f"*Generated {datetime.now():%Y-%m-%d %H:%M} by `reconcile_citations.py` "
             f"(report-only).* Re-run with `--apply` to wire the confident matches.")
    L.append("")
    L.append(f"- source: `{plan_rel}`")
    L.append(f"- library: {len(lib.entries)} papers in the manifest "
             f"({n_proj} tagged `{project}`)")
    L.append(f"- distinct citations found: {len(cits)} "
             f"(in-text occurrences + {n_refs} reference-list entries)")
    L.append(f"- **MATCHED {len(matched)} · MISSING {len(missing)} · AMBIGUOUS {len(ambig)}**")
    L.append("")

    def where(c: Citation) -> str:
        bits = []
        if c.intext:
            bits.append(f"in-text ×{c.intext}")
        if c.in_reflist:
            bits.append("ref-list")
        if c.unverified:
            bits.append("⚠ flagged unverified in plan")
        return ", ".join(bits) or "—"

    L.append("## MATCHED — confident, wire to `[@stem]`")
    if matched:
        via_label = {"key": "exact cite-key", "doi": None, "author-year": "author+year"}
        for c in matched:
            via = f"via DOI {c.doi}" if c.method == "doi" else f"via {via_label.get(c.method, c.method)}"
            L.append(f"- `[{c.display}]` → `[@{c.stem}]`  ({via}; {where(c)})")
    else:
        L.append("- (none)")
    L.append("")

    L.append("## MISSING — cited in the plan, NOT in the library")
    L.append("*Fetch candidates: add the DOI to `projects/%s/papers.txt` and re-fetch, "
             "or surface via `suggest.py`.*" % project)
    if missing:
        for c in missing:
            ident = f"DOI {c.doi}" if c.doi else "no DOI in plan"
            title = f" — {c.title}" if c.title else ""
            L.append(f"- `[{c.display}]`{title}  ({ident}; {where(c)})")
    else:
        L.append("- (none)")
    L.append("")

    L.append("## AMBIGUOUS — weak match, confirm before wiring")
    if ambig:
        for c in ambig:
            cand = f" candidate `[@{c.stem}]`" if c.stem else ""
            L.append(f"- `[{c.display}]`{cand} — {c.note}  ({where(c)})")
    else:
        L.append("- (none)")
    L.append("")
    return "\n".join(L)


# --------------------------------------------------------------------------- #
# --apply (rewrite plan body; confident matches only)
# --------------------------------------------------------------------------- #
def apply_to_plan(plan_text: str, cits: list[Citation]) -> tuple[str, int, int]:
    """Convert confident author-year tokens to [@stem]; flag the rest with ⚠.
    Only the body (before '## References') is rewritten; the ref section is left
    intact. Returns (new_text, n_converted, n_flagged)."""
    by_key = {(c.surname, c.year): c for c in cits}
    body, ref_section = split_plan(plan_text)
    # keep the exact heading text we cut on
    heading = ""
    m = list(REFS_HEADING_RE.finditer(plan_text))
    if m:
        heading = plan_text[m[-1].start():m[-1].end()]

    n_conv = n_flag = 0

    def rewrite_group(gm: re.Match) -> str:
        nonlocal n_conv, n_flag
        content = gm.group(1)
        if not looks_like_citation_group(content):
            return gm.group(0)
        new_parts = []
        for part in content.split(";"):
            token = part.strip()
            token_clean = token.rstrip(" ⚠").strip()
            am = AUTHOR_YEAR_RE.match(token_clean)
            if not am:
                new_parts.append(token)
                continue
            key = (norm_surname(am.group(1)), am.group(2))
            c = by_key.get(key)
            if c and c.status == "MATCHED" and c.stem:
                new_parts.append(f"@{c.stem}")
                n_conv += 1
            else:
                new_parts.append(f"{token_clean} ⚠")
                n_flag += 1
        return "[" + "; ".join(new_parts) + "]"

    new_body = BRACKET_RE.sub(rewrite_group, body)
    new_text = new_body + heading + ref_section
    return new_text, n_conv, n_flag


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def plan_is_committed(plan: Path) -> tuple[bool, str]:
    """True iff plan.md is tracked and clean in git — so `git checkout -- plan.md`
    can undo an --apply rewrite. Returns (ok, reason-if-not)."""
    repo = plan.parent
    try:
        inside = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True)
    except FileNotFoundError:
        return False, "git is not on PATH"
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return False, f"{plan} is not inside a git work tree"
    tracked = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "--error-unmatch", plan.name],
        capture_output=True, text=True)
    if tracked.returncode != 0:
        return False, f"{plan} is not tracked by git"
    status = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain", "--", plan.name],
        capture_output=True, text=True)
    if status.stdout.strip():
        return False, f"{plan} has uncommitted changes"
    return True, ""


def main() -> int:
    ap = argparse.ArgumentParser(description="Reconcile a plan's citations against the library.")
    ap.add_argument("--vault", required=True, type=Path, help="neubrain vault root")
    ap.add_argument("--project", required=True, help="project under projects/<name>/")
    ap.add_argument("--apply", action="store_true",
                    help="rewrite plan.md, converting ONLY confident matches to [@stem]")
    ap.add_argument("--manuscript", action="store_true",
                    help="reconcile manuscript.tex (\\cite + \\bibitem) instead of plan.md; "
                         "report-only")
    ap.add_argument("--manuscript-md", action="store_true",
                    help="reconcile manuscript.md (Markdown [Author Year] + ## References) "
                         "instead of plan.md; report-only")
    args = ap.parse_args()

    library_dir = args.vault / "_library"
    if not (library_dir / "manifest.json").exists():
        sys.exit(f"no manifest under {library_dir} — is this the vault root?")
    lib = Library(load_manifest(library_dir))

    if args.manuscript:
        tex = args.vault / "projects" / args.project / "manuscript.tex"
        if not tex.exists():
            sys.exit(f"no manuscript at {tex}")
        text = tex.read_text()
        bibitems = parse_tex_bibitems(text)
        cites = parse_tex_cites(text)
        cits = build_tex_citations(cites, bibitems)
        for c in cits:
            classify(c, lib)
        src_rel = f"projects/{args.project}/manuscript.tex"
        report = render_report(args.project, src_rel, lib, cits, len(bibitems))
        report_path = args.vault / "projects" / args.project / "manuscript-citation-reconcile.md"
        report_path.write_text(report)
        n_m = sum(c.status == "MATCHED" for c in cits)
        n_x = sum(c.status == "MISSING" for c in cits)
        n_a = sum(c.status == "AMBIGUOUS" for c in cits)
        print(f"reconcile {args.project}/manuscript.tex: {len(cits)} cite keys — "
              f"MATCHED {n_m}, MISSING {n_x}, AMBIGUOUS {n_a}")
        print(f"report -> {report_path}")
        if args.apply:
            print("--apply is not supported for --manuscript: swapping thebibliography "
                  "for \\bibliography{references.bib} is a manual step once all keys resolve.",
                  file=sys.stderr)
        return 0

    if args.manuscript_md:
        md = args.vault / "projects" / args.project / "manuscript.md"
        if not md.exists():
            sys.exit(f"no manuscript at {md}")
        md_text = md.read_text()
        body, ref_text = split_plan(md_text)
        reflist = parse_reflist(ref_text)
        intext = parse_intext(body)
        cits = build_citations(intext, reflist)
        for c in cits:
            classify(c, lib)
        src_rel = f"projects/{args.project}/manuscript.md"
        report = render_report(args.project, src_rel, lib, cits, len(reflist))
        report_path = args.vault / "projects" / args.project / "manuscript-citation-reconcile.md"
        report_path.write_text(report)
        n_m = sum(c.status == "MATCHED" for c in cits)
        n_x = sum(c.status == "MISSING" for c in cits)
        n_a = sum(c.status == "AMBIGUOUS" for c in cits)
        print(f"reconcile {args.project}/manuscript.md: {len(cits)} citations — "
              f"MATCHED {n_m}, MISSING {n_x}, AMBIGUOUS {n_a}")
        print(f"report -> {report_path}")
        if args.apply:
            print("--apply is not supported for --manuscript-md (report-only); the "
                  "MISSING list is a fetch list, not a rewrite target.", file=sys.stderr)
        return 0

    plan = args.vault / "projects" / args.project / "plan.md"
    if not plan.exists():
        sys.exit(f"no plan at {plan}")

    plan_text = plan.read_text()
    body, ref_text = split_plan(plan_text)
    reflist = parse_reflist(ref_text)
    intext = parse_intext(body)
    cits = build_citations(intext, reflist)
    for c in cits:
        classify(c, lib)

    plan_rel = f"projects/{args.project}/plan.md"
    report = render_report(args.project, plan_rel, lib, cits, len(reflist))
    report_path = args.vault / "projects" / args.project / "citation-reconcile.md"
    report_path.write_text(report)

    n_m = sum(c.status == "MATCHED" for c in cits)
    n_x = sum(c.status == "MISSING" for c in cits)
    n_a = sum(c.status == "AMBIGUOUS" for c in cits)
    print(f"reconcile {args.project}: {len(cits)} citations — "
          f"MATCHED {n_m}, MISSING {n_x}, AMBIGUOUS {n_a}")
    print(f"report -> {report_path}")

    if args.apply:
        ok, why = plan_is_committed(plan)
        if not ok:
            print(f"--apply REFUSED: {why}.", file=sys.stderr)
            print("Commit plan.md first — git is the backup, so `git checkout -- "
                  f"{plan}` undoes a rewrite you dislike. The report above is "
                  "already written; re-run --apply once plan.md is clean.",
                  file=sys.stderr)
            return 2
        new_text, n_conv, n_flag = apply_to_plan(plan_text, cits)
        if new_text != plan_text:
            plan.write_text(new_text)
            print(f"--apply: rewrote {plan} — {n_conv} converted to [@stem], "
                  f"{n_flag} left flagged ⚠")
        else:
            print("--apply: nothing to convert (no confident in-text matches).")
    else:
        print("report-only (no --apply): plan.md untouched. Read the report, then re-run with --apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
