# HANDOFF — read this first

> **Purpose.** This is the continuity document for an AI-assisted research
> paper-writing system. Any agent (Claude Code, Gemini CLI, or other) reads this
> file FIRST to understand the system and pick up exactly where the last session
> left off. The Git repos + this file are the memory: state lives on disk, not in
> any agent's head.
>
> **How handoff works.** At the END of a session, the agent updates the
> "CURRENT STATE", "NEXT ACTION", and "SESSION LOG" sections below, then the user
> commits & pushes both repos. The NEXT session (any tool, any machine) reads this
> file and continues. When switching tools (Claude ↔ Gemini), the rule is:
> **commit + push first, then open the other tool — never run two agents on the
> repo at once.**
>
> **Entry points.** `CLAUDE.md`, `GEMINI.md`, and `AGENTS.md` all point here for
> state, and to `AGENTS.md` for the durable rules. This file = dynamic state.
> `AGENTS.md` = rules that rarely change. Don't duplicate rules here.

---

## WHERE THESE FILES LIVE  (decided 2026-06-30)

The parent `/mnt/sysfs01/users/cagatay/code/` is a **shared junk drawer** (~34
unrelated projects, multi-GB archives, no remote) — it is deliberately **NOT a git
repo**. So:

- **This file is canonical at `neuresearch/HANDOFF.md`** — tracked, pushed each
  session with the builder repo (which already has a GitHub remote). Single source
  of truth; never copied (a dynamic file must not be duplicated, or it drifts).
- **`CLAUDE.md` + `GEMINI.md` live at the parent** `…/code/` as un-versioned
  bootstrap stubs. Claude Code / Gemini auto-read them from the launch directory
  and they route here. They are trivially recreatable — their exact 3-line content
  is reproduced at the bottom of this file under "PARENT POINTER STUBS", so any
  machine can regenerate them after cloning the repos.

