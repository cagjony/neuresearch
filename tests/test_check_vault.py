from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import check_vault


def make_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "neubrain"
    (vault / "projects").mkdir(parents=True)
    (vault / "logs").mkdir()
    return vault


def add_project(vault: Path, name: str, cfg: dict | None) -> Path:
    d = vault / "projects" / name
    d.mkdir(parents=True)
    if cfg is not None:
        (d / "project.json").write_text(json.dumps(cfg, indent=2) + "\n")
    return d


def paper_cfg(name: str) -> dict:
    return {"schema": 1, "name": name, "type": "paper", "status": "active"}


def test_discover_finds_project_directories_sorted(tmp_path):
    vault = make_vault(tmp_path)
    add_project(vault, "zeta", paper_cfg("zeta"))
    add_project(vault, "alpha", paper_cfg("alpha"))
    (vault / "projects" / "loose.md").write_text("not a project\n")
    found = [p.name for p in check_vault.discover(vault)]
    assert found == ["alpha", "zeta"]


def test_missing_config_is_a_report_finding(tmp_path):
    vault = make_vault(tmp_path)
    add_project(vault, "orphan", None)
    findings = check_vault.collect(vault)
    codes = {f.code for f in findings}
    assert "no-project-config" in codes
    bad = [f for f in findings if f.code == "no-project-config"]
    assert bad[0].project == "orphan"
    assert bad[0].level == "REPORT"


def test_render_says_clean_when_there_are_no_findings():
    text = check_vault.render([])
    assert "no drift" in text.lower()


def test_render_groups_by_project_and_shows_both_levels():
    text = check_vault.render([
        check_vault.Finding("REPORT", "alz-olf", "loose-script", "patch.py"),
        check_vault.Finding("AUTO", "alz-olf", "missing-state", "STATE.md absent"),
    ])
    assert "alz-olf" in text
    assert "patch.py" in text
    assert "STATE.md absent" in text
    assert "AUTO" in text and "REPORT" in text


def test_main_writes_the_report_and_exits_1_on_drift(tmp_path, monkeypatch):
    vault = make_vault(tmp_path)
    add_project(vault, "orphan", None)
    monkeypatch.setattr(sys, "argv", ["check_vault.py", "--vault", str(vault)])
    rc = check_vault.main()
    assert rc == 1
    report = vault / "logs" / "vault-status.md"
    assert report.is_file()
    assert "orphan" in report.read_text()


def test_main_exits_0_and_still_writes_when_clean(tmp_path, monkeypatch):
    vault = make_vault(tmp_path)
    monkeypatch.setattr(sys, "argv", ["check_vault.py", "--vault", str(vault)])
    rc = check_vault.main()
    assert rc == 0
    assert (vault / "logs" / "vault-status.md").is_file()


def test_main_exits_2_when_vault_has_no_projects_dir(tmp_path, monkeypatch):
    empty = tmp_path / "not-a-vault"
    empty.mkdir()
    monkeypatch.setattr(sys, "argv", ["check_vault.py", "--vault", str(empty)])
    assert check_vault.main() == 2


def test_it_writes_only_the_report(tmp_path, monkeypatch):
    vault = make_vault(tmp_path)
    d = add_project(vault, "alz-olf", paper_cfg("alz-olf"))
    (d / "plan.md").write_text("plan\n")
    before = {p for p in vault.rglob("*") if p.is_file()}
    monkeypatch.setattr(sys, "argv", ["check_vault.py", "--vault", str(vault)])
    check_vault.main()
    after = {p for p in vault.rglob("*") if p.is_file()}
    assert after - before == {vault / "logs" / "vault-status.md"}


def full_paper(vault: Path, name: str) -> Path:
    d = add_project(vault, name, paper_cfg(name))
    (d / "plan.md").write_text("plan\n")
    (d / "papers.txt").write_text("\n")
    (d / "archive").mkdir()
    (d / "draft").mkdir()
    (d / "draft" / "manuscript.tex").write_text("\\documentclass{article}\n")
    (d / "draft" / "references.bib").write_text("\n")
    return d


def full_pipeline(vault: Path, name: str) -> Path:
    d = add_project(vault, name, {
        "schema": 1, "name": name, "type": "pipeline", "status": "active",
    })
    (d / "plan.md").write_text("plan\n")
    (d / "protocol.md").write_text("protocol\n")
    (d / "studies").mkdir()
    return d


