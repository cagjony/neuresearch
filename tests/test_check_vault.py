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
