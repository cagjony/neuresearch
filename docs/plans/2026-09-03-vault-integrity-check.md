# Vault Integrity Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `check_vault.py`, a read-only tool that reports every way the neubrain vault has drifted from the structure defined in the design spec.

**Architecture:** A project declares its kind in `project.json`. `project_config.py` loads and validates that file; `check_vault.py` walks `projects/*/`, runs a list of independent check functions against each, and renders every result into `logs/vault-status.md`. Each finding is classified `AUTO` (a later plan's `--fix` may repair it) or `REPORT` (needs a human). This plan builds **report mode only** — no repair, no file moves.

**Tech Stack:** Python 3.12, stdlib only for the tool. `pytest` for tests (dev-only dependency).

**Spec:** `neuresearch/docs/specs/2026-09-03-system-restructure-design.md`

## Global Constraints

- **Tools are stdlib-only.** No runtime third-party imports in `src/`. `reconcile.py` states this convention; follow it. `pytest` is a dev dependency and never imported by `src/`.
- **Interpreter is `/home/mouselab/.conda/envs/neuresearch/bin/python`, always by absolute path.** `conda activate neuresearch` does NOT change `python3` on this machine — the profile's PATH keeps `/opt/conda/envs/ece/bin/python3` (3.9) in front. This has already silently run a tool on the wrong interpreter once.
- **This tool never writes anything except `logs/vault-status.md`.** Same rule `reconcile.py` follows. No moves, no deletes, no edits, in any code path in this plan.
- **Exit codes:** `0` clean, `1` drift found, `2` tool error. On-disk state is identical either way.
- **Crash loudly on real errors; "nothing found" is a RESULT, not an error.** A project with no drift produces an empty findings list and exit 0, not an exception.
- **Never touch the paper subsystem.** `_library/`, `lit/`, `concepts/` are `reconcile.py`'s territory. This tool reads `projects/` only.
- Config format is **JSON** (`project.json`), not YAML.
- The two valid project types are `paper` and `pipeline`. There is no third type.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/project_config.py` | Load + validate one `project.json`. Knows the schema; knows nothing about checks. |
| `src/check_vault.py` | Discover projects, run checks, classify findings, render the report, set exit code. |
| `tests/test_project_config.py` | Schema loading and every rejection path. |
| `tests/test_check_vault.py` | Each check function against a synthetic vault in `tmp_path`. |

Checks live as small module-level functions in `check_vault.py`, each taking `(cfg, project_dir)` and returning `list[Finding]`. They are registered in one list so adding a check is one line.

---

### Task 1: Put pytest in the neuresearch environment

Today the only interpreter with `pytest` is `/opt/conda/envs/ece/bin/python3` (Python 3.9), while the tools run on `neuresearch` (3.12). Tests and tools must share one interpreter or the tests are not testing what ships.

**Files:**
- No source files. Environment change only.

**Interfaces:**
- Consumes: nothing.
- Produces: `/home/mouselab/.conda/envs/neuresearch/bin/python -m pytest` works. Every later task's test command depends on this.

- [ ] **Step 1: Confirm the problem before changing anything**

```bash
/home/mouselab/.conda/envs/neuresearch/bin/python -c "import pytest" 2>&1 | tail -1
```
Expected: `ModuleNotFoundError: No module named 'pytest'`

- [ ] **Step 2: Install pytest into the neuresearch env only**

```bash
/home/mouselab/.conda/envs/neuresearch/bin/python -m pip install pytest
```

- [ ] **Step 3: Verify it landed in the right env**

```bash
/home/mouselab/.conda/envs/neuresearch/bin/python -c "import pytest, sys; print(pytest.__version__, sys.prefix)"
```
Expected: a version number, and a prefix ending in `envs/neuresearch`. If the prefix says `ece`, stop — pip installed to the wrong environment.

- [ ] **Step 4: Run the existing test suite on the new interpreter**

```bash
cd /mnt/sysfs01/users/cagatay/code/neuresearch
/home/mouselab/.conda/envs/neuresearch/bin/python -m pytest tests/ -v
```
Expected: the three existing test files collect and pass. If any fail, they were previously only ever run on 3.9 — record the failures in the commit message and fix them before continuing, because every later task runs against this suite.

- [ ] **Step 5: Commit**

```bash
git add -A tests/
git commit -m "test: run the suite on the neuresearch interpreter

pytest was only present in the ece env (3.9) while the tools run on
neuresearch (3.12), so the suite was never exercising the shipped
interpreter. pytest is a dev dependency; src/ stays stdlib-only."
```

---

### Task 2: `project_config.py` — load and validate `project.json`

**Files:**
- Create: `src/project_config.py`
- Test: `tests/test_project_config.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `ProjectConfig` frozen dataclass with fields `name: str`, `type: str`, `status: str`, `path: Path`, `unit: str | None`, `code_repo: str | None`, `paper_repo: str | None`, `data_root: Path | None`, `source_studies: tuple[str, ...]`, `lane: str | None`
  - `ConfigError(Exception)`
  - `load(project_dir: Path) -> ProjectConfig`
  - `PROJECT_FILE = "project.json"`, `VALID_TYPES = frozenset({"paper", "pipeline"})`, `VALID_STATUS = frozenset({"active", "frozen", "archived"})`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_project_config.py`:

```python
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import project_config


def write(project_dir: Path, data: dict) -> Path:
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "project.json").write_text(json.dumps(data, indent=2) + "\n")
    return project_dir


