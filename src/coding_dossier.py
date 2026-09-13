#!/usr/bin/env python3
"""Build a human-review dossier for an authored coding table.

This is deliberately a screen, not a classifier.  It finds body-text sentences
that may bear on species, behavioural construct, and neural-recording codes,
removes reference lists and citation-bearing sentences from consideration, and
flags mechanical mismatches for a second coder to adjudicate.  It never proposes
or writes a replacement code.
"""

from __future__ import annotations

import argparse
import csv
import html
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path


REQUIRED_COLUMNS = [
    "citekey", "species", "design", "construct", "neural",
    "instrument", "evidence", "confidence",
]
MAX_MD_SENTENCES_PER_LABEL = 5
REFERENCE_HEADING_RE = re.compile(
    r"(?im)^\s*(?:\d+(?:\.\d+)*[.)]?\s*)?"
    r"(?:references|bibliography|literature\s+cited)\s*$"
)
CITATION_MARKER = "CODINGDOSSIERCITATION"
CITATION_RE = re.compile(
    rf"{CITATION_MARKER}"
    r"|\bet\s+al\."
    r"|\[(?=[^\]]*\d)[^\]]+\]"
    r"|\((?=[^)]*(?:19|20)\d{2})(?=[^)]*(?:et\s+al\.|[A-Z][A-Za-z'’.-]+))[^)]+\)"
    r"|\b[A-Z][A-Za-z'’.-]+(?:\s+et\s+al\.)?\s*\((?:19|20)\d{2}[a-z]?\)",
    re.IGNORECASE,
)
SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'“‘(])")


@dataclass(frozen=True)
class Evidence:
    dimension: str
    label: str
    term: str
    sentence: str


@dataclass
class PaperResult:
    row: dict[str, str]
    text_status: str
    evidence: list[Evidence] = field(default_factory=list)
    discarded_reference_matches: int = 0
    discarded_citation_matches: int = 0
    no_evidence_fields: list[str] = field(default_factory=list)
    disagreement_fields: list[str] = field(default_factory=list)
    disagreement_details: list[str] = field(default_factory=list)

    @property
    def citekey(self) -> str:
        return self.row["citekey"]

    @property
    def discarded_matches(self) -> int:
        return self.discarded_reference_matches + self.discarded_citation_matches


@dataclass(frozen=True)
class PatternSpec:
    dimension: str
    label: str
    term: str
    pattern: re.Pattern[str]


