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
| A3 | One-off agent scripts accumulate in the working tree | `projects/alz-olf/` has 9 loose `.py` at root (`patch.py`, `patch_s1.py`, `fix_figures.py`, `remove_fig5.py`, …). **Corrected 2026-09-11: all 9 are UNTRACKED.** The only tracked scripts are `tools/build_ms.py` and `tools/cites.py` — already where the rule says they belong. So the convention was being followed; the root scripts are uncommitted scratch, not committed drift. `bayat-et-al`'s `explore_*.py` were not re-checked. |
| B | Derived data lives inside the Obsidian-synced git vault, and the raw location is undeclared | six `.parquet` in `projects/oldenlabs/analysis/experiments/dacruz_combined/cache/`. Raw data *does* live outside the vault at `/mnt/sysfs01/users/cagatay/external/{cruz,verstreken}/`, reached by absolute path from `experiment.json` — but nothing declares it, it is group-writable, and it has no `derived/`/`results/` siblings |
| C | Parallelism happens but is undocumented | `neubrain-oldenlabs/` is a WORKTREE on branch `oldenlabs/dacruz-study2` (its `.git` is a file pointing at `neubrain/.git/worktrees/neubrain-oldenlabs`), while `AGENTS.md` says "never run two agents on these repos at once". Corrected 2026-09-11: an earlier draft of this spec called it a second clone. It is not. |
| D | `HANDOFF.md` is a 2151-line global bottleneck | all projects interleaved in one file, rewritten every session |
| E | Submission freeze is prose, not a tool | `alz-olf` has both `submission/` and `submissions/`, no `SUBMISSIONS.md`, no tag. `astro_atp` follows the rule, but its `submissions/` also holds an unsent bundle, so the folder does not mean one thing |
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
3. ~~**Worktrees, one per project lane.**~~ **REVERSED 2026-09-11 — serial, one
   tree, handoff.** The library stays in the vault, whole and shared. But a lane
   does not carry the archive (see §3), and the vault *is* the library, so
   parallel lanes buy little and carry a silent failure mode. Both worktrees
   (`neubrain-deep-sniff`, `neubrain-oldenlabs`) are removed and everything is
   merged into `main`. This restores what `AGENTS.md` already mandated: never two
   agents on one tree.

   The cheap route back, if concurrency is ever wanted: a `--library <path>` flag
   on `fetch_papers.py`, `refs.py`, `extract_text.py` and `coding_dossier.py`,
   defaulting to `<vault>/_library`, so a lane can point at the main checkout's
   archive. Not built.
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

### `project.json`

Every project gets `neubrain/projects/<name>/project.json`:

```json
// a pipeline project = an expertise-unit service
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
```

```json
// a paper project
{
  "schema": 1,
  "name": "astro_atp",
  "type": "paper",
  "paper_repo": "https://github.com/neurophysiology-expertise-unit/bayat-et-al",
  "data_root": null,
  "source_studies": ["oldenlabs/dacruz/study2"],
  "lane": "astro-atp/manuscript-v2-verified",
  "status": "active"
}
```

**JSON, not YAML.** Every tool in `neuresearch/src/` is stdlib-only —
`reconcile.py` states it explicitly — and the vault's existing configs
(`manifest.json`, `study.json`, `provenance.json`) are all JSON. YAML would add
the codebase's first runtime dependency to buy comment support. The `//` lines
above are illustrative only and are not written to disk; the schema is documented
in `neubrain/AGENTS.md` instead.

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
| `compare-svm` | paper | null | null | none yet |
| `theta-pac` | paper | null | null | none yet |
| `writing` | — see below | | | |

`compare-svm` and `theta-pac` both carry the full paper shape (`plan.md`,
`manuscript.md`, `references.bib`, `papers.txt`, `archive/`) and classify cleanly.

**OPEN — `writing` is not a project.** It contains one file, `papers.txt`, and
nothing else. It is either a literature holding pen that should not sit under
`projects/` at all, or an abandoned scaffold to retire. The author decides; it is
the only project that cannot be classified from its contents.

`astro_atp` and `aon-pir-rev` both have substantial analysis pipelines, but those
pipelines live in their **paper repos**, not in the vault — so the *vault
project's* required shape is `paper`. The type declares what the vault directory
must contain, not whether the science involved an analysis.

### A pipeline project is a service, not a paper-in-waiting

