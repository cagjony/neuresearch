#!/usr/bin/env python3
"""Extract searchable text sidecars for PDF-only manifest entries.

The manifest is the source of truth: eligible entries list ``<stem>.pdf`` and
list neither XML nor text.  ``pdftotext -layout`` supplies the text while a
three-page probe keeps image-only scans from producing near-empty sidecars.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


MIN_FIRST_THREE_CHARS = 600
CITATION_RE = re.compile(r"@([A-Za-z0-9][A-Za-z0-9_.:-]*)")


@dataclass
class Summary:
    extracted: int = 0
    needs_ocr: int = 0
    skipped_xml: int = 0
    skipped_text: int = 0
    skipped_project: int = 0
    skipped_uncited: int = 0


def load_manifest(path: Path) -> dict:
    try:
        manifest = json.loads(path.read_text())
    except FileNotFoundError:
        raise RuntimeError(f"manifest not found: {path}") from None
    if not isinstance(manifest.get("entries"), dict):
        raise RuntimeError(f"manifest has no entries object: {path}")
    return manifest


def _manifest_indent(path: Path) -> int:
    """Preserve the current file's indentation during whole-file RMW."""
    lines = path.read_text().splitlines()
    for line in lines[1:]:
        stripped = line.lstrip(" ")
        if stripped and stripped != line:
            return len(line) - len(stripped)
    return 2


def save_manifest(path: Path, manifest: dict, indent: int) -> None:
    payload = json.dumps(manifest, indent=indent, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=".manifest.", delete=False
    ) as handle:
        tmp = Path(handle.name)
        handle.write(payload)
    try:
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def cited_keys(vault: Path, project: str) -> set[str]:
    manuscript = vault / "projects" / project / "manuscript.md"
    try:
        return set(CITATION_RE.findall(manuscript.read_text()))
    except FileNotFoundError:
        raise RuntimeError(f"project manuscript not found: {manuscript}") from None


def _has_xml(files: list[str]) -> bool:
    return any(name.lower().endswith(".xml") for name in files)


def _has_txt(files: list[str]) -> bool:
    return any(Path(name).suffix.lower() == ".txt" for name in files)


def _pdf_for(stem: str, files: list[str], library: Path) -> Path | None:
    pdfs = [name for name in files if Path(name).suffix.lower() == ".pdf"]
    if not pdfs:
        return None
    expected = f"{stem}.pdf"
    if pdfs != [expected]:
        raise RuntimeError(
            f"manifest stem/file invariant violated for {stem}: expected only {expected}, "
            f"found {pdfs}"
        )
    pdf = library / expected
    if not pdf.is_file():
        raise RuntimeError(f"manifest lists missing PDF: {pdf}")
    return pdf


def _pdftotext(pdf: Path, first_three_only: bool) -> str:
    command = ["pdftotext", "-layout"]
    if first_three_only:
        command.extend(["-f", "1", "-l", "3"])
    command.extend([str(pdf), "-"])
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode:
        detail = result.stderr.strip() or "no diagnostic output"
        raise RuntimeError(f"pdftotext failed for {pdf.name}: {detail}")
    return result.stdout


def _meaningful_chars(text: str) -> int:
    return sum(not char.isspace() for char in text)


def extract(
    vault: Path,
    project: str | None = None,
    *,
    force: bool = False,
    dry_run: bool = False,
    only_cited: bool = False,
) -> Summary:
    library = vault / "_library"
    manifest_path = library / "manifest.json"
    manifest = load_manifest(manifest_path)
    indent = _manifest_indent(manifest_path)
    citations = cited_keys(vault, project) if only_cited and project else None
    summary = Summary()
    planned: list[tuple[str, Path, Path, str]] = []

    for stem, entry in sorted(manifest["entries"].items()):
        if not isinstance(entry, dict):
            raise RuntimeError(f"manifest entry {stem!r} is not an object")
        files = entry.get("files", [])
        if not isinstance(files, list) or not all(isinstance(name, str) for name in files):
            raise RuntimeError(f"manifest entry {stem!r} has an invalid files list")

        if project and project not in entry.get("projects", []):
            if any(Path(name).suffix.lower() == ".pdf" for name in files):
                summary.skipped_project += 1
            continue
        if citations is not None and stem not in citations:
            if any(Path(name).suffix.lower() == ".pdf" for name in files):
                summary.skipped_uncited += 1
            continue
        pdf = _pdf_for(stem, files, library)
        if pdf is None:
            continue
        if _has_xml(files):
            summary.skipped_xml += 1
            continue

        txt = library / f"{stem}.txt"
        if not force and (_has_txt(files) or txt.exists()):
            summary.skipped_text += 1
            continue

        if shutil.which("pdftotext") is None:
            raise RuntimeError("pdftotext not found on PATH (install poppler-utils)")
        probe = _pdftotext(pdf, first_three_only=True)
        chars = _meaningful_chars(probe)
        if chars < MIN_FIRST_THREE_CHARS:
            summary.needs_ocr += 1
            print(
                f"[OCR] {stem}: {chars} non-whitespace chars in first 3 pages "
                f"(< {MIN_FIRST_THREE_CHARS}); no sidecar written"
            )
            continue

        if dry_run:
            print(f"[DRY-RUN] {stem}: would write {txt.name} ({chars} probe chars)")
            summary.extracted += 1
            continue

        text = _pdftotext(pdf, first_three_only=False)
        planned.append((stem, pdf, txt, text))

    if not dry_run and planned:
        staged: list[tuple[str, Path, Path]] = []
        try:
            for stem, _pdf, txt, text in planned:
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", dir=library,
                    prefix=f".{stem}.", suffix=".txt", delete=False,
                ) as handle:
                    tmp = Path(handle.name)
                    handle.write(text)
                staged.append((stem, tmp, txt))

            for stem, tmp, txt in staged:
                tmp.replace(txt)
                files = manifest["entries"][stem]["files"]
                if txt.name not in files:
                    files.append(txt.name)
                summary.extracted += 1
                print(f"[OK] {stem}: wrote {txt.name}")

            save_manifest(manifest_path, manifest, indent)
        finally:
            for _stem, tmp, _txt in staged:
                tmp.unlink(missing_ok=True)

    print(
        "summary: "
        f"{'would_extract' if dry_run else 'extracted'}={summary.extracted}, "
        f"needs_ocr={summary.needs_ocr}, skipped_xml={summary.skipped_xml}, "
        f"skipped_text={summary.skipped_text}, skipped_project={summary.skipped_project}, "
        f"skipped_uncited={summary.skipped_uncited}"
    )
    return summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract .txt sidecars for PDF-only manifest entries."
    )
    parser.add_argument("--vault", required=True, type=Path, help="neubrain vault root")
    parser.add_argument("--project", help="restrict to manifest entries tagged with this project")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--only-missing", dest="force", action="store_false", default=False,
        help="do not overwrite existing .txt sidecars (default)",
    )
    mode.add_argument(
        "--force", dest="force", action="store_true", help="re-extract and overwrite .txt"
    )
    parser.add_argument("--dry-run", action="store_true", help="report actions; write nothing")
    parser.add_argument(
        "--cited-only", action="store_true",
        help="with --project, restrict further to citekeys in its manuscript.md",
    )
    args = parser.parse_args(argv)
    if args.cited_only and not args.project:
        parser.error("--cited-only requires --project")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        extract(
            args.vault,
            args.project,
            force=args.force,
            dry_run=args.dry_run,
            only_cited=args.cited_only,
        )
    except RuntimeError as error:
        print(f"extract_text: ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
