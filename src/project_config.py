#!/usr/bin/env python3
"""
project_config.py
=================
Load and validate a neubrain project's ``project.json``.

Every project under ``neubrain/projects/`` declares what kind of thing it is,
so that tools can check its shape instead of guessing from its contents. See
docs/specs/2026-09-03-system-restructure-design.md §1.

    {
      "schema": 1,
      "name": "oldenlabs",
      "type": "pipeline",
      "unit": "oldenlabs",
      "code_repo": "neu-oldenlabs",
      "data_root": "/mnt/sysfs01/users/cagatay/data",
      "lane": "oldenlabs/dacruz-study2",
      "status": "active"
    }

This module knows the schema and nothing else: it reads one file, performs no
other filesystem checks, and never writes.

JSON rather than YAML because the vault's other configs (manifest.json,
study.json, provenance.json) are JSON and this stays stdlib-only.

Requires: Python 3.10+ (stdlib only).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
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