`oldenlabs` and `intellicage` are the same kind of thing: an **expertise-unit
service** that runs analyses for client labs, and keeps accumulating them. They do
not converge on a single manuscript. That is already visible on disk —
`oldenlabs` holds `dacruz_combined`, `dacruz_study1`, `dacruz_study2`;
`intellicage` holds `verstreken` and `verstreken_2026-08`. Client, then study.

So there are exactly **two types**, not three. `pipeline+paper` is removed. A
pipeline project's contents are *studies*, one per client engagement, and when a
study yields a paper the paper becomes its **own `paper` project** that names the
studies it draws on in `source_studies`. The unit is never converted; it keeps
serving.

This also settles the open `study.json` / `experiment.json` question below: the
unit's unit-of-work is a **study**, so `study.json` is the right name and
`intellicage` renames.

`data_root` is **independent of type**: any project with data declares one,
including a `paper` project whose figure code lives in its paper repo and reads
from that root.

### RESOLVED — `analysis/` means experiments only; the manuscript lives in `draft/`

`astro_atp/analysis/manuscript_v2/` was never meant to be under `analysis/`. The
author's model is a two-state lifecycle: **a draft moves, a submission is locked.**
`analysis/` is therefore reserved for pipeline experiment runs, and a paper
project's working manuscript lives in `draft/`.

The current state of `astro_atp` shows why this needs fixing — the manuscript
exists in three places at once:

| path | size | last touched | what it is |
|---|---|---|---|
| `manuscript.tex` | 60 KB | 2026-07-21 | the version the two submissions were built from |
| `analysis/manuscript_v2/manuscript.tex` | 89 KB | 2026-09-01 | the actually-live draft |
| `manuscript.tex.bak-preKemal` | 50 KB | 2026-07-06 | a hand-made backup |

Two rules follow, and both are already implied by conventions the vault states
elsewhere:

