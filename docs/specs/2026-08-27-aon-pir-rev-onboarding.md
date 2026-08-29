# aon-pir-rev — onboarding into the neubrain/neuresearch pipeline

**Status:** approved 2026-08-27. This file is the shared brief for ALL agents.
Every agent reads THIS file plus its own lane, and nothing else new.

Goal: finish the point-by-point response to reviewers for the AON/aPCx paper,
with the same tooling, library and citation grounding the other vault projects use.

---

## ABSOLUTE PATHS — use these, never relative ones

Each lane opens in a DIFFERENT directory, so a path like `neubrain/projects/...` resolves
only from `code/` and is missing from inside `neubrain/`. This bit Lane C on 2026-08-27.
**Every cross-repo path in this file is absolute. Use it verbatim.**

    ROOT      /mnt/sysfs01/users/cagatay/code
    ANALYSIS  /mnt/sysfs01/users/cagatay/code/aon_pir_rev
    VAULT     /mnt/sysfs01/users/cagatay/code/neubrain
    BUILDER   /mnt/sysfs01/users/cagatay/code/neuresearch
    PROJECT   /mnt/sysfs01/users/cagatay/code/neubrain/projects/aon-pir-rev

If a file this spec names appears to be missing, check your working directory against the
table above BEFORE concluding the prerequisite was never created.

**Python:** `conda activate neuresearch` does NOT change `python3` on this machine — the
profile's PATH keeps `/opt/conda/envs/ece/bin/python3` (3.9) in front. Always call
`/home/mouselab/.conda/envs/neuresearch/bin/python` by absolute path.

---

## Locked decisions (do not re-litigate)

1. **Vault-canonical text.** `neubrain/projects/aon-pir-rev/` is the version of
   record for `reviewer_responses.md` and `manuscript.md`. `aon_pir_rev` stays the
   version of record for CODE, DATA and FIGURES. Figures cross the boundary by
   export, never by editing them in the vault.
2. **Serialized lanes.** One agent at a time, one repo at a time. NEVER two agents
   on one tree. Between lanes: update HANDOFF, user commits + pushes, then the next
   agent opens. This is already the rule in every AGENTS.md here.
3. **Skill home.** `ephys-pipeline-invariants` moves to `neuresearch/skills/` and is
   deployed with `sync_skills.py`, so it loads from any directory under `code/`.

## Two mechanical rules that have bitten this setup before

- **Skills are not portable between agents.** Codex and Antigravity cannot invoke a
  Claude Code skill. Read the file directly:
  `~/.claude/skills/ephys-pipeline-invariants/SKILL.md` (+ its `references/`).
- **Codex and Antigravity do not read `CLAUDE.md`.** Anything they must obey belongs
  in an `AGENTS.md`.

## Invariants — every lane, no exceptions

- **Never fabricate** a citation, a DOI, a metadata field, a figure path, or a number
  the data do not show. A citekey with no library entry is an error to FLAG, not to invent.
- **Fail loud.** No bare `except:`, no swallowed MATLAB `try/catch`, no invented
  fallback value. See the ephys-pipeline-invariants skill.
- **Report-only tools never modify their inputs.** They write only their own report.
- **Scope.** Do the task asked. If something contradicts the code or the data, fix it
  and say so. If it is merely worse than you would have written it, leave it and
  mention it. Never change the title, delete a claim, or reorder Results unasked.
- **Numbers are load-bearing.** If you re-run anything, report **old vs new for every
  number that moved**, not just the new value.

## Reviewer-named literature (none of these is in the library yet)

Bolding 2020 · Bolding & Franks 2017 · Schoonover 2021 · Iurilli 2017 · Yuan 2024 ·
Marks & Goard 2021 · Aitken 2022 · Driscoll 2017 · Ziv 2013 · Lei 2006 ·
Wachowiak 2011 · Kehl 2024 · Jacobson 2018 · Boyd 2012 · Sokolov (orienting reflex)

These are the papers the response must argue *against specific numbers in*
(3.09 Hz, population sparseness 0.68, across-odor r ≈ 0.4). **Resolve each to a DOI
by search and verify first author + year + title before adding it to `papers.txt`.
Do not write a DOI you have not verified.**

## Scope of the response

~30 reviewer points across R1–R4. Leads: **CA** = agent-assistable analysis
(~11 still open), **SH** = prose/framing, **RDP** = wet-lab histology/DREADD —
**no agent can do RDP's items**, do not attempt them. **ES** = done.

---

# GATE 0 — user, before any agent starts

`aon_pir_rev` is dirty: `reviewer_responses.md` modified, plus untracked
`scratch/20260821_plot_svm_curves_absolute_N.py` and `scratch/check_cell_counts.py`.
The file about to move is the modified one and git is the only undo.

    cd /mnt/sysfs01/users/cagatay/code/aon_pir_rev
    git add -A && git commit -m "checkpoint before vault onboarding" && git push

---

# LANE A — claude, in `neuresearch` + `neubrain`

Run FIRST. Nothing else can start until the project exists.