def _rx(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


PATTERNS = [
    # Species. Specific animal labels remain separate in evidence; comparison
    # folds mouse and rat into the table's authored ``rodent`` category.
    PatternSpec("species", "human", "human cohort", _rx(
        r"\b(?:humans|patients?|participants?|volunteers?)\b"
        r"|\bhuman\s+(?:patients?|participants?|subjects?|volunteers?|cohorts?|adults?)\b"
    )),
    PatternSpec("species", "mouse", "mouse/mice", _rx(r"\b(?:mouse|mice|murine)\b")),
    PatternSpec("species", "rat", "rat/rats", _rx(r"\brats?\b")),
    PatternSpec("species", "primate", "non-human primate", _rx(
        r"\b(?:macaques?|monkeys?|non[- ]human\s+primates?|primates?)\b"
    )),

    # Construct-bearing terms. ``instrument-only`` is shown to the reviewer but
    # deliberately cannot support an automatic construct comparison.
    PatternSpec("construct", "identification", "UPSIT", _rx(r"\bUPSIT(?:[- ]?40)?\b")),
    PatternSpec("construct", "identification", "B-SIT", _rx(r"\bB[- ]?SIT\b")),
    PatternSpec("construct", "identification", "SIT-12", _rx(r"\bSIT[- ]?12\b")),
    PatternSpec("construct", "instrument-only", "Sniffin' Sticks", _rx(
        r"\bSniffin(?:g)?[’']?\s+Sticks\b"
    )),
    PatternSpec("construct", "detection", "TDI", _rx(r"\bTDI\b")),
    PatternSpec("construct", "discrimination", "TDI", _rx(r"\bTDI\b")),
    PatternSpec("construct", "identification", "TDI", _rx(r"\bTDI\b")),
    PatternSpec("construct", "detection", "buried food/pellet", _rx(
        r"\bburied[- ](?:food|pellet)(?:\s+test)?\b"
    )),
    PatternSpec("construct", "discrimination", "habituation-dishabituation", _rx(
        r"\bhabituation\s*(?:[-–/]\s*)?dishabituation\b"
    )),
    PatternSpec("construct", "instrument-only", "go/no-go", _rx(
        r"\bgo\s*/?\s*no[- ]?go\b"
    )),
    PatternSpec("construct", "detection", "threshold series", _rx(
        r"\b(?:threshold\s+series|detection\s+threshold)\b"
    )),
    PatternSpec("construct", "identification", "identification", _rx(
        r"\b(?:odou?r|smell)\s+identification\b"
    )),
    PatternSpec("construct", "discrimination", "discrimination", _rx(
        r"\b(?:odou?r|olfactory)\s+(?:mixture\s+)?discrimination\b"
    )),
    PatternSpec("construct", "detection", "detection/threshold", _rx(
        r"\b(?:odou?r|olfactory)\s+(?:detection|threshold)\b"
    )),
    PatternSpec("construct", "other-memory", "odour memory", _rx(
        r"\b(?:odou?r|olfactory)\s+(?:recognition|memory)\b"
    )),
]

ODOUR_RE = _rx(r"\bodou?r(?:ant)?s?\b|\bolfactory\s+stimulation\b")
EVOKED_EVENT_RE = _rx(
    r"\b(?:evoked|stimuli?|stimulation|presentation|inhalation|olfactometer|sniff(?:ing|ed)?)\b"
)
RECORDING_RE = _rx(
    r"\b(?:LFP|EEG|ERP|OERP|fMRI|unit(?:s)?|spik(?:e|es|ing)|imaging|"
    r"electrophysiolog(?:y|ical)|oscillation(?:s)?|gamma|beta|potential(?:s)?|record(?:ed|ing|ings)?)\b"
)
RESTING_DIRECT_PATTERNS = [
    ("resting-state", _rx(r"\bresting[- ]state\b")),
    ("resting recording", _rx(r"\bresting\s+(?:EEG|fMRI|recording|activity)\b")),
    ("structural MRI", _rx(r"\bstructural\s+(?:MRI|magnetic resonance)\b")),
    ("FDG PET", _rx(r"\b(?:FDG[- ]?PET|fluorodeoxyglucose\s+PET)\b")),
]
EYES_CLOSED_RE = _rx(r"\beyes?[- ]closed\b")
HOME_CAGE_RE = _rx(r"\bhome[- ]cage\b")


def load_rows(path: Path) -> list[dict[str, str]]:
    try:
        handle = path.open(newline="", encoding="utf-8-sig")
    except OSError as error:
        raise RuntimeError(f"cannot open coding TSV {path}: {error}") from None
    with handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise RuntimeError(f"coding TSV has no header: {path}")
        missing = [name for name in REQUIRED_COLUMNS if name not in reader.fieldnames]
        if missing:
            raise RuntimeError(f"coding TSV missing required column(s): {', '.join(missing)}")
        rows = []
        seen = set()
        for number, raw in enumerate(reader, start=2):
            if None in raw or any(raw.get(name) is None for name in reader.fieldnames):
                raise RuntimeError(f"malformed coding TSV row {number}: wrong number of fields")
            row = {name: raw[name].strip() for name in reader.fieldnames}
            citekey = row["citekey"]
            if not citekey:
                raise RuntimeError(f"malformed coding TSV row {number}: empty citekey")
            if citekey in seen:
                raise RuntimeError(f"duplicate citekey in coding TSV: {citekey}")
            seen.add(citekey)
            rows.append(row)
    return rows


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


BLOCK_TAGS = {
    "abstract", "article-title", "p", "sec", "title", "list-item", "caption",
    "statement", "disp-quote", "table-wrap", "tr",
}


def _flatten_xml(
    element: ET.Element, *, mark_citations: bool = True, skip_ref_lists: bool = True
) -> str:
    parts: list[str] = []

    def visit(node: ET.Element) -> None:
        name = _local_name(node.tag)
        if name == "ref-list" and skip_ref_lists:
            return
        if name == "xref" and node.attrib.get("ref-type") == "bibr":
            if mark_citations:
                parts.append(f" {CITATION_MARKER} ")
            if node.tail:
                parts.append(node.tail)
            return
        if node.text:
            parts.append(node.text)
        for child in node:
            visit(child)
        if name in BLOCK_TAGS:
            parts.append(". ")
        if node.tail:
            parts.append(node.tail)

    visit(element)
    return html.unescape("".join(parts))


def load_xml_text(path: Path) -> tuple[str, str]:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as error:
        raise RuntimeError(f"cannot parse XML {path}: {error}") from None

    body_parts = []
    for element in root.iter():
        name = _local_name(element.tag)
        if name in {"abstract", "body"}:
            body_parts.append(_flatten_xml(element, mark_citations=True))
    # In normal JATS there is one body. Abstracts can be nested; de-duplicate the
    # resulting strings rather than depending on a publisher-specific structure.
    body_text = " ".join(dict.fromkeys(part for part in body_parts if part.strip()))

    ref_parts = [
        _flatten_xml(element, mark_citations=False, skip_ref_lists=False)
        for element in root.iter()
        if _local_name(element.tag) == "ref-list"
    ]
    return body_text, " ".join(ref_parts)


def split_plain_references(text: str) -> tuple[str, str]:
    match = REFERENCE_HEADING_RE.search(text)
    if match:
        return text[:match.start()], text[match.end():]

    # Multi-column PDF extraction can place a heading at the end of a line that
    # begins with unrelated column text: ``ARTICLE INFORMATION ... REFERENCES``.
    # Restrict this fallback to uppercase headings to avoid splitting prose that
    # merely mentions references or a bibliography.
    fallback = re.search(
        r"(?m)\b(?:REFERENCES|BIBLIOGRAPHY|LITERATURE\s+CITED)\s*$", text
    )
    if fallback:
        return text[:fallback.start()], text[fallback.end():]
    return text, ""


def load_full_text(vault: Path, citekey: str) -> tuple[str, str, str]:
    library = vault / "_library"
    txt = library / f"{citekey}.txt"
    xml = library / f"{citekey}.xml"
    if txt.is_file():
        try:
            body, references = split_plain_references(txt.read_text(errors="replace"))
        except OSError as error:
            raise RuntimeError(f"cannot read text sidecar {txt}: {error}") from None
        return body, references, "txt"
    if xml.is_file():
        body, references = load_xml_text(xml)
        return body, references, "xml"
    return "", "", "NO TEXT"


def split_sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []
    return [part.strip() for part in SENTENCE_BOUNDARY_RE.split(normalized) if part.strip()]


def evidence_for_sentence(sentence: str) -> list[Evidence]:
    found = []
    for spec in PATTERNS:
        if spec.pattern.search(sentence):
            found.append(Evidence(spec.dimension, spec.label, spec.term, sentence))

    if ODOUR_RE.search(sentence) and EVOKED_EVENT_RE.search(sentence) and RECORDING_RE.search(sentence):
        found.append(Evidence("neural", "evoked", "odour-evoked recording", sentence))
    for term, pattern in RESTING_DIRECT_PATTERNS:
        if pattern.search(sentence):
            found.append(Evidence("neural", "resting", term, sentence))
    if RECORDING_RE.search(sentence) and EYES_CLOSED_RE.search(sentence):
        found.append(Evidence("neural", "resting", "eyes-closed recording", sentence))
    if RECORDING_RE.search(sentence) and HOME_CAGE_RE.search(sentence):
        found.append(Evidence("neural", "resting", "home-cage recording", sentence))

    # A sentence can hit synonymous patterns. Preserve distinct labels/terms but
    # never inflate counts with exact duplicates.
    return list(dict.fromkeys(found))


def extract_evidence(body: str, references: str) -> tuple[list[Evidence], int, int]:
    evidence: list[Evidence] = []
    discarded_citations = 0
    for sentence in split_sentences(body):
        hits = evidence_for_sentence(sentence)
        if not hits:
            continue
        if CITATION_RE.search(sentence):
            discarded_citations += len(hits)
            continue
        evidence.extend(hits)

    discarded_references = sum(
        len(evidence_for_sentence(sentence)) for sentence in split_sentences(references)
    )
    return list(dict.fromkeys(evidence)), discarded_references, discarded_citations


def _labels(result: PaperResult, dimension: str, comparable_only: bool = True) -> set[str]:
    labels = {item.label for item in result.evidence if item.dimension == dimension}
    if comparable_only:
        labels.discard("instrument-only")
    return labels


def apply_screen_flags(result: PaperResult) -> None:
    if result.text_status == "NO TEXT":
        result.no_evidence_fields = [
            field for field in ("species", "construct", "neural")
            if result.row[field].lower() != "none"
        ]
        return

    species_raw = _labels(result, "species")
    species_seen = set(species_raw)
    if species_seen & {"mouse", "rat"}:
        species_seen.add("rodent")
    species_seen -= {"mouse", "rat"}

    construct_seen = _labels(result, "construct")
    neural_seen = _labels(result, "neural")
    seen_by_field = {
        "species": species_seen,
        "construct": construct_seen,
        "neural": neural_seen,
    }

    for field, seen in seen_by_field.items():
        coded = result.row[field].lower()
        expected = set() if coded == "none" else set(coded.split("+"))
        if expected and not seen:
            result.no_evidence_fields.append(field)
            continue
        if not seen:
            continue

        disagrees = False
        if field == "species" and coded == "both":
            disagrees = not {"human", "rodent"}.issubset(seen)
        elif not expected:
            disagrees = bool(seen)
        else:
            # Extra candidate labels do not contradict an authored code: they
            # may describe background, a transgenic protein, or a secondary
            # assay. Flag only when the body-pattern labels fail to contain the
            # coded category/categories.
            disagrees = not expected.issubset(seen)
        if disagrees:
            result.disagreement_fields.append(field)
            result.disagreement_details.append(
                f"{field}: coded={coded}; body-pattern labels={'+'.join(sorted(seen))}"
            )


def analyze(vault: Path, rows: list[dict[str, str]]) -> list[PaperResult]:
    results = []
    for row in rows:
        body, references, status = load_full_text(vault, row["citekey"])
        result = PaperResult(row=row, text_status=status)
        if status != "NO TEXT":
            evidence, ref_count, citation_count = extract_evidence(body, references)
            result.evidence = evidence
            result.discarded_reference_matches = ref_count
            result.discarded_citation_matches = citation_count
        apply_screen_flags(result)
        results.append(result)
    return results


def _evidence_lines(
    result: PaperResult, dimension: str, limit_per_label: int | None = None
) -> list[str]:
    grouped: dict[str, list[Evidence]] = {}
    for item in result.evidence:
        if item.dimension == dimension:
            grouped.setdefault(item.sentence, []).append(item)
    lines = []
    shown_by_label: dict[str, int] = {}
    for sentence, items in grouped.items():
        labels = {item.label for item in items}
        if limit_per_label is not None and all(
            shown_by_label.get(label, 0) >= limit_per_label for label in labels
        ):
            continue
        tags = ", ".join(sorted({f"{item.label}: {item.term}" for item in items}))
        lines.append(f"- **[{tags}]** {sentence}")
        for label in labels:
            shown_by_label[label] = shown_by_label.get(label, 0) + 1
    return lines


def render_markdown(results: list[PaperResult], coding_path: Path) -> str:
    no_evidence = [r for r in results if r.text_status == "NO TEXT" or r.no_evidence_fields]
    disagreements = [r for r in results if r.disagreement_fields]
    lines = [
        "# Coding-verification dossier",
        "",
        "> Generated by `coding_dossier.py`. This is a screening aid for a human second coder, ",
        "> not a classifier. Pattern hits are candidate evidence, disagreement flags are not ",
        "> corrections, and no proposed codes are produced.",
        f"> Markdown evidence display is capped at {MAX_MD_SENTENCES_PER_LABEL} sentences per label; ",
        "> omitted-hit counts are shown and all detected labels still contribute to screen flags.",
        "",
        f"**Coding table:** `{coding_path}`  ",
        f"**Rows screened:** {len(results)}  ",
        f"**No-text rows:** {sum(r.text_status == 'NO TEXT' for r in results)}  ",
        f"**Rows in the no-body-evidence queue (including `NO TEXT`):** {len(no_evidence)}  ",
        f"**Rows with mechanical evidence/code disagreement flags:** {len(disagreements)}",
        "",
        "## Review queue: no body evidence",
        "",
    ]
    if no_evidence:
        for result in no_evidence:
            detail = "NO TEXT" if result.text_status == "NO TEXT" else \
                ", ".join(result.no_evidence_fields)
            lines.append(f"- `{result.citekey}` — {detail}")
    else:
        lines.append("- none")

    lines += ["", "## Review queue: evidence/code disagreement", ""]
    if disagreements:
        for result in disagreements:
            lines.append(f"- `{result.citekey}` — " + "; ".join(result.disagreement_details))
    else:
        lines.append("- none")

    lines += [
        "",
        "## Discarded reference/citation matches",
        "",
        "Counts are pattern matches, not unique sentences. `reference-list` is text after a plain-",
        "text References/Bibliography/Literature Cited heading or inside an exact JATS `<ref-list>`. ",
        "`citation-bearing body` counts candidate matches rejected because their sentence contains ",
        "an in-text citation marker/string.",
        "",
        "| citekey | text | reference-list | citation-bearing body | total discarded |",
        "|---|---:|---:|---:|---:|",
    ]
    for result in results:
        lines.append(
            f"| `{result.citekey}` | {result.text_status} | "
            f"{result.discarded_reference_matches} | {result.discarded_citation_matches} | "
            f"{result.discarded_matches} |"
        )

    lines += ["", "## Paper dossiers", ""]
    for result in results:
        row = result.row
        lines += [
            f"### {result.citekey}",
            "",
            f"- Text: **{result.text_status}**",
            f"- Coded: species=`{row['species']}`; design=`{row['design']}`; "
            f"construct=`{row['construct']}`; neural=`{row['neural']}`; "
            f"instrument=`{row['instrument']}`; confidence=`{row['confidence']}`",
            f"- Authored evidence: {row['evidence'] or '-'}",
            f"- Discarded matches: **{result.discarded_matches}** "
            f"(reference-list={result.discarded_reference_matches}, "
            f"citation-bearing body={result.discarded_citation_matches})",
            f"- No-evidence flag: {', '.join(result.no_evidence_fields) or 'none'}",
            f"- Disagreement flag: {'; '.join(result.disagreement_details) or 'none'}",
            "",
        ]
        if result.text_status == "NO TEXT":
            lines += ["No full text held; no extraction attempted.", ""]
            continue
        for dimension in ("species", "construct", "neural"):
            all_evidence_lines = _evidence_lines(result, dimension)
            evidence_lines = _evidence_lines(
                result, dimension, limit_per_label=MAX_MD_SENTENCES_PER_LABEL
            )
            lines += [f"#### {dimension.capitalize()} candidate sentences", ""]
            lines += evidence_lines or ["- none found"]
            omitted = len(all_evidence_lines) - len(evidence_lines)
            if omitted:
                lines.append(
                    f"- *Display capped at {MAX_MD_SENTENCES_PER_LABEL} sentences per label; "
                    f"{omitted} additional candidate sentence(s) omitted.*"
                )
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _flat_evidence(result: PaperResult, dimension: str) -> str:
    parts = []
    for line in _evidence_lines(result, dimension):
        parts.append(re.sub(r"^- \*\*|\*\* ", "", line))
    return " || ".join(parts)


def render_tsv(results: list[PaperResult]) -> str:
    extra = [
        "text_status", "no_evidence_fields", "disagreement_fields", "disagreement_details",
        "discarded_reference_matches", "discarded_citation_matches", "discarded_matches",
        "species_candidate_sentences", "construct_candidate_sentences", "neural_candidate_sentences",
    ]
    output = []
    from io import StringIO
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=REQUIRED_COLUMNS + extra, delimiter="\t",
                            lineterminator="\n")
    writer.writeheader()
    for result in results:
        row = {name: result.row[name] for name in REQUIRED_COLUMNS}
        row.update({
            "text_status": result.text_status,
            "no_evidence_fields": "+".join(result.no_evidence_fields),
            "disagreement_fields": "+".join(result.disagreement_fields),
            "disagreement_details": " || ".join(result.disagreement_details),
            "discarded_reference_matches": result.discarded_reference_matches,
            "discarded_citation_matches": result.discarded_citation_matches,
            "discarded_matches": result.discarded_matches,
            "species_candidate_sentences": _flat_evidence(result, "species"),
            "construct_candidate_sentences": _flat_evidence(result, "construct"),
            "neural_candidate_sentences": _flat_evidence(result, "neural"),
        })
        writer.writerow(row)
    output.append(stream.getvalue())
    return "".join(output)


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
    parser = argparse.ArgumentParser(description="Build a review dossier for a coding TSV.")
    parser.add_argument("--vault", required=True, type=Path, help="neubrain vault root")
    parser.add_argument("--coding", required=True, type=Path, help="coding TSV")
    parser.add_argument("--out", required=True, type=Path, help="output dossier path")
    parser.add_argument(
        "--citekey", action="append", nargs="+", metavar="KEY",
        help="restrict to named citekeys (repeatable)",
    )
    parser.add_argument("--format", choices=("md", "tsv"), default="md")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        rows = load_rows(args.coding)
        if args.citekey:
            requested = {key for group in args.citekey for key in group}
            available = {row["citekey"] for row in rows}
            unknown = sorted(requested - available)
            if unknown:
                raise RuntimeError(f"citekey(s) absent from coding TSV: {', '.join(unknown)}")
            rows = [row for row in rows if row["citekey"] in requested]
        results = analyze(args.vault, rows)
        content = render_markdown(results, args.coding) if args.format == "md" else render_tsv(results)
        write_output(args.out, content)
    except RuntimeError as error:
        print(f"coding_dossier: ERROR: {error}", file=sys.stderr)
        return 1

    no_evidence = [r.citekey for r in results if r.text_status == "NO TEXT" or r.no_evidence_fields]
    disagreements = [r.citekey for r in results if r.disagreement_fields]
    print(f"wrote {args.out}")
    print(f"rows={len(results)} no_text={sum(r.text_status == 'NO TEXT' for r in results)} "
          f"no_body_evidence={len(no_evidence)} disagreements={len(disagreements)}")
    print("no_body_evidence: " + (", ".join(no_evidence) or "none"))
    print("disagreements: " + (", ".join(disagreements) or "none"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
