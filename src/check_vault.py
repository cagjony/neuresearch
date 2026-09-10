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
