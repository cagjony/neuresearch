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

**Beyond 500 GB of scratch:** node-local `$VSC_SCRATCH_NODE` (600 GB per wICE job, wiped at job end) for per-job intermediates; GPFS scratch is Mindwell-only (Mindwell credits = 1); staging/project storage are paid and currently frozen; Tier-1 Data is from 5 TB and free, by proposal. Stream sessions (in → process → out → delete) rather than keep datasets on scratch. Recommended `~/.bashrc` (NXF_HOME, Apptainer vars inside jobs only, `neu2p-env`/`-status`/`-history` aliases): neuvsc guide, step 3.

## Quick reference: failures seen in practice

- **"Disk quota exceeded" on `~/.nextflow` or `~/.globus`:** home is full. Run `du -sh ~/.[!.]* | sort -h`. The usual cause is `~/.vscode-server` (GBs). Move it and symlink it, keeping the same name at both ends (`compute/portal/ondemand/vscode-server.rst`):
  `mv ~/.vscode-server $VSC_DATA/.vscode-server && ln -s $VSC_DATA/.vscode-server ~/.vscode-server`.
  Then set `export NXF_HOME=$VSC_DATA/.nextflow` (never scratch: it is purged).
- **SSH from a lab server** (verified 2026-09-26): no permanent key login; you need a 16 h certificate plus the firewall.
  Run `SSH_AUTH_SOCK=~/.ssh/agent-vsc.sock step ssh login --context VSC` from a MobaXterm terminal (it opens Firefox on
  the server); `--console` fails (no device flow); `invalid_grant` means retry faster. Firewall: `curl -4` the token line
  from firewall.vscentrum.be on the server. Then `ssh vsc`. kmk/certagent are for u-number servers, not VSC (`accounts/mfa_login*.rst`).
- **VS Code** leaves an "agent host" process running on the login node after you disconnect (one ran for 22 days) and fills `~/.vscode-server` with GBs of program files that are safe to delete. Prefer the OnDemand VS Code app (it runs inside a job); otherwise use "Remote-SSH: Kill VS Code Server on Host".
- **Non-interactive `ssh vsc '<cmd>'` has no `$VSC_DATA`/`$VSC_SCRATCH`**: the VSC variables are set only in login shells. Wrap commands in `bash -l -c '...'`.
- **A tool looks missing** (`which`/`module avail` show nothing): run `module spider <Name>`. Modules are per cluster tree; e.g. `Nextflow/25.04.8` needs a `cluster/...` module (the login default works). Globus CLI has no KU Leuven module; install it in a venv in `$VSC_DATA` (`globus/cli.rst`).
- **Apptainer:** set the cache/tmp to `/tmp/$USER/...` only when `$SLURM_JOB_ID` is set. Build and run containers on compute nodes (`compute/software/installing_software/containers.rst`). Keep `.sif` files in `$VSC_DATA`.
- **Login node:** no heavy or long work (`compute/jobs/index.rst`). The free wICE `interactive` partition exists (`leuven/wice_quick_start.rst`) but **rejects the lp_big_* accounts ("Invalid qos", verified 2026-09-26)**: run long light processes such as the Nextflow head as a 1-core job on `dedicated_big_bigmem`.
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

