#!/usr/bin/env python3
"""
log_writer.py
=============
Append-only Markdown fetch log for the neubrain vault.

This is the human/Claude-readable VIEW of what fetch_papers.py did. The
machine source of truth stays _library/manifest.json; this file is a printed
statement projected from those actions, never the ledger itself.

Design:
  - logs/fetch-log.md is APPEND-ONLY: one dated block per fetch run. Old
    entries are never rewritten, so it is a durable history of "which paper,
    from which source, when".
  - it is generated, not hand-edited (the vault AGENTS.md says so).

Usage from fetch_papers.py:
    from log_writer import FetchLog
    log = FetchLog(vault_path)            # vault root, contains logs/
    log.record(stem="fujii2017", source="europepmc-jats",
               title="...", doi="10.1038/...")
    log.gap(raw="10.xxxx/paywalled", reason="no legal OA copy")
    log.flush()                            # writes one dated block, appends

If you prefer the toolbox to stay vault-agnostic, pass the logs dir directly:
    FetchLog(logs_dir=Path("/path/to/neubrain/logs"))
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class _Row:
    stem: str
    source: str
    title: str = ""
    doi: str = ""


@dataclass
class _Gap:
    raw: str
    reason: str


class FetchLog:
    def __init__(self, vault: Path | None = None, logs_dir: Path | None = None):
        if logs_dir is not None:
            self.logs = logs_dir
        elif vault is not None:
            self.logs = vault / "logs"
        else:
            raise ValueError("FetchLog needs either vault or logs_dir")
        self.logs.mkdir(parents=True, exist_ok=True)
        self.path = self.logs / "fetch-log.md"
        self._fetched: list[_Row] = []
        self._relinked: list[_Row] = []
        self._gaps: list[_Gap] = []

    # --- collect during a run --- #
    def record(self, stem: str, source: str, title: str = "", doi: str = "") -> None:
        self._fetched.append(_Row(stem, source, title, doi))

    def relink(self, stem: str, project: str) -> None:
        self._relinked.append(_Row(stem, f"already-had → linked into {project}"))

    def gap(self, raw: str, reason: str) -> None:
        self._gaps.append(_Gap(raw, reason))

    # --- write one dated block, appended --- #
    def flush(self, project: str | None = None) -> None:
        if not (self._fetched or self._relinked or self._gaps):
            return

        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        out: list[str] = []

        # write a one-time header if the file is new
        if not self.path.exists():
            out += [
                "# Fetch log",
                "",
                "> Append-only history written by `fetch_papers.py`. "
                "Do not hand-edit. The machine record is `_library/manifest.json`.",
                "",
            ]

        scope = f" — project `{project}`" if project else ""
        out.append(f"## {ts}{scope}")
        out.append("")

        if self._fetched:
            out.append(f"**Fetched ({len(self._fetched)}):**")
            out.append("")
            for r in self._fetched:
                doi = f" · {r.doi}" if r.doi else ""
                ttl = f" — {r.title}" if r.title else ""
                out.append(f"- `{r.stem}` ← {r.source}{doi}{ttl}")
            out.append("")

        if self._relinked:
            out.append(f"**Re-linked ({len(self._relinked)}):**")
            out.append("")
            for r in self._relinked:
                out.append(f"- `{r.stem}` — {r.source}")
            out.append("")

        if self._gaps:
            out.append(f"**Gaps ({len(self._gaps)}) — need manual / institutional access:**")
            out.append("")
            for g in self._gaps:
                out.append(f"- `{g.raw}` — {g.reason}")
            out.append("")

        block = "\n".join(out)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(block + "\n")

        # reset so the same instance can be reused
        self._fetched.clear()
        self._relinked.clear()
        self._gaps.clear()