def full_reference(vault: Path, name: str) -> Path:
    d = add_project(vault, name, {
        "schema": 1, "name": name, "type": "reference", "status": "active",
    })
    (d / "STATE.md").write_text("state\n")
    (d / "reading.md").write_text("sources\n")
    return d


def codes_for(vault: Path, project: str, code: str) -> list:
    return [f for f in check_vault.collect(vault)
            if f.project == project and f.code == code]


def test_complete_paper_project_reports_no_shape_drift(tmp_path):
    vault = make_vault(tmp_path)
    full_paper(vault, "alz-olf")
    assert codes_for(vault, "alz-olf", "missing-required") == []


def test_complete_pipeline_project_reports_no_shape_drift(tmp_path):
    vault = make_vault(tmp_path)
    full_pipeline(vault, "oldenlabs")
    assert codes_for(vault, "oldenlabs", "missing-required") == []


def test_complete_reference_project_reports_no_shape_drift(tmp_path):
    vault = make_vault(tmp_path)
    full_reference(vault, "neuvsc")
    assert codes_for(vault, "neuvsc", "missing-required") == []


def test_reference_missing_reading_list_is_reported(tmp_path):
    vault = make_vault(tmp_path)
    d = full_reference(vault, "neuvsc")
    (d / "reading.md").unlink()
    found = codes_for(vault, "neuvsc", "missing-required")
    assert [f.message for f in found] == ["reading.md is missing"]


def test_paper_missing_draft_manuscript_is_reported(tmp_path):
    vault = make_vault(tmp_path)
    d = full_paper(vault, "alz-olf")
    (d / "draft" / "manuscript.tex").unlink()
    found = codes_for(vault, "alz-olf", "missing-required")
    assert len(found) == 1
    assert "draft/manuscript" in found[0].message
    assert found[0].level == "REPORT"


def test_markdown_manuscript_also_satisfies_the_glob(tmp_path):
    vault = make_vault(tmp_path)
    d = full_paper(vault, "alz-olf")
    (d / "draft" / "manuscript.tex").unlink()
    (d / "draft" / "manuscript.md").write_text("# title\n")
    assert codes_for(vault, "alz-olf", "missing-required") == []


def test_pipeline_missing_protocol_is_reported(tmp_path):
    vault = make_vault(tmp_path)
    d = full_pipeline(vault, "oldenlabs")
    (d / "protocol.md").unlink()
    found = codes_for(vault, "oldenlabs", "missing-required")
    assert [f.message for f in found] == ["protocol.md is missing"]


def test_a_file_where_a_directory_is_required_is_reported(tmp_path):
    vault = make_vault(tmp_path)
    d = full_pipeline(vault, "oldenlabs")
    (d / "studies").rmdir()
    (d / "studies").write_text("oops\n")
    found = codes_for(vault, "oldenlabs", "missing-required")
    assert len(found) == 1
    assert "studies/" in found[0].message


def test_loose_python_at_project_root_is_reported(tmp_path):
    vault = make_vault(tmp_path)
    d = full_paper(vault, "alz-olf")
    (d / "patch.py").write_text("# one-off\n")
    (d / "fix_figures.py").write_text("# one-off\n")
    found = codes_for(vault, "alz-olf", "loose-script")
    assert {f.message.split()[0] for f in found} == {"fix_figures.py", "patch.py"}
    assert all(f.level == "REPORT" for f in found)


def test_scripts_in_tools_are_fine(tmp_path):
    vault = make_vault(tmp_path)
    d = full_paper(vault, "alz-olf")
    (d / "tools").mkdir()
    (d / "tools" / "build_figure.py").write_text("# kept\n")
    assert codes_for(vault, "alz-olf", "loose-script") == []


def test_manuscript_outside_draft_is_reported(tmp_path):
    vault = make_vault(tmp_path)
    d = full_paper(vault, "astro_atp")
    (d / "manuscript.tex").write_text("old\n")
    found = codes_for(vault, "astro_atp", "stray-manuscript")
    assert len(found) == 1
    assert "manuscript.tex" in found[0].message


def test_nested_manuscript_outside_draft_is_reported(tmp_path):
    vault = make_vault(tmp_path)
    d = full_paper(vault, "astro_atp")
    (d / "analysis" / "manuscript_v2").mkdir(parents=True)
    (d / "analysis" / "manuscript_v2" / "manuscript.tex").write_text("live\n")
    found = codes_for(vault, "astro_atp", "stray-manuscript")
    assert len(found) == 1
    assert "analysis/manuscript_v2/manuscript.tex" in found[0].message