GOOD_PIPELINE = {
    "schema": 1,
    "name": "oldenlabs",
    "type": "pipeline",
    "unit": "oldenlabs",
    "code_repo": "neu-oldenlabs",
    "data_root": "/data/olden",
    "lane": "oldenlabs/dacruz-study2",
    "status": "active",
}


def test_loads_a_valid_pipeline_config(tmp_path):
    d = write(tmp_path / "oldenlabs", GOOD_PIPELINE)
    cfg = project_config.load(d)
    assert cfg.name == "oldenlabs"
    assert cfg.type == "pipeline"
    assert cfg.unit == "oldenlabs"
    assert cfg.data_root == Path("/data/olden")
    assert cfg.source_studies == ()
    assert cfg.path == d


def test_optional_fields_default_to_none(tmp_path):
    d = write(tmp_path / "alz-olf", {
        "schema": 1, "name": "alz-olf", "type": "paper", "status": "active",
    })
    cfg = project_config.load(d)
    assert cfg.data_root is None
    assert cfg.paper_repo is None
    assert cfg.lane is None


def test_source_studies_becomes_a_tuple(tmp_path):
    d = write(tmp_path / "astro_atp", {
        "schema": 1, "name": "astro_atp", "type": "paper", "status": "active",
        "source_studies": ["oldenlabs/dacruz/study2"],
    })
    assert project_config.load(d).source_studies == ("oldenlabs/dacruz/study2",)


def test_missing_file_names_the_path(tmp_path):
    d = tmp_path / "nothing"
    d.mkdir()
    with pytest.raises(project_config.ConfigError) as e:
        project_config.load(d)
    assert "project.json" in str(e.value)
    assert str(d) in str(e.value)


def test_malformed_json_names_the_path(tmp_path):
    d = tmp_path / "broken"
    d.mkdir()
    (d / "project.json").write_text("{not json")
    with pytest.raises(project_config.ConfigError) as e:
        project_config.load(d)
    assert str(d / "project.json") in str(e.value)


def test_unknown_type_is_rejected_and_lists_valid_types(tmp_path):
    d = write(tmp_path / "x", {
        "schema": 1, "name": "x", "type": "pipeline+paper", "status": "active",
    })
    with pytest.raises(project_config.ConfigError) as e:
        project_config.load(d)
    assert "pipeline+paper" in str(e.value)
    assert "paper" in str(e.value) and "pipeline" in str(e.value)


