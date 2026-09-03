# System restructure — project typing, external data, worktree lanes, per-project state

**Date:** 2026-09-03
**Status:** design approved by author; implementation plan not yet written
**Scope:** `neuresearch/`, `neubrain/`, the per-paper repos, and the data roots

---

## Why

The system grew two project kinds — data-analysis pipelines for the expertise
units (IntelliCage, Oldenlabs) and paper-writing projects — inside one vault that
describes only the second. Nothing on disk declares which kind a project is, so
each agent (Claude, Codex, agy) reconstructs the convention from whatever it can
see and produces a slightly different answer. The visible symptoms, all verified
on disk 2026-09-02:

| # | Finding | Evidence |
|---|---|---|
| A | Project type is undeclared; nothing can validate shape | `neubrain/projects/` holds 8 projects of two kinds, no marker |
| A2 | The two pipeline projects disagree with each other | `intellicage` uses `experiment.json` + `sessions/`; `oldenlabs` uses `study.json` + `cache/` + `outputs/` |
| A3 | One-off agent scripts become permanent repo content | `projects/alz-olf/` has 9 loose `.py` at root (`patch.py`, `patch_s1.py`, `fix_figures.py`, `remove_fig5.py`, …) + `texput.log`; every other vault project has 0. Mirrored in `bayat-et-al/` (`explore_*.py`, `fig3_recompute.log`) |
| B | Derived data lives inside the Obsidian-synced git vault | six `.parquet` in `projects/oldenlabs/analysis/experiments/dacruz_combined/cache/`; no external raw location exists at all |
| C | Parallelism happens but is undocumented | `neubrain-oldenlabs/` is a second clone of the same remote on branch `oldenlabs/dacruz-study2`, while `AGENTS.md` says "never run two agents on these repos at once" |
| D | `HANDOFF.md` is a 2151-line global bottleneck | all projects interleaved in one file, rewritten every session |
| E | Submission freeze is prose, and compliance is already split | `astro_atp` has `SUBMISSIONS.md` + `submissions/` + 2 tags; `alz-olf` has both `submission/` and `submissions/`, no `SUBMISSIONS.md`, no tag |
| F | No method index | the library is keyed for citation (stem = citekey = bib key); nothing links a published method to the code implementing it |
| G | Code↔result binding is by convention only | `provenance.json` exists but nothing validates that a result names the code commit that produced it |

Two infrastructure facts constrain every decision below, both measured on
2026-09-02:

- **Everything is one CIFS share.** `/mnt/sysfs01` *is* `//10.38.77.34/haeslerlab`
  (`vers=2.0,nounix,cache=strict,actimeo=1,soft`). `code/`, `neuresearch/`,
  `neubrain/` and the per-paper repos are all on it — not just the vault, as
  `neubrain/AGENTS.md` currently implies. Both `HANDOFF.md` and `AGENTS.md`
  attribute the no-symlink limitation to NFS; it is CIFS with `nounix`. Same
  conclusion, wrong cause — correct the wording when next touching those files.
- **`git` is 2.25.1**, which predates `git worktree repair` (2.30). There is no
  recovery command if a worktree's admin files are damaged on this mount.
- **`chmod` is enforced from this client.** Verified: `chmod 444` on a probe file
  under `code/` made a subsequent append fail with `Permission denied`, despite
  `file_mode=0770,forceuid,forcegid` in the mount options.

---

## Decisions

Locked with the author on 2026-09-02/03:

1. **One vault, typed projects.** Pipeline and paper projects both stay in
   `neubrain/projects/`; each declares its type.
2. **Per-project data root, three stages.** `raw/` → `derived/` → `results/`,
   located anywhere the project names, not in one global tree.
3. **Worktrees, one per project lane.** The library stays in the vault, whole and
   shared — it is not split out into its own repo.
4. **`HANDOFF.md` becomes a router; state moves to per-project `STATE.md`**, in
   plain markdown with fixed headings so Codex, agy and Claude all read and write
   it identically. Cross-agent portability is the reason this system exists and is
   the binding constraint on the schema.
5. **Paper projects point at a separate paper repo.** Vault owns manuscript and
   literature; the paper repo owns figure/analysis code.
6. **Paper-repo `HANDOFF.md`/`CLAUDE.md`/`GEMINI.md` become pointer stubs.**
   `AGENTS.md` stays real in every repo — it holds durable repo-specific rules,
   which is its purpose.

