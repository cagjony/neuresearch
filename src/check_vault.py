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

Exit code: 0 clean, 1 drift found, 2 tool error. The on-disk state is
identical either way.

Requires: Python 3.10+ (stdlib only).
"""
from __future__ import annotations

import argparse
import json
import os
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
    # a knowledge base (e.g. neuvsc): what we read and what is verified
    "reference": [
        "STATE.md",
        "reading.md",
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


CHECKS: list = [
    check_required_shape,
    check_loose_scripts,
    check_stray_manuscript,
    check_submissions_recorded,
    check_data_root,
    check_provenance_commit,
]


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
