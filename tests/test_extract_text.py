from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import extract_text


def make_vault(tmp_path: Path, entries: dict) -> Path:
    vault = tmp_path / "vault"
    library = vault / "_library"
    library.mkdir(parents=True)
    (library / "manifest.json").write_text(
        json.dumps({"by_id": {}, "entries": entries}, indent=2, sort_keys=True) + "\n"
    )
    return vault


@pytest.fixture
def fake_pdftotext(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    command = bindir / "pdftotext"
    command.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys\n"
        "pdf = pathlib.Path(sys.argv[-2])\n"
        "if b'SCAN' in pdf.read_bytes():\n"
        "    print('')\n"
        "else:\n"
        "    print('extracted ' + 'x' * 800)\n"
    )
    command.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    return command


def add_pdf(vault: Path, stem: str, marker: bytes = b"TEXT") -> None:
    (vault / "_library" / f"{stem}.pdf").write_bytes(b"%PDF-1.4\n" + marker)


def read_manifest(vault: Path) -> dict:
    return json.loads((vault / "_library" / "manifest.json").read_text())


def test_pdf_without_text_writes_sidecar_and_updates_manifest(
    tmp_path: Path, fake_pdftotext: Path
) -> None:
    vault = make_vault(tmp_path, {"paper2000": {"files": ["paper2000.pdf"]}})
    add_pdf(vault, "paper2000")

    result = extract_text.extract(vault)

    assert result.extracted == 1
    assert (vault / "_library" / "paper2000.txt").read_text().startswith("extracted")
    assert read_manifest(vault)["entries"]["paper2000"]["files"] == [
        "paper2000.pdf", "paper2000.txt"
    ]


def test_entry_with_xml_is_skipped(tmp_path: Path, fake_pdftotext: Path) -> None:
    vault = make_vault(
        tmp_path,
        {"paper2000": {"files": ["paper2000.pdf", "paper2000.xml"]}},
    )
    add_pdf(vault, "paper2000")

    result = extract_text.extract(vault)

    assert result.skipped_xml == 1
    assert not (vault / "_library" / "paper2000.txt").exists()


def test_existing_text_is_skipped_unless_forced(
    tmp_path: Path, fake_pdftotext: Path
) -> None:
    vault = make_vault(
        tmp_path,
        {"paper2000": {"files": ["paper2000.pdf", "paper2000.txt"]}},
    )
    add_pdf(vault, "paper2000")
    txt = vault / "_library" / "paper2000.txt"
    txt.write_text("keep me")

    skipped = extract_text.extract(vault)
    assert skipped.skipped_text == 1
    assert txt.read_text() == "keep me"

    forced = extract_text.extract(vault, force=True)
    assert forced.extracted == 1
    assert txt.read_text().startswith("extracted")
    assert read_manifest(vault)["entries"]["paper2000"]["files"].count(
        "paper2000.txt"
    ) == 1


def test_image_only_pdf_is_reported_without_sidecar(
    tmp_path: Path, fake_pdftotext: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    vault = make_vault(tmp_path, {"scan1996": {"files": ["scan1996.pdf"]}})
    add_pdf(vault, "scan1996", b"SCAN")

    result = extract_text.extract(vault)

    assert result.needs_ocr == 1
    assert "[OCR] scan1996" in capsys.readouterr().out
    assert not (vault / "_library" / "scan1996.txt").exists()
    assert read_manifest(vault)["entries"]["scan1996"]["files"] == ["scan1996.pdf"]


def test_dry_run_writes_nothing(tmp_path: Path, fake_pdftotext: Path) -> None:
    vault = make_vault(tmp_path, {"paper2000": {"files": ["paper2000.pdf"]}})
    add_pdf(vault, "paper2000")
    manifest = vault / "_library" / "manifest.json"
    before = manifest.read_bytes()

    result = extract_text.extract(vault, dry_run=True)

    assert result.extracted == 1
    assert manifest.read_bytes() == before
    assert not (vault / "_library" / "paper2000.txt").exists()
