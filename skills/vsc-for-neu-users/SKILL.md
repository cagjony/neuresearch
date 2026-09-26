---
name: vsc-for-neu-users
description: Use when working on the VSC (Vlaams Supercomputer Centrum) KU Leuven Tier-2 clusters — Genius, wICE, Mindwell, login.hpc.kuleuven.be — for the Neurophysiology Expertise Unit; when a command fails with "Disk quota exceeded" in $VSC_HOME, a module or tool seems missing, choosing where data, containers or caches go ($VSC_HOME, $VSC_DATA, $VSC_SCRATCH, /tmp, manGO), submitting SLURM jobs to the BIG nodes (lp_big_* accounts), moving data with Globus, checking credits, or running the neu2p Nextflow + Apptainer pipeline on VSC.
---

# VSC (KU Leuven) for NEU users

## Overview

Facts about the VSC that were verified in the official docs, the VSC training
slides, or in practice. Cite a source path when you rely on a rule. **Do not
answer VSC questions from memory:** tested without this skill, an agent got the
quota cause, the Apptainer cache, the accounts, the purge rule and the credit
command wrong.

manGO portal: https://mango.vscentrum.be/.

Where the knowledge lives:
- **Sources we READ** (official docs, training slides, lab-practice files), pinned to the commit we read:
  `neubrain/projects/neuvsc/reading.md`. The clones are in `code/hpcleuven/` (slide text in `_text/`);
  the lab files are in `neubrain/projects/neuvsc/archive/`.
- **What we WRITE for colleagues:** the onboarding guide, `github.com/neurophysiology-expertise-unit/neuvsc`
  (local clone `code/neuvsc/README.md`). When a fact changes, fix it there and here in the same session.
- **What is verified vs pending:** `neubrain/projects/neuvsc/STATE.md`.

Cited `*.rst` paths are relative to `code/hpcleuven/VscDocumentation/source/`; "HPCintro slide N" is `code/hpcleuven/_text/HPCintro.txt`; "BIG handbook" is `neubrain/projects/neuvsc/archive/BIG Nodes - Handbook.md`.

## Where things go

| Location | Quota | Rules | Put here |
|---|---|---|---|
| `$VSC_HOME` `/user/leuven/...` | **3 GB** | backed up, all clusters | only dotfiles, `~/.ssh`, `~/.bashrc` |
| `$VSC_DATA` `/data/leuven/...` | 75 GB | backed up (snapshots), all clusters | tools, venvs, `.sif` images, `NXF_HOME`, `.vscode-server` |
| `$VSC_SCRATCH` | 500 GB | **files not *accessed* for 30 days are deleted**, no backup; Lustre on Genius/wICE, GPFS on Mindwell | raw data for a run, work dirs, results until copied out |
| `/tmp` (node scratch) | 600 GB on wICE | wiped at job end; **avoid on login nodes** (10 GB, needed by the OS) | Apptainer cache/tmp **inside jobs** |
| manGO / NERF file server | — | long-term | raw data and final results |
| GitHub | — | — | code (not shared storage) |

Sources: `leuven/tier2_hardware/kuleuven_storage.rst`, `data/data_management_guidelines.rst`, HPCintro slide 25.

## Quick reference: failures seen in practice

- **"Disk quota exceeded" on `~/.nextflow` or `~/.globus`:** home is full. Run `du -sh ~/.[!.]* | sort -h`. The usual cause is `~/.vscode-server` (GBs). Move it and symlink it, keeping the same name at both ends (`compute/portal/ondemand/vscode-server.rst`):
  `mv ~/.vscode-server $VSC_DATA/.vscode-server && ln -s $VSC_DATA/.vscode-server ~/.vscode-server`.
  Then set `export NXF_HOME=$VSC_DATA/.nextflow` (never scratch: it is purged).
- **A tool looks missing** (`which`/`module avail` show nothing): run `module spider <Name>`. Modules are per cluster tree; e.g. `Nextflow/25.04.8` needs a `cluster/...` module (the login default works). Globus CLI has no KU Leuven module; install it in a venv in `$VSC_DATA` (`globus/cli.rst`).
- **Apptainer:** set the cache/tmp to `/tmp/$USER/...` only when `$SLURM_JOB_ID` is set. Build and run containers on compute nodes (`compute/software/installing_software/containers.rst`). Keep `.sif` files in `$VSC_DATA`.
- **Login node:** no heavy or long work (`compute/jobs/index.rst`). Start the Nextflow head from the wICE `interactive` partition, which is free of credits (`leuven/wice_quick_start.rst`). **Unverified:** which account `interactive` accepts; BIG accounts are tied to their own partitions, so try `wicedefaultslurmaccount` if `lp_big_*` is rejected.
- **Staging data into scratch:** use `cp` (not `-a`) or Globus. `mv` and `rsync -a` keep an old access time, so the file can be purged at once. Copy results out when done.
- **Match scratch to cluster:** wICE/Genius jobs use Lustre, Mindwell jobs use GPFS; admins cancel jobs that don't, without notice.

## BIG-node accounts (from the BIG handbook)

| Cluster | Hardware | `-A` account | `-p` partition |
|---|---|---|---|
| wICE | CPU bigmem | `lp_big_wice_cpu` | `dedicated_big_bigmem` |
| wICE | A100 GPU | `lp_big_wice_gpu` | `dedicated_big_gpu` |
| wICE | H100 GPU | `lp_big_wice_gpu_h100` | `dedicated_big_gpu_h100` |
| Mindwell | CPU bigmem | `lp_big_mindwell_cpu` | `dedicated_big_bigmem` |
| Mindwell | B200 GPU | `lp_big_mindwell_gpu_b200` | `dedicated_big_gpu_b200` |

Always add `--clusters=wice` or `--clusters=mindwell`. An account works only with its own partition. Access is requested via account.vscentrum.be → New/Join Group; check it with `groups` and `sacctmgr show assoc user=$USER`.

**Credits:** `sam-balance`. A full wICE GPU node costs 45,000 credits/h (billed pro rata by cores and GPUs); 1M credits ≈ €3.50; the interactive partition is free (HPCintro slide 36).

## Globus

Collection IDs: KU Leuven Tier-2 Lustre scratch `82c495cc-aef8-40ad-88df-f9c92bee82d3`,
GPFS scratch `a6593381-d93d-4543-a3af-89424bcc6555`, data dirs `38948f53-d4f5-4e94-afa5-ad364c7a66b8`
(`globus/collections.rst`). Paths inside a collection are relative, e.g. `scratch/<3 digits>/vscXXXXX/...` (from `$VSC_SCRATCH`).

**Unverified (from lab code only):** manGO-on-VSC `cb13a033-02dd-401d-9cb5-7554178c0435`,
NERF file server `46cc0b3b-735d-4499-9fd8-8d085a71dca6`. Confirm with `globus ls <id>:/` before relying on them.
The lab's pattern is a 3-job chain (`--dependency=afterok`): Globus in → compute → Globus out plus scratch cleanup. Scratch is deleted only after the transfer reports SUCCEEDED.

## neu2p on VSC

`$VSC_DATA`: `git clone https://github.com/neurophysiology-expertise-unit/neu2p.git`, plus `suite2p.sif`.
Run from an interactive job:
`nextflow run neu2p/main.nf -profile vsc --device cuda --suite2p_container $VSC_DATA/suite2p.sif --vsc_account lp_big_wice_gpu --cluster_options '--clusters=wice --partition=dedicated_big_gpu' --input_dir ... --settings ...`
**Status: not yet run end-to-end on VSC.** Update this line after the first successful run.
