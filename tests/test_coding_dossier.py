from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import coding_dossier


HEADER = [
    "citekey", "species", "design", "construct", "neural",
    "instrument", "evidence", "confidence",
]


def row(citekey: str, species: str = "none", construct: str = "none",
        neural: str = "none") -> dict[str, str]:
    return {
        "citekey": citekey, "species": species, "design": "empirical",
        "construct": construct, "neural": neural, "instrument": "-",
        "evidence": "fixture", "confidence": "high",
    }


def make_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    (vault / "_library").mkdir(parents=True)
    return vault


def write_coding(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADER, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def test_plain_reference_only_keyword_is_discarded(tmp_path: Path) -> None:
    vault = make_vault(tmp_path)
    (vault / "_library" / "plain2000.txt").write_text(
        "This methods paper discusses calibration.\n\n"
        "References\nSmith A. Sniffin' Sticks identification in patients. 2019.\n"
    )

    result = coding_dossier.analyze(vault, [row("plain2000")])[0]

    assert not result.evidence
    assert result.discarded_reference_matches > 0


def test_jats_ref_list_keyword_is_discarded(tmp_path: Path) -> None:
    vault = make_vault(tmp_path)
    (vault / "_library" / "jats2000.xml").write_text(
        "<article><body><p>This methods paper discusses calibration.</p></body>"
        "<back><ref-list><ref><mixed-citation>Mouse UPSIT study. 2018."
        "</mixed-citation></ref></ref-list></back></article>"
    )

    result = coding_dossier.analyze(vault, [row("jats2000")])[0]

    assert not result.evidence
    assert result.discarded_reference_matches > 0


def test_body_keyword_is_reported(tmp_path: Path) -> None:
    vault = make_vault(tmp_path)
    (vault / "_library" / "body2000.txt").write_text(
        "Human participants completed the SIT-12 smell identification test."
    )

    result = coding_dossier.analyze(
        vault, [row("body2000", species="human", construct="identification")]
    )[0]

    assert any(item.term == "SIT-12" for item in result.evidence)
    assert any(item.dimension == "species" for item in result.evidence)


def test_citation_bearing_body_sentence_is_discarded(tmp_path: Path) -> None:
    vault = make_vault(tmp_path)
    (vault / "_library" / "cited2000.txt").write_text(
        "Patients completed UPSIT in an earlier study (Smith et al., 2020). "
        "This paper discusses calibration."
    )

    result = coding_dossier.analyze(vault, [row("cited2000")])[0]

    assert not result.evidence
    assert result.discarded_citation_matches > 0


def test_disagreement_with_body_evidence_is_flagged(tmp_path: Path) -> None:
    vault = make_vault(tmp_path)
    (vault / "_library" / "mismatch2000.txt").write_text(
        "Mice underwent the buried food test."
    )

    result = coding_dossier.analyze(
        vault, [row("mismatch2000", species="human", construct="none")]
    )[0]

    assert set(result.disagreement_fields) == {"species", "construct"}
    assert not any("proposed" in detail for detail in result.disagreement_details)


def test_no_text_is_reported_not_skipped(tmp_path: Path) -> None:
    vault = make_vault(tmp_path)

    result = coding_dossier.analyze(
        vault, [row("missing2000", species="human", construct="identification")]
    )[0]

    assert result.text_status == "NO TEXT"
    assert result.no_evidence_fields == ["species", "construct"]
    assert "No full text held" in coding_dossier.render_markdown([result], Path("coding.tsv"))


def test_citekey_restricts_output(tmp_path: Path) -> None:
    vault = make_vault(tmp_path)
    coding = tmp_path / "coding.tsv"
    out = tmp_path / "dossier.md"
    write_coding(coding, [row("keep2000"), row("drop2000")])

    exit_code = coding_dossier.main([
        "--vault", str(vault), "--coding", str(coding), "--out", str(out),
        "--citekey", "keep2000",
    ])

    assert exit_code == 0
    assert "### keep2000" in out.read_text()
    assert "drop2000" not in out.read_text()


def test_missing_required_column_crashes_loudly(tmp_path: Path) -> None:
    coding = tmp_path / "bad.tsv"
    coding.write_text("citekey\tspecies\nkey2000\thuman\n")

    with pytest.raises(RuntimeError, match="missing required column"):
        coding_dossier.load_rows(coding)