1. **Promote the skill.** `git mv` (or copy + delete)
   `aon_pir_rev/.claude/skills/ephys-pipeline-invariants/` →
   `neuresearch/skills/ephys-pipeline-invariants/`, preserving `references/`.
   Then `python src/sync_skills.py` and confirm with `python src/sync_skills.py --check`.
   Leave a one-line pointer in `aon_pir_rev/AGENTS.md` saying where it now lives.
2. **Scaffold.**
   `python src/new_project.py --vault /mnt/sysfs01/users/cagatay/code/neubrain --name aon-pir-rev`
3. **Migrate text.** `aon_pir_rev/reviewer_responses.md` → the project folder verbatim
   (no rewriting). `aon_pir_rev/paper.md` → `manuscript.md` verbatim. Write `plan.md`
   from the paper's actual question and contribution — do not invent a framing.
4. **Co-author copy-back.** Add a derived read-only copy at
   `aon_pir_rev/reviewer_responses.md` headed `<!-- DERIVED — edit in the vault -->`,
   same pattern as `references.bib`. SH/RDP/ES reach it through Bitbucket.
5. **Library.** Resolve + verify the DOIs above → `papers.txt` → then in order:
   `fetch_papers.py --project aon-pir-rev --email cagatay.aydin@kuleuven.be` →
   `refs.py --only-empty` → `make_nodes.py propose` → (user edits
   `concepts/_proposed.md`) → `make_nodes.py wire` → `relate.py` → `build_bib.py --project aon-pir-rev`.
6. **Reconcile.** `reconcile_citations.py --project aon-pir-rev --manuscript-md`
   (report-only). Do NOT `--apply` unless the target is committed and clean.

**Done when:** `sync_skills.py --check` is clean, the project holds the migrated text,
the reviewer-named papers are fetched with lit nodes, and `references.bib` builds.
**Then:** update `neuresearch/HANDOFF.md` DYNAMIC SECTION, user commits + pushes
BOTH repos, and only then does Lane B open.

---

# LANE B — agy (Antigravity), in `aon_pir_rev` ONLY

Do not touch `neubrain` or `neuresearch`. Read `HANDOFF.md` and `CLAUDE.md` in this
repo first, and read `~/.claude/skills/ephys-pipeline-invariants/SKILL.md` as a plain
file — you cannot invoke it as a skill.

**Job: every `Data/Figure: ___` in the reviewer response is a hole. Fill it with a
real script path, a real figure file, and the real number.**

Work only the CA-led items still open:

- R1.1 tracking validation — error rates / stability metrics, Schoonover-style
- R1.7 cell-selection criteria — per-odor tests, correction, exclusion counts, tailedness
- R1.8 Fig. 4d–h rate-normalised re-plot + Cohen's d
- R2.3 distance-to-stable · R2.5 relabel Cell A/B · R2.8 200 ms window supplemental
- R2.9 Fig. 4H marginal histogram
- R3.2 habituation scaling + sniff window · R3.3/R4.3 standard drift measures
  (Marks & Goard, Aitken, Driscoll) alongside CKA, plus the Ziv 2013-style raw
  across-day response heatmap
- Cross-cutting: FR decrease with decreasing novelty (late trials); ITI short-vs-long

**Rules.** Numbers come from `comb_my_update` unless the point is about the frozen
paper dataset — say which you used, every time. `est_delay` and `sniff_source`
decisions in HANDOFF are settled; do not re-tune them. Do not edit
`reviewer_responses.md` in this repo — it is now a DERIVED copy. Write your findings
to a plain report file and let Lane A merge them into the vault.

**Done when:** each item above has script + figure + number, or an explicit
"cannot do, because". **Then:** update `aon_pir_rev/HANDOFF.md`, user commits + pushes.

---

# LANE C — codex, in `neubrain` — READ-ONLY

Do not modify the manuscript, the response, the manifest, any figure, or any coding
table. You write ONE new report file and nothing else. This is the same contract as
`BUILDER/src/claim_dossier.py` on alz-olf: **evidence assembly, no verdicts.**

**Job: a claim–evidence dossier for `PROJECT/reviewer_responses.md`.**
One entry per quantitative claim in the response. Each entry carries:

1. the claim, verbatim, with its R-number
2. **our side** — the script in `ANALYSIS/paper/` that produces the number, and
   the figure file it lands in (from `ANALYSIS/LANE_B_report.md`)
3. **their side** — the literature value being argued against, quoted from the
   library full text with its citekey
4. an empty VERDICT column

**Contamination rules, non-negotiable** — reuse the logic in `BUILDER/src/coding_dossier.py`,
do not reimplement it: prefer `.txt` over `.xml`; strip plain-text
References/Bibliography sections; remove exact JATS `<ref-list>` elements; reject
whole citation-bearing sentences so another paper's result is never presented as
evidence for this one. Report per-paper discard counts. A keyword hit inside a
reference list is exactly how the retired `bibliometrics.py` classifier failed and
how a hand-coded row was wrong too.

Where no full text is held, write `NO TEXT` and say so. Do not infer, do not
adjudicate, do not propose a rewrite.

**Done when:** the dossier exists with every VERDICT cell structurally empty and no
other file changed. **Then:** hand back for human adjudication.
