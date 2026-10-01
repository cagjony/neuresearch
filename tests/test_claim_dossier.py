from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import claim_dossier


TARGET_HEADER = ["citekey", "n_citations", "has_text"]


def make_vault(tmp_path: Path, titles: dict[str, str]) -> Path:
    vault = tmp_path / "vault"
    library = vault / "_library"
    library.mkdir(parents=True)
    entries = {
        key: {"title": title, "files": [f"{key}.txt"]}
        for key, title in titles.items()
    }
    (library / "manifest.json").write_text(
        json.dumps({"by_id": {}, "entries": entries}, indent=2) + "\n"
    )
    return vault


def write_targets(path: Path, rows: list[tuple[str, int, str]]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(TARGET_HEADER)
        writer.writerows(rows)


def run_tool(vault: Path, targets: Path, manuscript: Path, out: Path,
             citekeys: list[str] | None = None) -> int:
    args = [
        "--vault", str(vault), "--targets", str(targets),
        "--manuscript", str(manuscript), "--out", str(out),
    ]
    if citekeys:
        args += ["--citekey", *citekeys]
    return claim_dossier.main(args)


def test_one_entry_per_citation_instance(tmp_path: Path) -> None:
    vault = make_vault(tmp_path, {"twice2000": "Repeated source"})
    (vault / "_library" / "twice2000.txt").write_text(
        "Oscillatory recording was performed with EEG.\n\nMethods\nEEG recorded oscillations."
    )
    targets = tmp_path / "targets.tsv"
    write_targets(targets, [("twice2000", 2, "txt")])
    manuscript = tmp_path / "manuscript.md"
    manuscript.write_text(
        "## First section\nOscillations were recorded [@twice2000].\n\n"
        "<!-- audit note with a non-prose citation [@twice2000] -->\n\n"
        "## Second section\nEEG changed later [@twice2000].\n"
    )
    out = tmp_path / "out.md"

    assert run_tool(vault, targets, manuscript, out) == 0
    text = out.read_text()
    assert len(re.findall(r"^### Entry", text, re.MULTILINE)) == 2
    assert "twice2000 (1/2)" in text
    assert "twice2000 (2/2)" in text


def test_reference_only_term_is_never_selected_as_evidence(tmp_path: Path) -> None:
    vault = make_vault(tmp_path, {"refs2000": "Reference-only term"})
    (vault / "_library" / "refs2000.txt").write_text(
        "This body discusses calibration procedures.\n\n"
        "References\nSmith A. Gamma oscillations measured with EEG. 2020.\n"
    )
    body, references, _status = claim_dossier.coding.load_full_text(vault, "refs2000")
    clean = [
        sentence for sentence in claim_dossier.coding.split_sentences(body)
        if not claim_dossier.coding.CITATION_RE.search(sentence)
    ]

    evidence = claim_dossier.best_evidence("Gamma oscillations changed [@refs2000].", clean)

    assert not evidence
    assert "Gamma oscillations" in references


def test_verdict_column_is_always_empty(tmp_path: Path) -> None:
    vault = make_vault(tmp_path, {"blank2000": "Blank verdict"})
    (vault / "_library" / "blank2000.txt").write_text("Patients completed an olfactory test.")
    targets = tmp_path / "targets.tsv"
    write_targets(targets, [("blank2000", 1, "txt")])
    manuscript = tmp_path / "manuscript.md"
    manuscript.write_text("## Results\nPatients completed testing [@blank2000].\n")
    out = tmp_path / "out.md"

    assert run_tool(vault, targets, manuscript, out) == 0
    text = out.read_text()
    assert text.count("| VERDICT |") == 1
    assert re.findall(r"\| VERDICT \|\n\|---\|\n(.*)", text) == ["| |"]


def test_no_text_target_is_reported_with_reason(tmp_path: Path) -> None:
    vault = make_vault(tmp_path, {"missing2000": "No text source"})
    (vault / "_library" / "missing2000.txt").unlink(missing_ok=True)
    manifest = json.loads((vault / "_library" / "manifest.json").read_text())
    manifest["entries"]["missing2000"]["files"] = ["missing2000.pdf"]
    (vault / "_library" / "manifest.json").write_text(json.dumps(manifest))
    targets = tmp_path / "targets.tsv"
    write_targets(targets, [("missing2000", 1, "NONE")])
    manuscript = tmp_path / "manuscript.md"
    manuscript.write_text("## Models\nThe model was foundational [@missing2000].\n")
    out = tmp_path / "out.md"

    assert run_tool(vault, targets, manuscript, out) == 0

    text = out.read_text()
    assert "NO TEXT HELD — PDF is present" in text
    assert "### Entry 001 — missing2000" in text


def test_citekey_restricts_correctly(tmp_path: Path) -> None:
    vault = make_vault(tmp_path, {"keep2000": "Keep", "drop2000": "Drop"})
    for key in ("keep2000", "drop2000"):
        (vault / "_library" / f"{key}.txt").write_text("Olfactory testing was performed.")
    targets = tmp_path / "targets.tsv"
    write_targets(targets, [("keep2000", 1, "txt"), ("drop2000", 1, "txt")])
    manuscript = tmp_path / "manuscript.md"
    manuscript.write_text(
        "## Section\nKeep claim [@keep2000]. Drop claim [@drop2000].\n"
    )
    out = tmp_path / "out.md"

    assert run_tool(vault, targets, manuscript, out, ["keep2000"]) == 0

    text = out.read_text()
    assert "keep2000" in text
    assert "drop2000" not in text


def test_missing_target_column_crashes_loudly(tmp_path: Path) -> None:
    targets = tmp_path / "bad.tsv"
    targets.write_text("citekey\tn_citations\nkey2000\t1\n")

    with pytest.raises(RuntimeError, match="missing required column"):
        claim_dossier.load_targets(targets)