Deferred to a later round, recorded here so they are not lost: `freeze_submission.py`
+ a reconcile check for finding E; the method index for F; environment and
provenance hardening for G.

---

## §1 — Project typing

### `project.yml`

Every project gets `neubrain/projects/<name>/project.yml`:

```yaml
schema: 1
name: oldenlabs
type: pipeline              # paper | pipeline | pipeline+paper
unit: oldenlabs             # instrument / expertise unit; null for a pure paper
code_repo: neu-oldenlabs    # reusable analysis code; null if none
paper_repo: null            # URL of the per-paper repo; null if none
data_root: /mnt/sysfs01/.../oldenlabs-data   # null for a pure paper
lane: oldenlabs/dacruz-study2                # branch owning this project
status: active              # active | frozen | archived
```

`paper_repo` is a **URL, not a repo name** — `aon-pir-rev`'s repo is on Bitbucket
because its co-authors read it there, while `astro_atp`'s and `alz-olf`'s are on
GitHub under `neurophysiology-expertise-unit`.

Values for the projects that exist today:

| project | type | unit | code_repo | paper_repo |
|---|---|---|---|---|
| `astro_atp` | paper | null | null | `github.com/neurophysiology-expertise-unit/bayat-et-al` |
| `alz-olf` | paper | null | null | `github.com/neurophysiology-expertise-unit/ayan-et-al` |
| `aon-pir-rev` | paper | null | null | `bitbucket.org/cagatay_aydin/aon-priform-repo` |
| `intellicage` | pipeline | intellicage | `neu-intellicage` | null |
| `oldenlabs` | pipeline | oldenlabs | `neu-oldenlabs` | null |
| `compare-svm`, `theta-pac`, `writing` | to be classified during migration | | | |

`astro_atp` and `aon-pir-rev` both have substantial analysis pipelines, but those
pipelines live in their **paper repos**, not in the vault — so the *vault
project's* required shape is `paper`. The type declares what the vault directory
must contain, not whether the science involved an analysis. `pipeline+paper` is
therefore reserved for a project whose experiments live in the vault *and* which
grows a manuscript there — the state `oldenlabs` reaches when its manuscript
starts.

`data_root` is **independent of type**: any project with data declares one,
including a `paper` project whose figure code lives in its paper repo and reads
from that root.

**Minor open item — the meaning of `analysis/`.** In pipeline projects
`analysis/experiments/` holds experiment runs. In `astro_atp` the same directory
name, `analysis/manuscript_v2/`, holds a LaTeX build (`.aux`, `.bbl`, `.cls`,
figures, `manuscript.pdf`). One name, two meanings. The recommendation is to
rename the paper-project use to `build/` during migration so `analysis/` means
exactly one thing; deferred to the author because it changes paths co-authors may
have bookmarked.

### Required shape per type

| type | must contain |
|---|---|
| `paper` | `plan.md`, `manuscript.{md,tex}`, `references.bib`, `papers.txt`, `archive/` |
| `pipeline` | `plan.md`, `protocol.md`, `analysis/experiments/<exp>/{study.json, provenance.json, outputs/}` |
| `pipeline+paper` | the union of both |

All types additionally require `project.yml` and `STATE.md`.

### Canonical experiment shape

`study.json` (run configuration) + `provenance.json` (run record: input hashes,
parameters, code commit) + `outputs/` (results). Session-structured studies nest
by session **inside** `outputs/`.

**OPEN DECISION — requires the author.** This names `oldenlabs`' convention as
canonical, which costs `intellicage` a rename of `experiment.json` → `study.json`
plus a matching change in `neu-intellicage`. Adopting `intellicage`'s names
instead costs the same work on the `oldenlabs` side. The recommendation is
`study.json`, on the grounds that the file configures a study/run rather than
describing an experiment, and that `oldenlabs` already pairs it with the
`outputs/` name this spec adopts — but the author has not yet ruled, and the
migration must not start on this item until they do.

### Enforcement

- `neuresearch/src/check_project.py` — **report-only**, validating each project's
  shape against its declared type, matching `reconcile.py`'s existing philosophy.
- `new_project.py --type <paper|pipeline|pipeline+paper>` scaffolds the correct
  skeleton and writes `project.yml` and `STATE.md`.
- The schema is documented in `neubrain/AGENTS.md`, not `CLAUDE.md`, so Codex and
  agy see it.

### No loose scripts at project root