**Credits:** `sam-balance` (as of 2026-09-26 the `lp_big_mindwell_*` accounts show a balance of 1, so they're effectively unusable; use wICE). Jobs: `squeue --clusters=all -u $USER`, `sacct -M wice …`, `slurmtop --dedicated --cluster wice`. **Will it start now?** `neu2p-avail [walltime]` (guide `.bashrc`) runs these checks for a CPU head and an A100 job. `sbatch … --test-only job.sh` prints the predicted start time and node without submitting; `squeue -M wice -u $USER --start` for waiting jobs; `sinfo -M wice -p <partition> -o "%P %D %N %T"` shows node states (`planned` = held for a big waiting job, `draining` = being taken out). If `dedicated_big_bigmem` is blocked, a 2-core Nextflow head can run on `dedicated_big_gpu` without a GPU. A full wICE GPU node costs 45,000 credits/h (billed pro rata by cores and GPUs); 1M credits ≈ €3.50; the interactive partition is free (HPCintro slide 36).

## Globus and manGO (verified 2026-09-26)

Setup, once, in the `$VSC_DATA/tools` venv: `globus login --no-local-server`, then a one-time
`globus session consent --no-local-server '<scope>'` per collection (`globus ls <id>:/` prints the scope; several fit in one bracket).
`globus collection show` needs admin consent; use `globus ls` / `globus endpoint show`.

| Collection | ID |
|---|---|
| manGO ("VSC iRODS gbiomed.irods.icts.kuleuven.be") | `cb13a033-02dd-401d-9cb5-7554178c0435` |
| Tier-2 Lustre scratch (`globus/collections.rst`) | `82c495cc-aef8-40ad-88df-f9c92bee82d3` |
| Tier-2 GPFS scratch | `a6593381-d93d-4543-a3af-89424bcc6555` |
| Bonin NERF share ("vsc-nerf-boninlab-boninlabwip2024", NOT bigDATA; needs Bonin-lab ACL) | `46cc0b3b-735d-4499-9fd8-8d085a71dca6` |

- manGO paths start at `/gbiomed/home/<project>/`. **A project you aren't a member of reports "not found"**, not "denied" (e.g. Bonin's `PVDH/`).
- Unit 2p data: `/gbiomed/home/Data_Hub/FD000009-NEUROPHY_2PAST/BDS calcium imaging project/2p_data/<session>/<run>/` (~90 sessions, ~26 GB tif per run). The names contain spaces: quote `"<id>:<path>"`.
- Scratch inside `82c495cc` is `/scratch/<3 digits>/vscXXXXX/` = `$VSC_SCRATCH` without `leuven/` (verified).
- Lab pattern (Dylan): a 3-job chain (`--dependency=afterok`): Globus in → compute → Globus out, then delete scratch only after SUCCEEDED.

## neu2p on VSC (ran 2026-09-26)

- The code (private repo) and `suite2p.sif` live in `$VSC_DATA`; data is in `$VSC_SCRATCH/raw/`.
- **The `interactive` partition rejects the lp_big_* accounts ("Invalid qos")**: run the Nextflow head as
  `sbatch -M wice -A lp_big_wice_cpu -p dedicated_big_bigmem -n 1 -c 1 --mem=4G`.
- **KU Leuven sbatch requires `-M`** ("Please select a cluster…", cli_filter error): `export SLURM_CLUSTERS=wice` in the head script.
- Use `--partition dedicated_big_gpu --vsc_account lp_big_wice_gpu --device cuda`. **Never `--cluster_options '--x'`**:
  Nextflow's CLI takes it as a new flag and sets the value to `true` → "Invalid directive … true".
- 1024² movies: `-c mem.config` with SUITE2P memory 96 GB (the default 32 GB is too small for detection).
- A100 check: driver 595.71, the container's torch 2.14+cu130 sees CUDA.
- **Data on manGO → `stream.nf`** (preflight, Globus in/out waiting for SUCCEEDED, raw deleted only after upload).
  Nextflow pitfalls seen: `session` is a reserved name (tasks became `nextflow.Session@…`); SLURM variables are not
  set inside the container (`$SLURM_JOB_ID: unbound variable`); `errorStrategy 'ignore'` + `cleanup` deletes failed
  tasks' logs; the vsc profile's 8-CPU default must not apply to steps run in the head job (label `transfer`).
- PENDING "ReqNodeNotAvail, Reserved for maintenance" = walltime overlaps maintenance: request less, `-resume` later.
- macOS `._*.tif` AppleDouble files (magic 00051607) sit next to movies on manGO: skip dotfiles.
- Full recipe: neuvsc guide, step 8.

## Keeping this knowledge up to date

One fact lives in three places, all versioned. **When you verify, correct or add a VSC fact, update all three in the same session:**
1. this skill: `neuresearch/skills/vsc-for-neu-users/SKILL.md` (then `python src/sync_skills.py`);
2. the colleague guide: `code/neuvsc/README.md` (push to github.com/neurophysiology-expertise-unit/neuvsc);
3. `neubrain/projects/neuvsc/STATE.md` (what is verified vs pending) and `reading.md` if a new source was read.

A fact marked "unverified" becomes plain text only after it worked in practice; note the date.
