Tooling, not notes: code that fetches open-access papers into the neubrain vault.

Scope: Open-access only via Europe PMC + Unpaywall. Reconcile is scoped to the paper subsystem. Requested papers are copied into each project's `papers/` folder (copy model, NFS-safe — no symlinks).

## Setup

This project runs in a dedicated `neuresearch` conda env:

```
conda env create -f environment.yml   # first time
conda activate neuresearch            # each session
```

All commands below run inside this env. If you don't activate it, prefix each command with `conda run -n neuresearch`, e.g.:

```
conda run -n neuresearch python3 src/fetch_papers.py ...
```