A rule, applying to **both** vault projects and paper repos: a script committed at
project root must live in `tools/` and be named for what it does. One-off patch
scripts are not committed at all — the edit is made and committed, the script is
not. This is what produced the nine `patch*.py`/`fix_*.py` files in `alz-olf` and
the `explore_*.py` files in `bayat-et-al`.

---

## §2 — Data layout

Under each project's `data_root`:

```
<data_root>/
  raw/        immutable. chmod a-w + MANIFEST.sha256 written at landing.
              No agent writes here, ever.
  derived/    preprocessed intermediates. Fully regenerable.
              Safe to delete wholesale.
  results/    tables + figures. The only stage the vault sees.
```

### The invariant

`derived/` and `results/` must be reconstructible from `raw/` plus the code commit
recorded in `provenance.json`. The operational test is literal: delete `derived/`,
rebuild, and get the same hashes.

### Vault contract

`projects/<name>/analysis/experiments/<exp>/` keeps only `study.json`,
`provenance.json`, `report.md`, and the small machine-readable tables the
manuscript actually cites. Anything large is referenced by path into `results/`.
This preserves the existing rule that every plotted quantity is also written as a
machine-readable table — the table stays with the report; the bulk does not.

### Immutability is a detector, not a guarantee

`chmod a-w` is enforced from this client, so it stops an agent writing to `raw/`
here. It may not hold from a machine that mounts the share with different
`file_mode`/`forceuid` options. `MANIFEST.sha256`, verified by
`check_project.py`, is therefore the mechanism that actually **detects** a
violation; the mode bits only make one inconvenient.

### Migration

The six `.parquet` files in
`projects/oldenlabs/analysis/experiments/dacruz_combined/cache/` move to that
project's `derived/`. The vault retains `study.json`, `provenance.json`,
`outputs/*.csv` and the figures.

---

## §3 — Worktree lanes

- `neubrain/` stays on `main` and is the **integration tree**. No project work
  happens in it.
- A lane is created with `git worktree add ../nb-<project> -b <project>/<topic>`.
- **Lane rule:** a lane stages only paths under its own `projects/<name>/`,
  verified with the idiom already in `neubrain/AGENTS.md`:

  ```
  git diff --cached --name-only | grep -v '^projects/<name>/' || echo "scope OK"
  ```

- **Shared state.** `logs/` is generated from `_library/manifest.json`, so a
  conflict there is resolved by **regenerating, never hand-merging**.
  `_library/manifest.json` is the one genuinely shared writer; conflicts in it are
  additive (each lane adds stems), so a small `merge_manifest.py` performing a
  key-union merge is built alongside this change.
- `neubrain-oldenlabs/` is retired once `oldenlabs/dacruz-study2` merges, and is
  replaced by a worktree.

### Why worktrees are the safer option here, despite the CIFS history

The 2026-08-18 failure recorded in `neubrain/AGENTS.md` was `git checkout -b`
writing the branch ref and reflog but failing to write `.git/HEAD`, after which the
name `HEAD` became unwritable — a stale directory entry on the mount.
`git worktree add` never rewrites the main repo's `HEAD`; it creates a fresh
`.git/worktrees/<name>/HEAD` at a path that did not previously exist, so it does
not rename into place over a hot file. The residual risk is that git 2.25.1 has no
`git worktree repair`, so damage to a worktree's admin files has no recovery
command — the fallback is to remove the worktree directory and re-add it, which is
safe because a lane's work is on a branch in the shared object store.

---

## §4 — State system

Cross-agent portability is the requirement: Claude, Codex and agy must all read and
update state identically, with no tooling. That makes the schema plain markdown
with fixed headings, documented in `AGENTS.md`.

### `neuresearch/HANDOFF.md` becomes a router

It keeps: purpose, the cross-agent handoff protocol, where files live, and the
core conventions summary. It loses all per-project narrative, replaced by one
table:

| project | type | lane | status | next action | state |
|---|---|---|---|---|---|

One row per project. This is the only file every lane touches, and it touches one
line of it.

### `neubrain/projects/<name>/STATE.md`

```markdown
# STATE — <project>
<!-- Schema v1. This file is the project's dynamic state. Any agent updates
     this file and no other. Durable rules live in AGENTS.md. -->

## CURRENT STATE
(YYYY-MM-DD) What is true now.

## NEXT ACTION
1. …

## BLOCKED
- … or "none"

## OPEN DECISIONS
- Things needing the author, not an agent.

## SESSION LOG
### YYYY-MM-DD — <agent> — <one-line summary>
…
```

