from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import check_vault
import new_project


def test_scaffolded_project_passes_the_vault_check(tmp_path, monkeypatch):
    """The scaffolder and check_vault must agree on the canonical paper shape."""
    vault = tmp_path / "neubrain"
    (vault / "projects").mkdir(parents=True)

    monkeypatch.setattr(sys, "argv", [
        "new_project.py", "--vault", str(vault), "--name", "demo",
    ])
    assert new_project.main() == 0

    findings = check_vault.collect(vault)
    assert findings == [], [f"{f.code}: {f.message}" for f in findings]