def test_unknown_status_is_rejected(tmp_path):
    d = write(tmp_path / "x", {
        "schema": 1, "name": "x", "type": "paper", "status": "wip",
    })
    with pytest.raises(project_config.ConfigError):
        project_config.load(d)


def test_name_must_match_directory(tmp_path):
    d = write(tmp_path / "alz-olf", {
        "schema": 1, "name": "alz_olf", "type": "paper", "status": "active",
    })
    with pytest.raises(project_config.ConfigError) as e:
        project_config.load(d)
    assert "alz_olf" in str(e.value) and "alz-olf" in str(e.value)


def test_relative_data_root_is_rejected(tmp_path):
    d = write(tmp_path / "x", {
        "schema": 1, "name": "x", "type": "paper", "status": "active",
        "data_root": "../data",
    })
    with pytest.raises(project_config.ConfigError) as e:
        project_config.load(d)
    assert "absolute" in str(e.value).lower()


def test_unknown_schema_version_is_rejected(tmp_path):
    d = write(tmp_path / "x", {
        "schema": 99, "name": "x", "type": "paper", "status": "active",
    })
    with pytest.raises(project_config.ConfigError) as e:
        project_config.load(d)
    assert "99" in str(e.value)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd /mnt/sysfs01/users/cagatay/code/neuresearch