State lives in the vault beside the project it describes, so each worktree carries
its own state file and lanes never conflict on it.

### Archiving the current 2151 lines

`HANDOFF.md` has **durable methodology tangled into session narrative**. Archiving
it wholesale would bury findings that must keep influencing behaviour. So the
migration splits it:

- **Extracted to `AGENTS.md` or a new `KNOWN_ISSUES.md`** (durable, must stay
  live): the `REFERENCE_HEADING_RE` gap in `coding_dossier.py:29` that makes a
  zero-discard result on a PDF-derived `.txt` mean "the stripper never found the
  section" rather than "the text was clean"; the `conda activate neuresearch`
  footgun where `python3` stays 3.9 and the interpreter must be called by absolute
  path; `fetch_papers.py` stripping whole-line `#` comments only; the lesson that a
  coding table built from abstracts is not safe because a human built it.
- **Distributed to `projects/<name>/STATE.md`**: the current state and next action
  for each live project.
- **Archived verbatim** to `neuresearch/docs/handoff-archive-2026-09.md`: the
  remaining session narrative.

---

## §5 — Paper repos

### The split

| owner | holds |
|---|---|
| **vault** (`neubrain/projects/<name>/`) | `plan.md`, manuscript, `references.bib`, `papers.txt`, `archive/`, `submissions/`, `SUBMISSIONS.md`, `STATE.md`, `project.yml` |
| **paper repo** | figure and analysis code, `environment.yml`, generated figures, repo-specific `AGENTS.md` |

Either side may hold a **read-only derived copy** of a file the other owns. Every
such copy carries the header already established in
`aon_pir_rev/reviewer_responses.md`: a `DERIVED FILE — DO NOT EDIT HERE` block
naming the version of record, why the copy exists, and that edits will be
overwritten. The main intended use is copying the built manuscript PDF into the
paper repo so co-authors see current state without vault access.

### Paper-repo entry points

`HANDOFF.md`, `CLAUDE.md` and `GEMINI.md` in a paper repo shrink to pointer stubs
naming `neubrain/projects/<name>/STATE.md` as the state file — the same pattern the
parent `code/CLAUDE.md` and `code/GEMINI.md` stubs already use. `AGENTS.md` stays a
real file: it holds durable repo-specific rules, which for `aon_pir_rev` includes
the pipeline architecture pointer and the `ephys-pipeline-invariants` skill
location.

This removes the current situation where `aon_pir_rev` runs an independent handoff
protocol for a project that also has vault state.

---

## Migration order

1. Write `project.yml` for all 8 vault projects; classify `compare-svm`,
   `theta-pac`, `writing`.
2. Build `check_project.py`; run it and record the failures without fixing them.
3. Resolve the `study.json` / `experiment.json` open decision. **Blocks step 4.**
4. Normalise the two pipeline projects to the canonical experiment shape.
5. Split `HANDOFF.md`: extract durable findings, distribute per-project state,
   archive the remainder.
6. Create `STATE.md` for every project from the distributed content.
7. Establish `data_root` for `oldenlabs` and `intellicage`; move `cache/` to
   `derived/`; write `MANIFEST.sha256` and `chmod a-w` on `raw/`.
8. Convert paper-repo `HANDOFF.md`/`CLAUDE.md`/`GEMINI.md` to pointer stubs.
9. Merge `oldenlabs/dacruz-study2`, retire the `neubrain-oldenlabs` clone, create
   the first worktree lane; add `merge_manifest.py`.
10. Update `neubrain/AGENTS.md` and `neuresearch/AGENTS.md` with the new rules; fix
    the NFS/CIFS wording while there.

Steps 1–2 are non-destructive and can proceed immediately. Steps 4 and 7 move
files and should each be done on their own branch, with the vault clean before
starting.

---

## Out of scope

Not addressed by this design, deliberately:

- `freeze_submission.py` and the reconcile check for submission freezes (finding E).
- The method index linking published method → paper → code → project (finding F).
- Environment locking and provenance hardening (finding G).
- The `submission/` vs `submissions/` naming collision in `alz-olf` — resolved as
  part of finding E's round, not this one.
- Any change to the literature subsystem: `_library/`, `lit/`, `concepts/` and the
  manifest keep their current structure and stay whole in the vault.