def test_the_draft_manuscript_is_not_reported_as_stray(tmp_path):
    vault = make_vault(tmp_path)
    full_paper(vault, "astro_atp")
    assert codes_for(vault, "astro_atp", "stray-manuscript") == []


def test_submission_folder_missing_from_submissions_md_is_reported(tmp_path):
    vault = make_vault(tmp_path)
    d = full_paper(vault, "astro_atp")
    (d / "submissions" / "2026-07-09-csf").mkdir(parents=True)
    (d / "submissions" / "2026-08-14-nonlinear-science").mkdir(parents=True)
    (d / "SUBMISSIONS.md").write_text(
        "| 2026-07-09 | CSF | X | `submitted/2026-07-09-csf` | abc | sent |\n"
    )
    found = codes_for(vault, "astro_atp", "unrecorded-submission")
    assert len(found) == 1
    assert "2026-08-14-nonlinear-science" in found[0].message


def test_submissions_without_a_submissions_md_is_reported(tmp_path):
    vault = make_vault(tmp_path)
    d = full_paper(vault, "alz-olf")
    (d / "submissions" / "2026-01-01-journal").mkdir(parents=True)
    found = codes_for(vault, "alz-olf", "unrecorded-submission")
    assert len(found) == 1
    assert "SUBMISSIONS.md" in found[0].message


def test_no_submissions_directory_is_not_a_finding(tmp_path):
    vault = make_vault(tmp_path)
    full_paper(vault, "alz-olf")
    assert codes_for(vault, "alz-olf", "unrecorded-submission") == []


def pipeline_with_data(vault: Path, name: str, data_root: Path) -> Path:
    d = add_project(vault, name, {
        "schema": 1, "name": name, "type": "pipeline", "status": "active",
        "data_root": str(data_root),
    })
    (d / "plan.md").write_text("plan\n")
    (d / "protocol.md").write_text("protocol\n")
    (d / "studies").mkdir()
    return d


def test_absent_data_root_is_reported(tmp_path):
    vault = make_vault(tmp_path)
    pipeline_with_data(vault, "oldenlabs", tmp_path / "nowhere")
    found = codes_for(vault, "oldenlabs", "data-root-missing")
    assert len(found) == 1
    assert "nowhere" in found[0].message


def test_writable_raw_is_an_auto_finding(tmp_path):
    vault = make_vault(tmp_path)
    root = tmp_path / "data"
    (root / "raw").mkdir(parents=True)
    (root / "raw" / "MANIFEST.sha256").write_text("")
    pipeline_with_data(vault, "oldenlabs", root)
    found = codes_for(vault, "oldenlabs", "raw-writable")
    assert len(found) == 1
    assert found[0].level == "AUTO"


def test_missing_manifest_is_report_not_auto(tmp_path):
    vault = make_vault(tmp_path)
    root = tmp_path / "data"
    (root / "raw").mkdir(parents=True)
    pipeline_with_data(vault, "oldenlabs", root)
    found = codes_for(vault, "oldenlabs", "raw-unmanifested")
    assert len(found) == 1
    assert found[0].level == "REPORT"


def test_project_without_data_root_gets_no_data_findings(tmp_path):
    vault = make_vault(tmp_path)
    full_paper(vault, "alz-olf")
    assert codes_for(vault, "alz-olf", "data-root-missing") == []
    assert codes_for(vault, "alz-olf", "raw-unmanifested") == []


def test_provenance_without_a_code_commit_is_reported(tmp_path):
    vault = make_vault(tmp_path)
    d = full_pipeline(vault, "intellicage")
    study = d / "studies" / "verstreken" / "2026-07"
    study.mkdir(parents=True)
    (study / "study.json").write_text("{}\n")
    (study / "provenance.json").write_text(json.dumps({"version": "0.1.0"}) + "\n")
    found = codes_for(vault, "intellicage", "provenance-no-commit")
    assert len(found) == 1
    assert "verstreken/2026-07" in found[0].message


def test_provenance_with_a_code_commit_is_clean(tmp_path):
    vault = make_vault(tmp_path)
    d = full_pipeline(vault, "intellicage")
    study = d / "studies" / "verstreken" / "2026-07"
    study.mkdir(parents=True)
    (study / "provenance.json").write_text(
        json.dumps({"code_commit": "a1b2c3d"}) + "\n"
    )
    assert codes_for(vault, "intellicage", "provenance-no-commit") == []