/home/mouselab/.conda/envs/neuresearch/bin/python -m pytest tests/test_project_config.py -v
```
Expected: collection error — `ModuleNotFoundError: No module named 'project_config'`.

- [ ] **Step 3: Write the implementation**

Create `src/project_config.py`:

```python
#!/usr/bin/env python3
"""
project_config.py
=================
Load and validate a neubrain project's ``project.json``.

Every project under ``neubrain/projects/`` declares what kind of thing it is.
This module knows the schema and nothing else — it performs no filesystem
checks beyond reading the one file, and it never writes.

Requires: Python 3.10+ (stdlib only).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_FILE = "project.json"
SCHEMA_VERSION = 1
VALID_TYPES = frozenset({"paper", "pipeline"})
VALID_STATUS = frozenset({"active", "frozen", "archived"})


class ConfigError(Exception):
    """A project.json is missing, malformed, or violates the schema."""


@dataclass(frozen=True)
class ProjectConfig:
    name: str
    type: str
    status: str
    path: Path
    unit: str | None = None
    code_repo: str | None = None
    paper_repo: str | None = None
    data_root: Path | None = None
    source_studies: tuple[str, ...] = ()
    lane: str | None = None


def load(project_dir: Path) -> ProjectConfig:
    """Read ``project_dir/project.json``. Raise ConfigError on any violation."""
    path = project_dir / PROJECT_FILE
    if not path.is_file():
        raise ConfigError(f"no {PROJECT_FILE} in {project_dir}")

    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{path} must contain a JSON object")

    schema = raw.get("schema")
    if schema != SCHEMA_VERSION:
        raise ConfigError(
            f"{path}: schema {schema!r} is not supported "
            f"(this tool understands schema {SCHEMA_VERSION})"
        )

    name = raw.get("name")
    if name != project_dir.name:
        raise ConfigError(
            f"{path}: name {name!r} does not match its directory "
            f"{project_dir.name!r}"
        )

    ptype = raw.get("type")
    if ptype not in VALID_TYPES:
        raise ConfigError(
            f"{path}: type {ptype!r} is not one of "
            f"{', '.join(sorted(VALID_TYPES))}"
        )

    status = raw.get("status")
    if status not in VALID_STATUS:
        raise ConfigError(
            f"{path}: status {status!r} is not one of "
            f"{', '.join(sorted(VALID_STATUS))}"
        )

    data_root = raw.get("data_root")
    if data_root is not None:
        data_root = Path(data_root)
        if not data_root.is_absolute():
            raise ConfigError(
                f"{path}: data_root {str(data_root)!r} must be an absolute path"
            )

    studies = raw.get("source_studies") or []
    if not isinstance(studies, list):
        raise ConfigError(f"{path}: source_studies must be a list")

    return ProjectConfig(
        name=name,
        type=ptype,
        status=status,
        path=project_dir,
        unit=raw.get("unit"),
        code_repo=raw.get("code_repo"),
        paper_repo=raw.get("paper_repo"),
        data_root=data_root,
        source_studies=tuple(studies),
        lane=raw.get("lane"),
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
/home/mouselab/.conda/envs/neuresearch/bin/python -m pytest tests/test_project_config.py -v
```
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add src/project_config.py tests/test_project_config.py
git commit -m "feat: project.json schema loader

Validates schema version, type, status, name-matches-directory, and that
data_root is absolute. Rejects the retired pipeline+paper type by listing
the two valid ones."
```

---

### Task 3: `check_vault.py` — discovery, findings, report, exit codes

**Files:**
- Create: `src/check_vault.py`
- Test: `tests/test_check_vault.py`

**Interfaces:**
- Consumes: `project_config.load`, `project_config.ConfigError`, `ProjectConfig`.
- Produces:
  - `Finding` frozen dataclass: `level: str` (`"AUTO"` or `"REPORT"`), `project: str`, `code: str`, `message: str`
  - `discover(vault: Path) -> list[Path]` — sorted `projects/*/` directories
  - `CHECKS: list` — registry of check functions, each `(cfg, project_dir) -> list[Finding]`
  - `collect(vault: Path) -> list[Finding]`
  - `render(findings: list[Finding]) -> str`
  - `main() -> int`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_check_vault.py`:

```python
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


def test_render_says_clean_when_there_are_no_findings(tmp_path):
    text = check_vault.render([])
    assert "no drift" in text.lower()


def test_render_groups_by_project_and_shows_both_levels(tmp_path):
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
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
/home/mouselab/.conda/envs/neuresearch/bin/python -m pytest tests/test_check_vault.py -v
```
Expected: collection error — `ModuleNotFoundError: No module named 'check_vault'`.

- [ ] **Step 3: Write the implementation**

Create `src/check_vault.py`:

```python
#!/usr/bin/env python3
"""
check_vault.py
==============
READ-ONLY structural integrity check for the neubrain vault's projects/ tree.

    python check_vault.py --vault /path/to/neubrain

Reports every way a project has drifted from the structure defined in
docs/specs/2026-09-03-system-restructure-design.md, classified as:

  AUTO    mechanically repairable, no judgement needed
  REPORT  needs a human; never repaired automatically

What it never does (by design):
  - it does not delete, move, or edit anything
  - the ONLY file it writes is logs/vault-status.md
  - it does not read _library/, lit/ or concepts/ — that is reconcile.py's job

Exit code: 0 clean, 1 drift found, 2 tool error.

Requires: Python 3.10+ (stdlib only).
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import project_config
from project_config import ConfigError, ProjectConfig

AUTO = "AUTO"
REPORT = "REPORT"


@dataclass(frozen=True)
class Finding:
    level: str
    project: str
    code: str
    message: str


def discover(vault: Path) -> list[Path]:
    """Every directory directly under projects/, sorted by name."""
    root = vault / "projects"
    return sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.name)


# --- checks -----------------------------------------------------------------
# Each takes (cfg, project_dir) and returns a list of Finding.
# Registered in CHECKS below; adding a check is one line there.

CHECKS: list = []


def collect(vault: Path) -> list[Finding]:
    findings: list[Finding] = []
    for project_dir in discover(vault):
        try:
            cfg = project_config.load(project_dir)
        except ConfigError as exc:
            findings.append(Finding(
                REPORT, project_dir.name, "no-project-config", str(exc),
            ))
            continue
        for check in CHECKS:
            findings.extend(check(cfg, project_dir))
    return findings


