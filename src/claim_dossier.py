#!/usr/bin/env python3
"""Marshal manuscript claims and source text for human citation auditing.

The tool deliberately does not adjudicate support.  It emits one dossier entry
per manuscript citation occurrence and leaves the VERDICT column empty.  Body
text loading, reference removal, sentence splitting, citation detection, and
discard counts are reused from ``coding_dossier`` so the two audits share the
same contamination barrier.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import coding_dossier as coding


REQUIRED_TARGET_COLUMNS = ["citekey", "n_citations", "has_text"]
CITEKEY_RE = re.compile(r"@([A-Za-z0-9][A-Za-z0-9_.:-]*)")
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
METHODS_HEADING_RE = re.compile(
    r"^\s*(?:\d+(?:\.\d+)*[.)]?\s*)?"
    r"(?:materials?\s+(?:and|&)\s+methods?|methods?|methodology|"
    r"experimental\s+procedures?)\s*$",
    re.IGNORECASE,
)
SECTION_END_RE = re.compile(
    r"^\s*(?:\d+(?:\.\d+)*[.)]?\s*)?"
    r"(?:results?|discussion|conclusions?|references|bibliography|"
    r"literature\s+cited|acknowledg(?:e)?ments?|supplementary\s+materials?)\s*$",
    re.IGNORECASE,
)

ASSAY_RE = re.compile(
    r"\b(?:assays?|instruments?|tests?|battery|UPSIT|B[- ]?SIT|SIT[- ]?12|TDI|"
    r"Sniffin(?:g)?[’']?\s+Sticks|threshold|identification|discrimination|"
    r"detection|buried[- ](?:food|pellet)|habituation|dishabituation|go/no-go|"
    r"odou?r(?:ants?)?|olfactory|stimuli?|stimulation|olfactometer|record(?:ed|ing|ings)?|"
    r"electrodes?|LFP|EEG|ERP|OERP|fMRI|MRI|PET|imaging|cohorts?|participants?|"
    r"patients?|mice|mouse|rats?|tissue|histology|immunohistochemistry|ELISA|"
    r"sequencing|PCR|spectroscopy|biomarkers?)\b",
    re.IGNORECASE,
)

STOPWORDS = {
    "about", "above", "after", "again", "against", "all", "also", "although", "among",
    "and", "another", "any", "are", "because", "been", "before", "being", "between",
    "both", "but", "can", "could", "did", "does", "doing", "during", "each", "few",
    "for", "from", "further", "had", "has", "have", "having", "here", "how", "into",
    "its", "itself", "may", "more", "most", "not", "now", "only", "other", "our",
    "out", "over", "same", "should", "some", "such", "than", "that", "the", "their",
    "them", "then", "there", "these", "they", "this", "those", "through", "under",
    "using", "very", "was", "were", "what", "when", "where", "which", "while", "who",
    "will", "with", "within", "without", "would", "yet", "your", "study", "studies",
    "paper", "papers", "result", "results", "show", "shown", "found", "reported",
}
SHORT_SCIENCE_TERMS = {"ad", "aβ", "lfp", "eeg", "erp", "pet", "mri", "csf", "mci"}


@dataclass(frozen=True)
class Target:
    citekey: str
    n_citations: int
    has_text: str


@dataclass(frozen=True)
class ClaimInstance:
    citekey: str
    claim: str
    section: str
    manuscript_order: int


@dataclass
class PaperContext:
    citekey: str
    title: str
    text_status: str
    no_text_reason: str
    abstract: str
    methods: str
    methods_source: str
    body_sentences: list[str]
    discarded_reference_matches: int
    discarded_citation_matches: int

    @property
    def discarded_matches(self) -> int:
        return self.discarded_reference_matches + self.discarded_citation_matches


@dataclass(frozen=True)
class EvidenceMatch:
    sentence: str
    overlap_terms: tuple[str, ...]


@dataclass
class DossierEntry:
    number: int
    instance_number: int
    instance_total: int
    claim: ClaimInstance
    paper: PaperContext
    evidence: list[EvidenceMatch]


def load_targets(path: Path) -> list[Target]:
    try:
        handle = path.open(newline="", encoding="utf-8-sig")
    except OSError as error:
        raise RuntimeError(f"cannot open targets TSV {path}: {error}") from None
    with handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise RuntimeError(f"targets TSV has no header: {path}")
        missing = [name for name in REQUIRED_TARGET_COLUMNS if name not in reader.fieldnames]
        if missing:
            raise RuntimeError(f"targets TSV missing required column(s): {', '.join(missing)}")
        targets = []
        seen = set()
        for line_number, row in enumerate(reader, start=2):
            if None in row or any(row.get(name) is None for name in reader.fieldnames):
                raise RuntimeError(f"malformed targets TSV row {line_number}: wrong number of fields")
            citekey = row["citekey"].strip()
            if not citekey:
                raise RuntimeError(f"malformed targets TSV row {line_number}: empty citekey")
            if citekey in seen:
                raise RuntimeError(f"duplicate citekey in targets TSV: {citekey}")
            try:
                n_citations = int(row["n_citations"])
            except ValueError:
                raise RuntimeError(
                    f"malformed targets TSV row {line_number}: n_citations is not an integer"
                ) from None
            if n_citations < 1:
                raise RuntimeError(
                    f"malformed targets TSV row {line_number}: n_citations must be positive"
                )
            has_text = row["has_text"].strip()
            if not has_text:
                raise RuntimeError(f"malformed targets TSV row {line_number}: empty has_text")
            seen.add(citekey)
            targets.append(Target(citekey, n_citations, has_text))
    return targets


def load_manifest_titles(vault: Path, citekeys: set[str]) -> tuple[dict[str, str], dict[str, list[str]]]:
    path = vault / "_library" / "manifest.json"
    try:
        manifest = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"cannot read manifest {path}: {error}") from None
    entries = manifest.get("entries")
    if not isinstance(entries, dict):
        raise RuntimeError(f"manifest has no entries object: {path}")
    titles = {}
    files = {}
    for citekey in citekeys:
        entry = entries.get(citekey)
        if not isinstance(entry, dict):
            raise RuntimeError(f"target citekey absent from manifest: {citekey}")
        title = str(entry.get("title") or "").strip()
        if not title:
            raise RuntimeError(f"manifest entry has no title: {citekey}")
        entry_files = entry.get("files", [])
        if not isinstance(entry_files, list):
            raise RuntimeError(f"manifest entry has invalid files list: {citekey}")
        titles[citekey] = title
        files[citekey] = [str(name) for name in entry_files]
    return titles, files


def _clean_heading(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def manuscript_claims(path: Path, target_keys: set[str]) -> list[ClaimInstance]:
    try:
        text = path.read_text()
    except OSError as error:
        raise RuntimeError(f"cannot read manuscript {path}: {error}") from None
    text = HTML_COMMENT_RE.sub("", text)

    hierarchy: dict[int, str] = {}
    paragraph_lines: list[str] = []
    claims: list[ClaimInstance] = []
    order = 0
    in_fence = False

    def section_path() -> str:
        return " › ".join(hierarchy[level] for level in sorted(hierarchy)) or "(before first heading)"

    def flush() -> None:
        nonlocal order
        if not paragraph_lines:
            return
        paragraph = re.sub(r"\s+", " ", " ".join(paragraph_lines)).strip()
        paragraph_lines.clear()
        if not paragraph:
            return
        for sentence in coding.split_sentences(paragraph):
            cited = [key for key in CITEKEY_RE.findall(sentence) if key in target_keys]
            for citekey in cited:
                order += 1
                claims.append(ClaimInstance(citekey, sentence, section_path(), order))

    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            flush()
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        heading = HEADING_RE.match(line)
        if heading:
            flush()
            level = len(heading.group(1))
            hierarchy[level] = _clean_heading(heading.group(2))
            for deeper in [key for key in hierarchy if key > level]:
                del hierarchy[deeper]
            continue
        if not line.strip():
            flush()
        else:
            paragraph_lines.append(line.strip())
    flush()
    return claims


def validate_claim_counts(claims: list[ClaimInstance], targets: list[Target]) -> None:
    observed = Counter(claim.citekey for claim in claims)
    mismatches = []
    for target in targets:
        if observed[target.citekey] != target.n_citations:
            mismatches.append(
                f"{target.citekey}: targets={target.n_citations}, manuscript={observed[target.citekey]}"
            )
    if mismatches:
        raise RuntimeError("citation-count mismatch after removing comments: " + "; ".join(mismatches))


def _words(text: str) -> list[str]:
    return re.findall(r"\S+", text)


def cap_words(text: str, limit: int) -> str:
    words = _words(re.sub(r"\s+", " ", text).strip())
    if len(words) <= limit:
        return " ".join(words)
    return " ".join(words[:limit]) + " …"


def _without_citation_sentences(text: str) -> str:
    return " ".join(
        sentence for sentence in coding.split_sentences(text)
        if not coding.CITATION_RE.search(sentence)
    )


def _jats_root(path: Path) -> ET.Element:
    try:
        return ET.parse(path).getroot()
    except (OSError, ET.ParseError) as error:
        raise RuntimeError(f"cannot parse XML {path}: {error}") from None


def _jats_abstract(root: ET.Element) -> str:
    for element in root.iter():
        if coding._local_name(element.tag) == "abstract":
            text = coding._flatten_xml(element, mark_citations=True)
            return re.sub(rf"\s*{coding.CITATION_MARKER}\s*", " ", text).strip()
    return "No JATS abstract found."


def _jats_methods(root: ET.Element) -> str | None:
    for section in root.iter():
        if coding._local_name(section.tag) != "sec":
            continue
        title = next(
            (child for child in section if coding._local_name(child.tag) == "title"), None
        )
        if title is None:
            continue
        heading = " ".join(title.itertext()).strip()
        if METHODS_HEADING_RE.match(heading):
            clean = _without_citation_sentences(
                coding._flatten_xml(section, mark_citations=True)
            )
            return clean or None
    return None


def _jats_paragraphs(root: ET.Element) -> list[str]:
    paragraphs = []
    for body in root.iter():
        if coding._local_name(body.tag) not in {"abstract", "body"}:
            continue
        for paragraph in body.iter():
            if coding._local_name(paragraph.tag) != "p":
                continue
            clean = _without_citation_sentences(
                coding._flatten_xml(paragraph, mark_citations=True)
            )
            if clean:
                paragraphs.append(clean)
    return list(dict.fromkeys(paragraphs))


def _plain_methods(body: str) -> str | None:
    lines = body.splitlines()
    start = None
    for index, line in enumerate(lines):
        if METHODS_HEADING_RE.match(line.strip()):
            start = index + 1
            break
    if start is None:
        return None
    end = len(lines)
    for index in range(start, len(lines)):
        if SECTION_END_RE.match(lines[index].strip()):
            end = index
            break
    clean = _without_citation_sentences("\n".join(lines[start:end]))
    return clean or None


def _plain_paragraphs(body: str) -> list[str]:
    paragraphs = []
    for paragraph in re.split(r"\n\s*\n", body):
        clean = _without_citation_sentences(paragraph)
        if clean:
            paragraphs.append(clean)
    return paragraphs


def _fallback_methods(paragraphs: list[str]) -> str:
    ranked = []
    for index, paragraph in enumerate(paragraphs):
        word_count = len(_words(paragraph))
        if word_count < 15:
            continue
        hits = len(ASSAY_RE.findall(paragraph))
        density = hits / math.sqrt(word_count)
        ranked.append((density, hits, -index, index, paragraph))
    if not ranked:
        return "No methods section or assay-dense fallback paragraph found."
    chosen = sorted(ranked, reverse=True)[:2]
    chosen.sort(key=lambda item: item[3])
    return "\n\n".join(item[4] for item in chosen)


def paper_context(
    vault: Path, citekey: str, title: str, manifest_files: list[str]
) -> PaperContext:
    body, references, status = coding.load_full_text(vault, citekey)
    if status == "NO TEXT":
        reason = (
            "NO TEXT HELD — PDF is present, but no .txt or .xml text is held."
            if any(name.lower().endswith(".pdf") for name in manifest_files)
            else "NO TEXT HELD — no .txt or .xml text is held."
        )
        return PaperContext(citekey, title, status, reason, reason, reason, "none", [], 0, 0)

    _coding_evidence, ref_discard, citation_discard = coding.extract_evidence(body, references)
    clean_body_sentences = list(dict.fromkeys(
        sentence for sentence in coding.split_sentences(body)
        if not coding.CITATION_RE.search(sentence)
    ))

    library = vault / "_library"
    if status == "xml":
        root = _jats_root(library / f"{citekey}.xml")
        abstract = _jats_abstract(root)
        methods = _jats_methods(root)
        paragraphs = _jats_paragraphs(root)
        methods_source = "JATS methods section" if methods else "fallback: two assay-dense paragraphs"
    else:
        abstract = cap_words(body, 250)
        methods = _plain_methods(body)
        paragraphs = _plain_paragraphs(body)
        methods_source = "plain-text methods heading" if methods else \
            "fallback: two assay-dense paragraphs"
    if not methods:
        methods = _fallback_methods(paragraphs)

    return PaperContext(
        citekey=citekey,
        title=title,
        text_status=status,
        no_text_reason="",
        abstract=abstract,
        methods=cap_words(methods, 400),
        methods_source=methods_source,
        body_sentences=clean_body_sentences,
        discarded_reference_matches=ref_discard,
        discarded_citation_matches=citation_discard,
    )


def _canonical_term(token: str) -> str:
    term = token.lower().replace("odour", "odor")
    if len(term) > 5 and term.endswith("ies"):
        term = term[:-3] + "y"
    elif len(term) > 5 and term.endswith("s") and not term.endswith(("ss", "is", "us")):
        term = term[:-1]
    return term


def content_terms(text: str) -> set[str]:
    text = re.sub(r"\[[^\]]*@[^\]]+\]", " ", text)
    text = text.replace("β", " beta ").replace("α", " alpha ").replace("ε", " epsilon ")
    text = text.replace("–", "-").replace("—", "-").replace("-", " ")
    terms = set()
    for raw in re.findall(r"[A-Za-z][A-Za-z0-9]*|aβ", text):
        term = _canonical_term(raw)
        if term in STOPWORDS:
            continue
        if len(term) < 3 and term not in SHORT_SCIENCE_TERMS:
            continue
        terms.add(term)
    return terms


def best_evidence(claim: str, sentences: list[str], limit: int = 3) -> list[EvidenceMatch]:
    claim_terms = content_terms(claim)
    ranked = []
    for index, sentence in enumerate(sentences):
        overlap = claim_terms & content_terms(sentence)
        if not overlap:
            continue
        word_count = max(len(_words(sentence)), 1)
        ranked.append((len(overlap), len(overlap) / math.sqrt(word_count), -index,
                       sentence, tuple(sorted(overlap))))
    ranked.sort(reverse=True)
    return [
        EvidenceMatch(cap_words(item[3], 180), item[4]) for item in ranked[:limit]
    ]


def build_entries(
    claims: list[ClaimInstance], contexts: dict[str, PaperContext]
) -> list[DossierEntry]:
    totals = Counter(claim.citekey for claim in claims)
    seen: Counter[str] = Counter()
    entries = []
    for number, claim in enumerate(claims, start=1):
        seen[claim.citekey] += 1
        paper = contexts[claim.citekey]
        evidence = [] if paper.text_status == "NO TEXT" else \
            best_evidence(claim.claim, paper.body_sentences)
        entries.append(DossierEntry(
            number, seen[claim.citekey], totals[claim.citekey], claim, paper, evidence
        ))
    return entries


def _md(text: str) -> str:
    return text.replace("\r", "").strip()


def render_markdown(
    entries: list[DossierEntry], targets: list[Target], manuscript: Path, targets_path: Path
) -> str:
    counts = Counter(entry.claim.citekey for entry in entries)
    contexts = {entry.claim.citekey: entry.paper for entry in entries}
    fewer: dict[str, list[tuple[int, int]]] = {}
    for entry in entries:
        if len(entry.evidence) < 3:
            fewer.setdefault(entry.claim.citekey, []).append((entry.instance_number, len(entry.evidence)))

    lines = [
        "# Claim–evidence dossier",
        "",
        "> Generated by `claim_dossier.py` for human citation review. Entries remain in manuscript ",
        "> order. Source excerpts are marshalled without an automated support decision, and every ",
        "> VERDICT column is intentionally empty.",
        "",
        f"**Targets:** `{targets_path}`  ",
        f"**Manuscript:** `{manuscript}`  ",
        f"**Target papers:** {len(targets)}  ",
        f"**Citation-instance entries:** {len(entries)}  ",
        f"**No-text papers:** {sum(contexts[t.citekey].text_status == 'NO TEXT' for t in targets)}  ",
        f"**Citekeys with at least one instance yielding fewer than 3 evidence sentences:** "
        f"{len(fewer)}",
        "",
        "## Citation-instance count by paper",
        "",
        "| citekey | target count | dossier entries |",
        "|---|---:|---:|",
    ]
    for target in targets:
        lines.append(f"| `{target.citekey}` | {target.n_citations} | {counts[target.citekey]} |")

    lines += [
        "",
        "## Per-paper discarded matches",
        "",
        "Counts reuse `coding_dossier.py`: candidate-pattern matches in removed reference lists and ",
        "in citation-bearing body sentences. They are contamination diagnostics, not claim verdicts.",
        "",
        "| citekey | text | reference-list | citation-bearing body | total discarded |",
        "|---|---:|---:|---:|---:|",
    ]
    for target in targets:
        context = contexts[target.citekey]
        lines.append(
            f"| `{target.citekey}` | {context.text_status} | "
            f"{context.discarded_reference_matches} | {context.discarded_citation_matches} | "
            f"{context.discarded_matches} |"
        )

    lines += ["", "## Fewer than 3 evidence sentences", ""]
    if fewer:
        for target in targets:
            if target.citekey not in fewer:
                continue
            detail = ", ".join(
                f"instance {instance}: {count}" for instance, count in fewer[target.citekey]
            )
            lines.append(f"- `{target.citekey}` — {detail}")
    else:
        lines.append("- none")

    lines += ["", "## Citation-instance dossiers", ""]
    for entry in entries:
        paper = entry.paper
        lines += [
            f"### Entry {entry.number:03d} — {entry.claim.citekey} "
            f"({entry.instance_number}/{entry.instance_total})",
            "",
            f"**Section:** {_md(entry.claim.section)}",
            "",
            "**CLAIM**",
            "",
            f"> {_md(entry.claim.claim)}",
            "",
            "**TITLE**",
            "",
            _md(paper.title),
            "",
            "**ABSTRACT**",
            "",
            _md(paper.abstract),
            "",
            f"**METHODS** ({paper.methods_source})",
            "",
            _md(paper.methods),
            "",
            "**EVIDENCE**",
            "",
        ]
        if paper.text_status == "NO TEXT":
            lines.append(f"- {paper.no_text_reason}")
        elif entry.evidence:
            for index, evidence in enumerate(entry.evidence, start=1):
                terms = ", ".join(evidence.overlap_terms)
                lines.append(f"{index}. **Overlap terms:** {terms}")
                lines.append("")
                lines.append(f"   {_md(evidence.sentence)}")
        else:
            lines.append("- No citation-free body sentence shared a content term with the claim.")
        lines += [
            "",
            f"**Discarded matches:** {paper.discarded_matches} "
            f"(reference-list={paper.discarded_reference_matches}; "
            f"citation-bearing body={paper.discarded_citation_matches})",
            "",
            "| VERDICT |",
            "|---|",
            "| |",
            "",
        ]
    return "\n".join(lines).rstrip() + "\n"


def write_output(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        tmp = Path(handle.name)
        handle.write(content)
    try:
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a claim-evidence dossier for human audit.")
    parser.add_argument("--vault", required=True, type=Path, help="neubrain vault root")
    parser.add_argument("--targets", required=True, type=Path, help="claimcheck target TSV")
    parser.add_argument("--manuscript", required=True, type=Path, help="Markdown manuscript")
    parser.add_argument("--out", required=True, type=Path, help="output dossier path")
    parser.add_argument(
        "--citekey", action="append", nargs="+", metavar="KEY",
        help="restrict to named target citekeys (repeatable)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        targets = load_targets(args.targets)
        if args.citekey:
            requested = {key for group in args.citekey for key in group}
            available = {target.citekey for target in targets}
            unknown = sorted(requested - available)
            if unknown:
                raise RuntimeError(f"citekey(s) absent from targets TSV: {', '.join(unknown)}")
            targets = [target for target in targets if target.citekey in requested]

        target_keys = {target.citekey for target in targets}
        claims = manuscript_claims(args.manuscript, target_keys)
        validate_claim_counts(claims, targets)
        titles, manifest_files = load_manifest_titles(args.vault, target_keys)
        contexts = {
            target.citekey: paper_context(
                args.vault, target.citekey, titles[target.citekey], manifest_files[target.citekey]
            )
            for target in targets
        }
        entries = build_entries(claims, contexts)
        content = render_markdown(entries, targets, args.manuscript, args.targets)
        write_output(args.out, content)
    except RuntimeError as error:
        print(f"claim_dossier: ERROR: {error}", file=sys.stderr)
        return 1

    counts = Counter(entry.claim.citekey for entry in entries)
    fewer = sorted({entry.claim.citekey for entry in entries if len(entry.evidence) < 3})
    print(f"wrote {args.out}")
    print(f"papers={len(targets)} entries={len(entries)} "
          f"no_text={sum(context.text_status == 'NO TEXT' for context in contexts.values())} "
          f"fewer_than_3={len(fewer)}")
    print("entries_per_paper: " + ", ".join(
        f"{target.citekey}:{counts[target.citekey]}" for target in targets
    ))
    print("fewer_than_3: " + (", ".join(fewer) or "none"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
