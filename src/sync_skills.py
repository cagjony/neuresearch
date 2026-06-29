#!/usr/bin/env python3
"""
sync_skills.py  —  verify + deploy skills
=========================================
The source of truth for skills is this repo's `skills/` directory. Claude Code
loads skills from `~/.claude/skills/`. This deploys the former to the latter as
REAL COPIES (never symlinks — the lab filesystem is NFS), and can audit drift
without touching anything.

    python sync_skills.py            # deploy: copy skills/ -> ~/.claude/skills/
    python sync_skills.py --check    # read-only audit: report drift, copy nothing

Each immediate sub-directory of `skills/` is one skill. Status per skill:
    new      — not yet in the target
    updated  — present but differs from source
    in-sync  — identical

Default mode makes the target match the source (overwriting changed skills) and is
idempotent. --check changes nothing and exits non-zero if any skill is out of sync,
so it is usable as a gate.

If `~/.claude/skills/` does not exist (e.g. a fresh machine where Claude Code has
not run yet) it does NOT crash: it warns and exits non-zero, telling you to create
it (or to let Claude Code create it on first run).

Requires: Python 3.10+ (stdlib only).
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parent.parent / "skills"
TARGET = Path.home() / ".claude" / "skills"


def skill_dirs(source: Path) -> list[Path]:
    return sorted(p for p in source.iterdir() if p.is_dir() and not p.name.startswith("."))


def _files(root: Path) -> dict[Path, Path]:
    return {p.relative_to(root): p for p in root.rglob("*") if p.is_file()}


def compare(src_dir: Path, dst_dir: Path) -> str:
    """Return 'new' | 'updated' | 'in-sync' for one skill dir."""
    if not dst_dir.exists():
        return "new"
    src, dst = _files(src_dir), _files(dst_dir)
    if set(src) != set(dst):
        return "updated"
    for rel, sp in src.items():
        if sp.read_bytes() != dst[rel].read_bytes():
            return "updated"
    return "in-sync"


def deploy(src_dir: Path, dst_dir: Path) -> None:
    """Replace dst_dir with a fresh real-file copy of src_dir."""
    if dst_dir.exists():
        shutil.rmtree(dst_dir)
    shutil.copytree(src_dir, dst_dir)  # copies file contents, not symlinks


def main() -> int:
    ap = argparse.ArgumentParser(description="Deploy/verify skills -> ~/.claude/skills/.")
    ap.add_argument("--check", action="store_true",
                    help="read-only: report drift, copy nothing (non-zero exit if drift)")
    ap.add_argument("--source", type=Path, default=SOURCE, help="skills source dir")
    ap.add_argument("--target", type=Path, default=TARGET, help="deploy target dir")
    args = ap.parse_args()

    if not args.source.is_dir():
        print(f"WARN: no skills source at {args.source} — nothing to sync.")
        return 1
    skills = skill_dirs(args.source)
    if not skills:
        print(f"WARN: {args.source} has no skill directories — nothing to sync.")
        return 1

    # the target ROOT must exist; Claude Code creates ~/.claude/skills on first run
    if not args.target.exists():
        print(f"WARN: target skills directory does not exist: {args.target}")
        print("      Claude Code creates it on first run; or create it yourself:")
        print(f"          mkdir -p {args.target}")
        print("      Then re-run to deploy. Nothing was copied.")
        return 1

    rows = []
    drift = False
    for sd in skills:
        td = args.target / sd.name
        status = compare(sd, td)
        if status != "in-sync":
            drift = True
            if not args.check:
                deploy(sd, td)
        rows.append((sd.name, status))

    w = max((len(n) for n, _ in rows), default=5)
    mode = "check (read-only)" if args.check else "deploy"
    print(f"sync_skills [{mode}]  {args.source}  ->  {args.target}\n")
    print(f"{'skill':<{w}}  status")
    print(f"{'-'*w}  {'-'*8}")
    for name, status in rows:
        shown = status
        if not args.check and status != "in-sync":
            shown = f"{status} -> copied"
        print(f"{name:<{w}}  {shown}")

    n_drift = sum(1 for _, s in rows if s != "in-sync")
    if args.check:
        print(f"\n{n_drift} of {len(rows)} skill(s) out of sync."
              if drift else f"\nAll {len(rows)} skill(s) in sync.")
        return 1 if drift else 0
    print(f"\nDeployed {n_drift} change(s); {len(rows) - n_drift} already in sync.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