If you ever want them version-controlled, the clean move is to keep templates in
`neuresearch/` and deploy them to the parent by copy (the same pattern
`sync_skills.py` uses for skills, since NFS can't symlink) — not to git-init the
junk-drawer parent.

---

## WHAT THIS SYSTEM IS

A pipeline that takes a planned scientific paper (from planyourscience) to a
finished, properly-cited draft. It (1) fetches open-access papers, (2) organizes
them into a linked literature library, (3) helps write & line-edit the manuscript
with grounded citations. Built for neuroscience/biomedical writing.

**Two repos, one system** (`neubrain` is what `neuresearch` builds):
- **`neubrain/`** — the Obsidian vault (DATA). Papers, notes, projects, the
  manuscript. `_library/` (flat: xml+pdf+manifest.json), `lit/` (paper nodes),
  `concepts/`, `projects/<name>/` (plan.md, papers.txt, manuscript.md, references.bib),
  `logs/`, dashboards. Has its own `AGENTS.md`.
- **`neuresearch/`** — the builder (CAPABILITIES). `src/` Python tools and
  `skills/` (the scientific-writing skill). Runs in conda env `neuresearch`.
  Tools operate on the vault via `--vault /…/neubrain`.

**Work from the parent** `/mnt/sysfs01/users/cagatay/code/` so both repos are in
view at once.

---

## CORE CONVENTIONS (summary — full rules in AGENTS.md)

- Papers live ONLY in `_library/` (flat). Projects connect papers via `lit/`
  nodes + citekeys; membership is in the manifest entry's `projects` field.
- One **stem = citekey = archive filename = node filename** (e.g. `fujii2017`).
- The **manifest is the source of truth**; logs, dashboards, `references.bib` are
  derived/regenerated from it — never hand-maintained.
- **Invariants:** never fabricate a citation, a reference, a metadata field, or a
  result the data don't show. Crash loudly on real errors; treat "not open access"
  / "no match" as expected RESULTS (logged), not errors. Report-only tools never
  modify inputs.
- Skills source of truth = `neuresearch/skills/`; deploy to `~/.claude/skills/`
  via copy (NFS can't symlink). Run `sync_skills.py` after editing a skill.
- Multi-machine: `git pull` before, `git push` after, every session.

---

## TOOLS (in neuresearch/src/)

- `fetch_papers.py` — OA fetch: Europe PMC JATS XML + Unpaywall PDF → `_library/`,
  updates manifest, logs to `logs/fetch-log.md`. `--vault --project --email`. [BUILT]
- `refs.py` — backfill `cited_dois` per paper: JATS → Crossref → GROBID(optional). [BUILT]
- `ingest.py` — absorb a manually-acquired PDF as a full library citizen. [BUILT]
- `make_nodes.py` — two-phase: `propose` (nodes + concepts/_proposed.md) then
  `wire` (create concepts + link). Read AGENTS.md. [BUILT]
- `relate.py` — bibliographic coupling: writes each node's `## Related` section
  (shared refs + direct citation). Regenerate freely. [BUILT]
- `reconcile.py` — READ-ONLY integrity check → `logs/library-status.md`. [BUILT]
- `export_project.py` — copy a project's papers out on demand. [BUILT]
- `suggest.py` — discovery: OpenAlex citation-graph + plan.md keywords → ranked
  `suggestions.md` (review file; preserves approval ticks). [BUILT]
- `build_bib.py` — manifest → `references.bib` (Crossref BibTeX, keyed by stem).
  [BUILT ✓ — ran for astro_atp]
- `reconcile_citations.py` — wire a draft's citations to the library; report to
  `citation-reconcile.md`, missing → `to-find.md`; `--apply` rewrites the draft.
  [BUILT — `--apply` is GATED: it refuses unless plan.md is committed & clean in git
  (git is the backup; `git checkout -- plan.md` is the undo — no .bak kept). TUNING
  NEEDED (later, not blocking): split MISSING into a separate `to-find.md`, and add
  an explicit fuzzy-match floor (currently a title-overlap check, no numeric floor).]
- `new_project.py` — scaffold a new project (plan template, papers.txt, manuscript
  stub) + print next steps. [BUILT]
- `sync_skills.py` — deploy `neuresearch/skills/` → `~/.claude/skills/`; `--check`
  audits. [BUILT — `--check` reports scientific-writing in-sync]

---

## WRITING WORKFLOW

- Write in **VS Code** (not Obsidian) — repo + terminal + agent in one place.
  Obsidian is for VIEWING the graph / reading nodes only.
- Manuscript in Markdown with `[@stem]` citations (or `.tex` with `\cite{stem}`).
- Cite-as-you-edit: select/point at a paragraph, ask the agent to improve English,
  swap words, add a sentence, add a citation "if we have one" — the agent edits in
  place and GROUNDS citations against `lit/` nodes (flags `⚠ no source` if unsupported).
  The user writes the science; the agent line-edits. (Gemini is used upstream for
  restructuring thoughts; the agent here line-edits written prose.)
- `references.bib` ← `build_bib.py`. Preview locally:
  `pandoc manuscript.md --citeproc --bibliography=references.bib -o out.pdf`
  (or `-o out.html` if no LaTeX engine). **NB: this server's pandoc is 2.7.2, which
  predates `--citeproc` (pandoc ≥ 2.11). Use `--filter pandoc-citeproc` instead —
  the filter is installed.** Final submission: Overleaf with the same .bib.
- Apply the **scientific-writing skill** (Carandini, Mensh & Kording): CCC at
  every scale, one contribution, interpret-don't-restate figures. Drafting + review
  modes.

---

## HOW TO START A NEW PROJECT

1. `new_project.py --vault /…/neubrain --name <project>` (scaffolds plan.md,
   papers.txt, manuscript.md).
2. Paste planyourscience export into `plan.md`; put its references into `papers.txt`.
3. `fetch_papers.py --project <project>` → `refs.py --only-empty` →
   `make_nodes.py propose` → (edit `concepts/_proposed.md`) → `make_nodes.py wire`
   → `relate.py`.
4. `build_bib.py --project <project>`; `reconcile_citations.py` to wire plan.md.
5. Write in VS Code; review with `reconcile.py`; view graph in Obsidian.

---

## ════════ DYNAMIC SECTION — UPDATE EACH SESSION ════════

### CURRENT STATE  (as of: 2026-06-30)
- **Doc spine complete:** `BLUEPRINT.md` now placed in `neuresearch/` → the four-doc
  spine (BLUEPRINT/AGENTS/USAGE/HANDOFF) is whole; `AGENTS.md`'s forward-reference no
  longer dangles. Both repos have an `AGENTS.md` (vault rules + builder rules).
- **`reconcile_citations.py --apply` is gated**: refuses unless plan.md is committed
  & clean in git, so `git checkout -- plan.md` is the one-step undo (no .bak).
- Active project: **astro_atp** (ATP modulation of astrocyte Ca²⁺ networks).
- **Library grew this session: 9 → 16 astro_atp papers** (18 manifest entries total,
  + `carandini2022`, `mensh2017`). New OA citizens: **conley2017, dahl2015, de2012,
  maris2019, verkhratsky2018** (plan refs) + **maly2021, zonca2025** (numbered list).
- **Root cause found & fixed:** the plan-reference block in `papers.txt` was pasted as
  full-citation prose (`Author… DOI: https://…`), which the fetcher can't parse — that
  is why those refs never came in. Rewrote that block to **bare DOIs** (the format the
  header asks for); De Pittà/Pittà **deduped** to one; **Bellinger 2005** flagged (no
  DOI anywhere — needs manual identification).
- **GAP / paywalled plan refs** (not OA — bring in via `ingest.py` with institutional
  PDFs): `guthrie1999, lapato2018, mme2004, retamal2007, scemes2000, weng2008`. Other
  GAPs: `scemes2006, newman2001, peng2026`.
- **MISS / unresolved identifiers:** Gibson 2008 book chapter
  (`10.1007/978-0-8176-4556-4_17`), Lallouette 2019 book chapter
  (`10.1007/978-3-030-00817-8_7`), Costa e Silva 2019 thesis (title search). Bellinger
  2005 (no id). These need manual identification before they can enter.
- The 7 new astro_atp papers have **EMPTY `cited_dois`** — `refs.py --only-empty` was
  the NEXT step but was **interrupted at handoff** (not yet run). No `lit/` nodes for
  them yet. Older 9 still have their nodes + 27 `relate.py` edges; `reconcile.py` was
  CLEAN before the grow.
- scientific-writing skill: canonical at `neuresearch/skills/scientific-writing/SKILL.md`,
  deployed + `sync_skills.py --check` = **in-sync**.
- **`build_bib.py` last ran on the OLD library** → `projects/astro_atp/references.bib`
  (9 Crossref entries). **Stale now — rebuild after refs/nodes.**
- **`reconcile_citations.py` report (also pre-grow):** MATCHED 1 / MISSING 14 /
  AMBIGUOUS 0. Re-running now should lift MATCHED to ~6 (Conley, Dahl, de2012, Maris,
  Verkhratsky joined Fujii); Guthrie/Même/Retamal/Scemes/Weng/Lapato stay MISSING until
  ingested. `plan.md` untouched (no `--apply` yet).
- `USAGE.md` has a **"Writing & citing"** section. Env: **pandoc 2.7.2** (use
  `--filter pandoc-citeproc`; no `--citeproc` until 2.11) + pdflatex/xelatex/lualatex.
- Vault changes this session (gitignored full-text excluded by design): `manifest.json`,
  `logs/fetch-log.md`, `projects/astro_atp/papers.txt`.

### IN PROGRESS / DECIDED, NOT YET DONE
- **Organize pipeline paused mid-run:** fetch DONE (library 9→16); the chain
  `refs.py → make_nodes → relate → build_bib → reconcile_citations re-run` is still
  pending. The very next step is the interrupted `refs.py --only-empty`.
- `reconcile_citations.py` TUNING NEEDED (later, non-blocking): split MISSING into a
  separate `to-find.md`; add an explicit fuzzy-match floor. (`--apply` data-loss is
  already closed via the git-clean gate.)
- (DONE since the seed: `build_bib.py`, `reconcile_citations.py` (+ --apply git gate),
  `new_project.py`, `sync_skills.py`, skill in `neuresearch/skills/`,
  `neuresearch/AGENTS.md`, `BLUEPRINT.md`.)

### NEXT ACTION
Resume the organize pipeline exactly where it stopped (mind the TWO human gates):
1. **`refs.py --vault … --project astro_atp --only-empty`** ← the interrupted step;
   backfills `cited_dois` for the 7 new papers (conley2017, dahl2015, de2012,
   maly2021, maris2019, verkhratsky2018, zonca2025).
2. `make_nodes.py propose` → **★ HUMAN GATE: review `concepts/_proposed.md`** before
   wiring → `make_nodes.py wire`.
3. `relate.py` (redraw coupling edges over the grown library).
4. `build_bib.py --project astro_atp` (the references.bib is stale — rebuild it).
5. `reconcile_citations.py --project astro_atp` **report-only** → **★ HUMAN GATE: read
   `citation-reconcile.md`**, confirm MATCHED rose (~6 expected).
6. **Commit plan.md** (the --apply gate requires it clean), then
   `reconcile_citations.py --project astro_atp --apply` to wire confident `[@stem]`.
7. Optional acquisition: `ingest.py` the 6 paywalled plan refs via institutional PDFs;
   manually identify Bellinger 2005 + the Gibson/Lallouette chapters + Costa e Silva
   thesis so they can enter the library.
8. Then start drafting `projects/astro_atp/manuscript.md` with the writing skill.

### OPEN DECISIONS / NOTES
- **HANDOFF placement (2026-06-30):** parent `code/` NOT git-inited (shared junk
  drawer, no remote); HANDOFF.md is canonical in `neuresearch/`; parent has
  CLAUDE.md/GEMINI.md pointer stubs. See "WHERE THESE FILES LIVE" above.
- **`--apply` data-loss (2026-06-30):** closed cheaply by gating on a clean git
  plan.md (git is the backup) rather than writing a `.bak`.
- GROBID not needed (Crossref covered all references) — skip Docker unless gaps appear.
- Obsidian Git plugin: only on the laptop, later, for holiday writing. Not the server.
- Drive sync of `_library/pdf/` for figures across machines: deferred until needed.

### SESSION LOG  (newest first; agent appends one line per session)
- 2026-06-30 — added `neuresearch/AGENTS.md` (builder rules); gated
  `reconcile_citations.py --apply` on a clean-git plan.md (no .bak); updated this
  HANDOFF; committed + pushed both repos. (agent: Claude)
- 2026-06-30 — built `build_bib.py` + `reconcile_citations.py`; ran for astro_atp
  (references.bib = 9 Crossref entries; citation-reconcile = 1 matched / 14 missing);
  added USAGE "Writing & citing"; verified pandoc 2.7.2 + LaTeX; placed HANDOFF.md
  (in neuresearch) + parent CLAUDE/GEMINI pointers; committed both repos. (agent: Claude)
- 2026-06-30 — created this HANDOFF.md; system state seeded. (agent: Claude)
- 2026-06-30 — relate.py (27 edges) + Dataview dashboards; reconcile CLEAN; committed.
- (earlier) — refs.py Crossref backfill (all 9), ingest.py built; nodes+concepts wired.
- (earlier) — single-location library (Option B), EPMC JATS fix, fetch+reconcile+make_nodes.

---

## PARENT POINTER STUBS  (recreate at `…/code/` if lost)

`…/code/CLAUDE.md` and `…/code/GEMINI.md` each contain exactly:

> Read neuresearch/HANDOFF.md first for current project state and next action. See
> each repo's AGENTS.md for durable rules. This is a paper-writing system: neubrain
> = vault/data, neuresearch = builder/tools+skills.

---

> **End-of-session checklist (every agent, every time):**
> 1. Update CURRENT STATE / IN PROGRESS / NEXT ACTION above.
> 2. Append one line to SESSION LOG.
> 3. Tell the user to `git add -A && commit && push` BOTH repos.
> 4. Remind: switching tools or machines → pull first, never two agents at once.