- **A version never goes in a name.** `manuscript_v2` and `.bak-preKemal` both
  encode history in a filename. History belongs in git tags and in
  `submissions/`, which is the entire point of the freeze mechanism.
  `neubrain/AGENTS.md` already makes this argument for `plan.md` ("git is the
  backup; no `.bak` kept") — it applies to the manuscript identically.
- **There is exactly one live draft per project.** Anything else is a frozen
  submission or git history.

### Canonical paper-project layout

```
projects/<name>/
  project.json
  STATE.md
  plan.md
  papers.txt, references.bib, archive/    # literature side
  draft/                                   # THE working manuscript. One. Moving.
    manuscript.{tex,md}
    references.bib                         # derived by build_bib.py
    cover_letter.tex, highlights.tex
    figs/, *.cls, *.sty                    # assembly assets
    build/<journal>/                       # a bundle being assembled, not yet sent
    (build artefacts gitignored)
  submissions/<date>-<journal>/            # SENT work only. Created at the moment
                                           # of sending. Never edited afterwards.
  SUBMISSIONS.md
```

`submission/` (singular) in `astro_atp` is **not** a stray duplicate of
`submissions/` — it is the assembly staging area holding `cas-sc.cls`,
`cas-common.sty`, `cover_letter_cnsns.tex` and `figs/`. It folds into `draft/`,
since building the submission bundle is what a draft directory is for. The
`alz-olf` `submission/` folder is resolved the same way.

### `submissions/` holds sent work only

`astro_atp/submissions/` currently holds three folders, but only two submissions
happened. `2026-08-14-nonlinear-science` is a **prepared bundle that was never
sent** — the author has still to read it. `SUBMISSIONS.md`'s two rows and the two
`submitted/*` tags are correct; the folder is the thing that is out of place.

So `submissions/` is redefined as **sent work only**, and the rule is:

> A folder appears under `submissions/` at the moment of sending, never before.
> Creating it *is* the lock: snapshot the PDFs, add the `SUBMISSIONS.md` row, tag
> the commit. Nothing under `submissions/` is ever edited afterwards.

A bundle being assembled for a journal lives in `draft/build/<journal>/` until it
is sent. Two reasons this is the right split rather than a status column:

- The folder name carries the **submission date**, which is unknowable until the
  thing is sent. `2026-08-14` is an assembly date wearing a submission date's
  name — the folder is already lying about itself.
- The author's workflow is "go to the most updated work, convert, and lock". Lock
  is a single event with a single output. If unsent bundles can also live there,
  "is this version the one they have?" stops having a one-line answer, which is
  the entire purpose `SUBMISSIONS.md` states for itself.

With one live `draft/`, "the most updated work" needs no hunting: it is always
`draft/`, and freezing copies out of it.

**Migration:** move `submissions/2026-08-14-nonlinear-science/` to
`draft/build/nonlinear-science/`. It gets a `submissions/` folder, a row and a tag
if and when it is actually sent.

**Migration note.** `SUBMISSIONS.md`'s documented recovery commands reference
`projects/astro_atp/manuscript.tex`. Existing tags keep working unchanged, because
`git show <tag>:<path>` resolves the path as it was at that tag. But the
instructions must gain a line stating that tags from before this migration use the
old root path and tags after it use `draft/manuscript.tex`.

### Required shape per type

| type | must contain |
|---|---|
| `paper` | `plan.md`, `papers.txt`, `archive/`, `draft/manuscript.{md,tex}`, `draft/references.bib` |
| `pipeline` | `plan.md`, `protocol.md`, `studies/<client>/<study>/{study.json, provenance.json, outputs/}` |

A `paper` project that has submitted anything additionally requires
`SUBMISSIONS.md` and at least one `submissions/<date>-<journal>/`.

All types additionally require `project.json` and `STATE.md`.

### Canonical study shape

```
projects/<unit>/
  project.json, STATE.md, plan.md, protocol.md
  studies/
    <client>/                     # the client lab, e.g. dacruz, verstreken
      <study>/                    # one engagement, e.g. study1, study2, combined
        study.json                # configuration
        provenance.json           # input hashes, parameters, code commit
        outputs/                  # results + machine-readable tables
        report.md
```

`analysis/experiments/` is replaced by `studies/<client>/<study>/`. Nesting by
client is what makes "more and more analyses for other labs" scale — it keeps one
lab's engagements together, and a client folder is the natural unit to hand back
to that lab. Session-structured studies nest by session **inside** `outputs/`,
which is where `intellicage`'s current `sessions/` goes.

`study.json` is canonical over `experiment.json`, resolved by the unit's own
vocabulary: the thing a unit does for a lab is a study. `intellicage` renames, and
`neu-intellicage` changes with it.

Existing content maps as:

| now | becomes |
|---|---|
| `oldenlabs/analysis/experiments/dacruz_study1` | `oldenlabs/studies/dacruz/study1` |
| `oldenlabs/analysis/experiments/dacruz_study2` | `oldenlabs/studies/dacruz/study2` |
| `oldenlabs/analysis/experiments/dacruz_combined` | `oldenlabs/studies/dacruz/combined` |
| `intellicage/analysis/experiments/verstreken` | `intellicage/studies/verstreken/2026-07` |
| `intellicage/analysis/experiments/verstreken_2026-08` | `intellicage/studies/verstreken/2026-08` |

The `verstreken` → `verstreken/2026-07` mapping is **confirmed** by the study's own
metadata: `experiment.json` describes it as "Generated from the three substantive
July 2026 IntelliCage sessions", and `verstreken_2026-08` is titled "August 2026
interim report".

### Enforcement

- `neuresearch/src/check_vault.py` — validates each project's shape against its
  declared type. Specified in full in §6.
- `new_project.py --type <paper|pipeline>` scaffolds the correct skeleton and
  writes `project.json` and `STATE.md`. For a pipeline unit it also takes
  `--client` / `--study` to add a study to an existing unit.
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
    <client>/<export>/
  derived/    preprocessed intermediates. Fully regenerable.
              Safe to delete wholesale.
    <client>/<study>/
  results/    tables + figures. The only stage the vault sees.
    <client>/<study>/
```

### The raw stage already exists

`/mnt/sysfs01/users/cagatay/external/` holds `cruz/` and `verstreken/` — already
nested by client, which is the shape this section proposes. `intellicage`'s
`experiment.json` reaches into it by absolute path
(`external/verstreken/Sessions/2026-07-10 18.38.52`). So the raw stage is not
missing; it is **undeclared, unprotected, and unaccompanied**:

- no `project.json` names it, so nothing can check it;
- it is `drwxrwx---`, so any agent can write into it;
- there is no `MANIFEST.sha256`, so a change would leave no trace;
- there are no `derived/` or `results/` siblings.

**Migration is therefore one rename plus two new directories**, not a data move:

```
/mnt/sysfs01/users/cagatay/data/     <- data_root, shared by both units
  raw/        <- the current .../external/ , renamed
    cruz/, verstreken/
  derived/    <- new
  results/    <- new
```

The absolute paths inside each `study.json` are updated to match. The paths inside
existing `provenance.json` files are **not** rewritten: a provenance record states
where data was read at the time of the run, and editing it would make it a lie.
Lower-churn alternative if the rename proves disruptive: leave `external/` where it
is, declare it as the raw stage, and create `derived/`/`results/` beside it — the
structure matters, the name does not.

**The three stages sit above client and study, not inside them.** This is forced
by real usage rather than taste: `oldenlabs/studies/dacruz/combined` pools cages
58597, 58616, 58623, 58627, 62923 and 66336 across the client's separate studies,
so a raw export cannot belong to one study. Raw is owned by the client; derived
and results are owned by a study.

### The invariant

`derived/` and `results/` must be reconstructible from `raw/` plus the code commit
recorded in `provenance.json`. The operational test is literal: delete `derived/`,
rebuild, and get the same hashes.

### Vault contract

`projects/<unit>/studies/<client>/<study>/` keeps only `study.json`,
`provenance.json`, `report.md`, and the small machine-readable tables the
manuscript actually cites. Anything large is referenced by path into `results/`.
This preserves the existing rule that every plotted quantity is also written as a
machine-readable table — the table stays with the report; the bulk does not.

### Immutability is a detector, not a guarantee

`chmod a-w` is enforced from this client, so it stops an agent writing to `raw/`
here. It may not hold from a machine that mounts the share with different
`file_mode`/`forceuid` options. `MANIFEST.sha256`, verified by
`check_vault.py`, is therefore the mechanism that actually **detects** a
violation; the mode bits only make one inconvenient.

### Migration

The six `.parquet` files in
`projects/oldenlabs/analysis/experiments/dacruz_combined/cache/` move to
`<data_root>/derived/dacruz/combined/`. The vault retains `study.json`,
`provenance.json`, `outputs/*.csv` and the figures.

---

## §3 — Worktree lanes

- `neubrain/` stays on `main` and is the **integration tree**. No project work
  happens in it.
- A lane is created with `git worktree add ../neubrain-<project> -b <project>/<topic> main`.
  Branch from `main`, not from whatever the main checkout is on — four `deep-sniff`
  commits initially landed on `astro-atp/manuscript-v2-verified` for exactly that reason.
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
- `neubrain-oldenlabs/` already IS a worktree; it needs no migration, only to be
  recorded in the lanes registry.

### A lane does NOT carry the paper archive — found 2026-09-11

`neubrain/.gitignore` line 4 is `_library/*`, excepting only `.gitkeep` and
`manifest.json`. So the two halves of the library behave differently across
worktrees:

| | tracked? | consequence in a lane |
|---|---|---|
| `_library/manifest.json` | **yes** | every lane sees all ~292 entries |
| `_library/*.xml`, `*.pdf` | **no** | only files fetched *into that directory* exist |

Measured on 2026-09-11: the main checkout held 138 archive files; a
freshly-created lane held 15 — only what it had just fetched.

**This fails silently, which is the dangerous part.** `refs.py`,
`make_nodes.py`, `extract_text.py` and `coding_dossier.py` treat a missing file
as "no full text available" — an expected RESULT in their design — so a lane
produces a large and entirely wrong "NO TEXT" count without erroring. It is the
same shape as the `REFERENCE_HEADING_RE` gap already recorded in HANDOFF: a
broken first layer reported as a clean result.

A symlink would be the obvious fix and is **not available** — the share is
mounted `nounix`, so CIFS cannot create one. Options, none yet chosen:

1. **Library-wide operations run only from the main checkout.** Lanes do
   manuscript and project work. Zero machinery; the rule has to be written into
   `AGENTS.md` and enforced by `check_vault.py`, because nothing else will
   catch a violation.
2. **`check_vault.py` refuses to run library tools in a lane** — detect
   `.git` being a file plus an archive count far below the manifest count, and
   fail loud.
3. **Track the archive in git.** Honest and self-healing, but it puts hundreds
   of MB of publisher XML and PDF into the repo, and the `*.pdf` ignore exists
   deliberately.

Recommendation is 1 plus 2: state the rule, and make the checker enforce it
rather than trusting it.

### Worktrees are already in use here, and have been since 2026-08-21

`neubrain-oldenlabs` is not a clone — `git worktree list` reports it, and its
`.git` is an 83-byte file reading
`gitdir: /mnt/.../neubrain/.git/worktrees/neubrain-oldenlabs`. So the mechanism
this section adopts is not new to this setup and is not speculative: it has run
on this CIFS mount for weeks. A second lane, `deep-sniff/onboarding` at
`code/neubrain-deep-sniff`, was created on 2026-09-11 and behaved correctly,
including cherry-picking multi-MB binaries with their hashes intact.

**Naming follows what already exists**: `neubrain-<project>`, not the `nb-<project>`
this spec first proposed.

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
| **vault** (`neubrain/projects/<name>/`) | `plan.md`, `draft/` (the live manuscript + assembly assets), `papers.txt`, `archive/`, `submissions/`, `SUBMISSIONS.md`, `STATE.md`, `project.json` |
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

## §6 — Vault integrity check

The structure this spec defines is worth nothing if it decays the first time an
agent improvises. Finding A3 is what decay looks like: nine one-off `patch*.py`
scripts in `alz-olf`, none of them ever decided on. So the structure needs a check
that is **run repeatedly over time**, reports what has drifted, and repairs the
part that is safe to repair.

### `neuresearch/src/check_vault.py`

Default mode is **report-only** and genuinely read-only, writing
`neubrain/logs/vault-status.md` — the same pattern `reconcile.py` already uses for
`logs/library-status.md`. `--fix` is a separate, announced mode.

The findings split in two, and the split is the important part of the design:

**AUTO-FIXABLE — no judgement required, `--fix` repairs these:**

- a missing `project.json` or `STATE.md` (scaffolded from template, fields blank
  and flagged rather than guessed);
- regenerable derived files that are stale or absent — `logs/`, `references.bib`,
  `to-find.md` — which `neubrain/AGENTS.md` already declares are generated, never
  hand-maintained;
- a file sitting at a known-wrong canonical path (`submission/` → `draft/`);
- `chmod a-w` not applied to `raw/`;
- missing `.gitignore` entries for build artefacts.

**REPORT-ONLY — needs a human, never auto-resolved:**

- anything touching manuscript content;
- a second live manuscript appearing anywhere in a paper project;
- a folder under `submissions/` with no `SUBMISSIONS.md` row or no tag;
- a file under `raw/` whose hash no longer matches `MANIFEST.sha256`;
- a study with no `provenance.json`, or a `provenance.json` with no code commit;
- loose `.py` at a project root;
- a project whose `type` and contents disagree.

**It never deletes.** A drifted file that must move out of the way goes to
`neubrain/_quarantine/<date>/` with a line in the report. Exit codes: `0` clean,
`1` drift found, `2` tool error — so it can gate a commit or run on a schedule.

This respects the two invariants already in force: report-only tools never modify
inputs, and real errors crash loudly while "nothing to do" is an expected result,
logged.

### Where the rules live — and why not only in a skill

A skill alone would break the property decision 4 called binding.
`neuresearch/AGENTS.md` states it plainly: *"Claude Code skills under
`~/.claude/skills/` cannot be invoked by Codex or Gemini."* Vault rules that only
exist as a skill would be invisible to two of the three agents doing the work —
and those are the agents whose improvisation this check exists to catch.

So the rules are layered, with exactly one normative source:

| layer | artefact | audience |
|---|---|---|
| **rules** | `neubrain/AGENTS.md` | all agents. Normative. The single source of truth. |
| **enforcement** | `check_vault.py` | all agents. The executable form of those rules. |
| **workflow** | `neuresearch/skills/neubrain-vault/` | Claude. When to run it, how to triage each finding class, what never to auto-fix. |

The skill **points at `AGENTS.md` rather than restating it**, so the rules cannot
drift between the two. This is the layering already proven with
`ephys-pipeline-invariants`: the skill lives in `neuresearch/skills/`, is deployed
by `sync_skills.py`, and `aon_pir_rev/AGENTS.md` carries a pointer telling
non-Claude agents to read the file directly.

**Running it.** The check is cheap and read-only, so the default is to run it at
the start and end of any session that touched the vault, and after any multi-agent
work. `STATE.md`'s definition-of-done includes a clean run.

---

## Migration order

1. Write `project.json` for all 8 vault projects; classify `compare-svm`,
   `theta-pac`, `writing`.
2. Build `check_vault.py` in report-only mode; run it and record the failures
   without fixing them. `--fix` and the skill come after the migration, so the
   check is written against the structure the migration produces.
3. Confirm the `verstreken` → `verstreken/2026-07` study name. **Blocks step 4.**
4. Restructure the two units to `studies/<client>/<study>/`; rename
   `experiment.json` → `study.json` and update `neu-intellicage` to match; move
   `sessions/` under `outputs/`.
5. Restructure the paper projects to `draft/`: fold `submission/` into it, retire
   `analysis/manuscript_v2/` and the root `manuscript.tex` down to one live draft,
   delete `manuscript.tex.bak-preKemal` (git holds it), move the unsent
   `submissions/2026-08-14-nonlinear-science/` to `draft/build/nonlinear-science/`,
   and add the path-change note to `SUBMISSIONS.md`.
6. Split `HANDOFF.md`: extract durable findings, distribute per-project state,
   archive the remainder.
7. Create `STATE.md` for every project from the distributed content.
8. Establish `data_root` for `oldenlabs` and `intellicage`; move `cache/` to
   `derived/<client>/<study>/`; write `MANIFEST.sha256` and `chmod a-w` on `raw/`.
9. Convert paper-repo `HANDOFF.md`/`CLAUDE.md`/`GEMINI.md` to pointer stubs.
10. Merge `oldenlabs/dacruz-study2`; record the existing worktrees in the lanes
    registry; add `merge_manifest.py`. (No clone to retire — `neubrain-oldenlabs`
    was already a worktree, and `neubrain-deep-sniff` was added 2026-09-11.)
11. Update `neubrain/AGENTS.md` and `neuresearch/AGENTS.md` with the new rules; fix
    the NFS/CIFS wording while there.
12. Add `--fix` to `check_vault.py`, then write the `neubrain-vault` skill against
    the finished rules and deploy it with `sync_skills.py`.

Steps 1–2 are non-destructive and can proceed immediately. Steps 4, 5 and 8 move
files and should each be done on their own branch, with the vault clean before
starting. Step 5 must not run while a submission is in preparation.

---

## Out of scope

Not addressed by this design, deliberately:

- `freeze_submission.py` and the reconcile check for submission freezes (finding E).
- The method index linking published method → paper → code → project (finding F).
- Environment locking and provenance hardening (finding G).
- Enforcement of the freeze: `freeze_submission.py` and the reconcile check that
  every `submissions/` folder has a matching row and tag. This round defines what
  `submissions/` means; the next round makes a tool do it.
- Any change to the literature subsystem: `_library/`, `lit/`, `concepts/` and the
  manifest keep their current structure and stay whole in the vault.


---

## Addendum 2026-09-11 — the CIFS mount is not merely "flaky"

Consolidating to one tree ran into the stale delete-pending dirent condition
`neubrain/AGENTS.md` documents, repeatedly and reproducibly, at
`projects/astro_atp/communication`:

- `ls` and `stat` report **No such file or directory**
- `find` still lists it
- `mkdir` reports **File exists**
- `git checkout` fails with `cannot create directory ... File exists`

Three consequences worth planning around, beyond what AGENTS.md already records:

1. **`git checkout` can partially succeed.** One checkout reported
   `Switched to branch 'main'` with exit 0 while leaving ~18 files holding the
   *other* branch's content. The branch pointer moved; the working tree did not
   follow. Never trust a checkout's exit code alone on this mount — diff the tree
   against the branch afterwards.
2. **`git status` can report a clean tree while a tracked file is unreadable.**
   `what_we_tested.html` (blob `916e6cf`, 54283 bytes) is committed and pushed,
   `git status` says clean, and `wc -c` on it fails with No such file. Git's stat
   cache is fooled by the mount. Content in git is safe; the working tree is not
   proof of anything.
3. **The workaround that succeeded:** merge from the side whose content already
   matches the working tree, so the merge writes as little as possible, then move
   the other branch pointer and check it out (a no-op write-wise). Pushing early
   and often is the real protection — every commit made here was pushed before
   the next risky operation.