def render(findings: list[Finding]) -> str:
    lines = [
        "# Vault status",
        "",
        f"Generated {date.today().isoformat()} by `check_vault.py`. "
        "This file is GENERATED — do not hand-edit.",
        "",
    ]
    if not findings:
        lines += ["**Clean.** No drift found in any project.", ""]
        return "\n".join(lines)

    n_auto = sum(1 for f in findings if f.level == AUTO)
    n_report = sum(1 for f in findings if f.level == REPORT)
    lines += [
        f"**{len(findings)} findings** — {n_auto} {AUTO}, {n_report} {REPORT}.",
        "",
        f"`{AUTO}` is mechanically repairable. `{REPORT}` needs a human and is "
        "never repaired automatically.",
        "",
    ]

    by_project: dict[str, list[Finding]] = {}
    for f in findings:
        by_project.setdefault(f.project, []).append(f)

    for project in sorted(by_project):
        lines += [f"## {project}", ""]
        for f in sorted(by_project[project], key=lambda f: (f.level, f.code)):
            lines.append(f"- `{f.level}` **{f.code}** — {f.message}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="read-only structural check of the neubrain projects/ tree")
    ap.add_argument("--vault", required=True, type=Path,
                    help="path to the neubrain vault root")
    args = ap.parse_args()

    if not (args.vault / "projects").is_dir():
        print(f"no projects/ under {args.vault} — is this the vault root?",
              file=sys.stderr)
        return 2

    findings = collect(args.vault)

    logs = args.vault / "logs"
    logs.mkdir(exist_ok=True)
    report = logs / "vault-status.md"
    report.write_text(render(findings))

    print(f"{len(findings)} findings; wrote {report}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
/home/mouselab/.conda/envs/neuresearch/bin/python -m pytest tests/test_check_vault.py -v
```
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add src/check_vault.py tests/test_check_vault.py
git commit -m "feat: check_vault.py skeleton — discovery, findings, report, exit codes

Report-only. Writes logs/vault-status.md and nothing else, asserted by a
test that diffs the vault's file set before and after a run."
```

---

### Task 4: Required-shape checks per project type

**Files:**
- Modify: `src/check_vault.py` (add `check_required_shape`, register in `CHECKS`)
- Modify: `tests/test_check_vault.py` (append)

**Interfaces:**
- Consumes: `Finding`, `AUTO`, `REPORT`, `CHECKS`, `ProjectConfig`.
- Produces: `check_required_shape(cfg, project_dir) -> list[Finding]`, emitting code `missing-required` (REPORT) per absent entry, and `REQUIRED_SHAPE: dict[str, list[str]]`.

Required entries, from the spec. A trailing `/` means a directory; `draft/manuscript.*` is a glob satisfied by either extension:

| type | entries |
|---|---|
| `paper` | `plan.md`, `papers.txt`, `archive/`, `draft/`, `draft/manuscript.*`, `draft/references.bib` |
| `pipeline` | `plan.md`, `protocol.md`, `studies/` |

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_check_vault.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
/home/mouselab/.conda/envs/neuresearch/bin/python -m pytest tests/test_check_vault.py -k required -v
```
Expected: FAIL — `AttributeError` or assertions failing because no shape check is registered yet.

- [ ] **Step 3: Write the implementation**

In `src/check_vault.py`, insert above `CHECKS: list = []`:

```python
REQUIRED_SHAPE: dict[str, list[str]] = {
    "paper": [
        "plan.md",
        "papers.txt",
        "archive/",
        "draft/",
        "draft/manuscript.*",
        "draft/references.bib",
    ],
    "pipeline": [
        "plan.md",
        "protocol.md",
        "studies/",
    ],
}


def _satisfied(project_dir: Path, entry: str) -> bool:
    if entry.endswith("/"):
        return (project_dir / entry.rstrip("/")).is_dir()
    if "*" in entry:
        parent, _, pattern = entry.rpartition("/")
        base = project_dir / parent if parent else project_dir
        return base.is_dir() and any(p.is_file() for p in base.glob(pattern))
    return (project_dir / entry).is_file()


def check_required_shape(cfg: ProjectConfig, project_dir: Path) -> list[Finding]:
    """Every entry the project's declared type requires must be present."""
    return [
        Finding(REPORT, cfg.name, "missing-required", f"{entry} is missing")
        for entry in REQUIRED_SHAPE[cfg.type]
        if not _satisfied(project_dir, entry)
    ]
```

Then replace `CHECKS: list = []` with:

```python
CHECKS: list = [
    check_required_shape,
]
```

- [ ] **Step 4: Run the full suite to verify it passes**

```bash
/home/mouselab/.conda/envs/neuresearch/bin/python -m pytest tests/ -v
```
Expected: all tests pass, including Task 3's.

- [ ] **Step 5: Commit**

```bash
git add src/check_vault.py tests/test_check_vault.py
git commit -m "feat: required-shape check per project type

paper needs draft/manuscript.* (either extension); pipeline needs
studies/. A file where a directory is required is reported, not ignored."
```

---

### Task 5: Drift checks — loose scripts, stray manuscripts, unrecorded submissions

These are the three symptoms the spec names as evidence of decay. All are `REPORT`: each needs a judgement the tool cannot make.

**Files:**
- Modify: `src/check_vault.py` (three checks + registration)
- Modify: `tests/test_check_vault.py` (append)

**Interfaces:**
- Consumes: `Finding`, `REPORT`, `CHECKS`, `ProjectConfig`.
- Produces: `check_loose_scripts`, `check_stray_manuscript`, `check_submissions_recorded`, emitting codes `loose-script`, `stray-manuscript`, `unrecorded-submission`.

Rules:
- **`loose-script`** — any `*.py` directly at the project root. Scripts belong in `tools/`. One finding per file.
- **`stray-manuscript`** — any `manuscript.*` outside `draft/`. There is exactly one live draft.
- **`unrecorded-submission`** — a directory under `submissions/` whose name does not appear in `SUBMISSIONS.md`. A missing `SUBMISSIONS.md` with submissions present is itself the finding.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_check_vault.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
/home/mouselab/.conda/envs/neuresearch/bin/python -m pytest tests/test_check_vault.py -k "loose or stray or submission" -v
```
Expected: FAIL — the codes are never emitted, so every list is empty.

- [ ] **Step 3: Write the implementation**

Add to `src/check_vault.py` above `CHECKS`:

```python
def check_loose_scripts(cfg: ProjectConfig, project_dir: Path) -> list[Finding]:
    """A .py at the project root is a one-off nobody decided to keep."""
    return [
        Finding(REPORT, cfg.name, "loose-script",
                f"{p.name} sits at the project root; scripts belong in tools/")
        for p in sorted(project_dir.glob("*.py"))
    ]


def check_stray_manuscript(cfg: ProjectConfig, project_dir: Path) -> list[Finding]:
    """There is exactly one live manuscript, and it lives in draft/."""
    if cfg.type != "paper":
        return []
    draft = project_dir / "draft"
    findings = []
    for path in sorted(project_dir.rglob("manuscript.*")):
        if path.suffix not in {".tex", ".md"} or not path.is_file():
            continue
        if draft in path.parents:
            continue
        rel = path.relative_to(project_dir)
        findings.append(Finding(
            REPORT, cfg.name, "stray-manuscript",
            f"{rel} is outside draft/; there is one live manuscript",
        ))
    return findings


def check_submissions_recorded(cfg: ProjectConfig,
                               project_dir: Path) -> list[Finding]:
    """Every submissions/ folder needs a SUBMISSIONS.md row naming it."""
    submissions = project_dir / "submissions"
    if not submissions.is_dir():
        return []
    folders = sorted(p.name for p in submissions.iterdir() if p.is_dir())
    if not folders:
        return []

    record = project_dir / "SUBMISSIONS.md"
    if not record.is_file():
        return [Finding(
            REPORT, cfg.name, "unrecorded-submission",
            f"{len(folders)} submission folder(s) but no SUBMISSIONS.md",
        )]

    text = record.read_text()
    return [
        Finding(REPORT, cfg.name, "unrecorded-submission",
                f"submissions/{name} has no row in SUBMISSIONS.md")
        for name in folders if name not in text
    ]
```

Extend the registry:

```python
CHECKS: list = [
    check_required_shape,
    check_loose_scripts,
    check_stray_manuscript,
    check_submissions_recorded,
]
```

- [ ] **Step 4: Run the full suite to verify it passes**

```bash
/home/mouselab/.conda/envs/neuresearch/bin/python -m pytest tests/ -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/check_vault.py tests/test_check_vault.py
git commit -m "feat: drift checks for loose scripts, stray manuscripts, unrecorded submissions

All REPORT: each needs a judgement the tool cannot make. Catches the nine
patch*.py in alz-olf, the manuscript living in three places in astro_atp,
and a submissions/ folder with no row."
```

---

### Task 6: Data-root checks

**Files:**
- Modify: `src/check_vault.py` (two checks + registration)
- Modify: `tests/test_check_vault.py` (append)

**Interfaces:**
- Consumes: `Finding`, `AUTO`, `REPORT`, `CHECKS`, `ProjectConfig`.
- Produces: `check_data_root`, `check_provenance_commit`, emitting codes `data-root-missing` (REPORT), `raw-writable` (AUTO), `raw-unmanifested` (REPORT), `provenance-no-commit` (REPORT).

Design note carried from the spec: a **missing `MANIFEST.sha256` is REPORT, not AUTO.** Generating one automatically would bless whatever state `raw/` happens to be in as authoritative — the opposite of what the manifest is for. A human confirms raw is correct, then it is hashed.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_check_vault.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
/home/mouselab/.conda/envs/neuresearch/bin/python -m pytest tests/test_check_vault.py -k "data or raw or provenance" -v
```
Expected: FAIL — none of the codes are emitted.

- [ ] **Step 3: Write the implementation**

Add to `src/check_vault.py` above `CHECKS` (add `import json` and `import os` to the imports at the top):

```python
def check_data_root(cfg: ProjectConfig, project_dir: Path) -> list[Finding]:
    """The declared data root must exist, with a protected, manifested raw/."""
    if cfg.data_root is None:
        return []
    if not cfg.data_root.is_dir():
        return [Finding(REPORT, cfg.name, "data-root-missing",
                        f"data_root {cfg.data_root} does not exist")]

    raw = cfg.data_root / "raw"
    if not raw.is_dir():
        return [Finding(REPORT, cfg.name, "data-root-missing",
                        f"{raw} does not exist")]

    findings = []
    if os.access(raw, os.W_OK):
        findings.append(Finding(
            AUTO, cfg.name, "raw-writable",
            f"{raw} is writable; raw data must be chmod a-w",
        ))
    if not (raw / "MANIFEST.sha256").is_file():
        findings.append(Finding(
            REPORT, cfg.name, "raw-unmanifested",
            f"{raw} has no MANIFEST.sha256 — confirm raw is in its intended "
            "state, then hash it; generating one now would bless whatever is "
            "there",
        ))
    return findings


def check_provenance_commit(cfg: ProjectConfig,
                            project_dir: Path) -> list[Finding]:
    """Every study run must record the code commit that produced it."""
    studies = project_dir / "studies"
    if not studies.is_dir():
        return []
    findings = []
    for prov in sorted(studies.rglob("provenance.json")):
        try:
            data = json.loads(prov.read_text())
        except json.JSONDecodeError:
            findings.append(Finding(
                REPORT, cfg.name, "provenance-no-commit",
                f"{prov.relative_to(project_dir)} is not valid JSON",
            ))
            continue
        if not data.get("code_commit"):
            findings.append(Finding(
                REPORT, cfg.name, "provenance-no-commit",
                f"{prov.parent.relative_to(studies)} records no code_commit",
            ))
    return findings
```

Extend the registry:

```python
CHECKS: list = [
    check_required_shape,
    check_loose_scripts,
    check_stray_manuscript,
    check_submissions_recorded,
    check_data_root,
    check_provenance_commit,
]
```

- [ ] **Step 4: Run the full suite to verify it passes**

```bash
/home/mouselab/.conda/envs/neuresearch/bin/python -m pytest tests/ -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/check_vault.py tests/test_check_vault.py
git commit -m "feat: data-root and provenance checks

A missing MANIFEST.sha256 is REPORT, not AUTO: generating one would bless
whatever state raw/ happens to be in, which is the opposite of its purpose."
```

---

### Task 7: Run it against the real vault and record the baseline

The spec's migration step 2 is explicit: run the check and **record the failures without fixing them**. That report is the input to Plan 2.

**Files:**
- Create: `docs/plans/2026-09-03-vault-baseline.md`

**Interfaces:**
- Consumes: the finished `check_vault.py`.
- Produces: a committed baseline report that Plan 2 works through.

- [ ] **Step 1: Confirm the vault tree is clean before touching it**

```bash
cd /mnt/sysfs01/users/cagatay/code/neubrain && git status --short
```
Expected: no changes to `projects/`. If dirty, stop and hand back to the author — the baseline must describe a known state.

- [ ] **Step 2: Run the check against the real vault**

```bash
cd /mnt/sysfs01/users/cagatay/code/neuresearch
/home/mouselab/.conda/envs/neuresearch/bin/python src/check_vault.py \
  --vault /mnt/sysfs01/users/cagatay/code/neubrain
```
Expected: exit 1, with a large finding count. Every one of the 8 projects lacks `project.json`, so expect at minimum 8 `no-project-config` findings and no others — the other checks are skipped for projects whose config will not load.

- [ ] **Step 3: Copy the report into the plan directory as the baseline**

```bash
cp /mnt/sysfs01/users/cagatay/code/neubrain/logs/vault-status.md \
   docs/plans/2026-09-03-vault-baseline.md
```

- [ ] **Step 4: Verify the vault itself was not modified beyond the report**

```bash
cd /mnt/sysfs01/users/cagatay/code/neubrain && git status --short
```
Expected: only `logs/vault-status.md` appears. Anything else means a check wrote where it must not — stop and fix before continuing.

- [ ] **Step 5: Commit the baseline**

```bash
cd /mnt/sysfs01/users/cagatay/code/neuresearch
git add docs/plans/2026-09-03-vault-baseline.md
git commit -m "docs: baseline vault-status report before any migration

Recorded per migration step 2: run the check, record the failures, fix
nothing. This is the worklist Plan 2 works through."
```

---

## What this plan does NOT do

Deliberately deferred, each to its own plan:

- **Plan 2 — the migration.** Writing the 8 `project.json` files, restructuring units to `studies/<client>/<study>/`, moving paper projects to `draft/`, relocating `submissions/2026-08-14-nonlinear-science`, establishing the data root. Driven by Task 7's baseline.
- **Plan 3 — state and lanes.** Splitting `HANDOFF.md` into a router plus per-project `STATE.md`, `merge_manifest.py`, the first worktree lane, `check_vault.py --fix`, and the `neubrain-vault` skill.

`--fix` is deliberately absent here. Repair should be written against the structure the migration produces, not against the structure as it is today.
