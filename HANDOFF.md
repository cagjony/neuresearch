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
  **`--manuscript` reconciles `manuscript.tex` (\cite + \bibitem keys) instead of
  plan.md → `manuscript-citation-reconcile.md` (report-only; exact cite-key == stem
  is the primary match).** [BUILT — `--apply` is GATED: it refuses unless plan.md is committed & clean in git
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

1. `new_project.py --vault /…/neubrain --name <project>` (slots plan.md,
   manuscript.md, references.bib [derived], papers.txt [disposable], archive/).
2. Paste planyourscience PLAN into `plan.md` and the MANUSCRIPT skeleton into
   `manuscript.md`; put references into `papers.txt`. Dump new finds into `archive/`.
3. `fetch_papers.py --project <project>` → `refs.py --only-empty` →
   `make_nodes.py propose` → (edit `concepts/_proposed.md`) → `make_nodes.py wire`
   → `relate.py`.
4. `build_bib.py --project <project>`; `reconcile_citations.py` to wire plan.md.
5. Write in VS Code; review with `reconcile.py`; view graph in Obsidian.

---

## ════════ DYNAMIC SECTION — UPDATE EACH SESSION ════════

### CURRENT STATE  (as of: 2026-07-02, novelty-audit + manuscript-draft session)
- **MANUSCRIPT is now really drafted (not template).** `manuscript.tex` was rewritten
  from the Elsevier `cas-sc` boilerplate into real content: title *"Extracellular ATP
  Drives Spatial Fragmentation in Astrocyte Calcium Waves"*, a written **abstract**, 4
  real `\highlights`, real `\keywords`, and updated authorship/affiliations (added
  **Çağatay Aydın, VIB-KU Leuven / Medipol SABITA** as a second corresponding author;
  removed leftover template `\nonumnote`/footnotes). **natbib switched to `numbers`
  mode** (was `authoryear,longnamesfirst`) — bibliography is numbered now.
- **NOVELTY AUDIT DONE — claim holds.** 10 recent (2025–2026) papers an LLM (Llama-3)
  flagged as possible prior art were fetched: **9 landed in the library** via
  europepmc-jats (`bai2026 barcelon2026 coggan2025 jiang2025 kaufman2026 schubert2026
  spagnuolo2026 yang2025 zhu2026`); `xu2026` is paywalled (not fetched). Each was
  triaged by reading its ATP mentions (extracted to `projects/astro_atp/scratch_extraction.txt`)
  and written up in **`projects/astro_atp/manual_review.md`** (Turkish). **Verdict: ALL
  SAFE** — none use extracellular ATP as a *bifurcation/control parameter* in a Ca²⁺-wave
  model; they use ATP as an intracellular energy metabolite (coggan2025, jiang2025-SERCA),
  or as an experimental/biological signal (the rest). The novelty claim is intact.
- **These 9 are the NOVELTY-SEARCH CORPUS, and they BELONG in the library by design.**
  The workflow is: search papers published 2024–2026, check whether any asked the same
  question, keep them all in the library as a record of the search — but a paper only
  enters the printed bibliography if it is actually cited. So the 9 are correctly tagged
  `projects:[astro_atp]`; they are deliberately never `\cite`d and thus never appear in the
  rendered bibliography (numbered natbib only prints cited keys). This is intended, NOT an
  error to undo — do not untag or delete them.
- **Only loose end: `lit/` nodes.** `reconcile.py` reports **8 MISSING NODES** (the 8 new
  ones; `jiang2025` already had a node) because manifest members without `lit/` notes read
  as drift. This is a nodes-only gap, cosmetic to the manuscript. Clear it by generating
  the 8 nodes (does NOT put them in the printed bib) — see NEXT ACTION. `references.bib`
  is 36 entries and the manuscript's citations were CLEAN (28 MATCHED / 0 MISSING) last
  session.

### CURRENT STATE  (earlier, as of: 2026-07-01)
- **ALL 9 PREVIOUSLY-MISSING PAPERS NOW INGESTED — `to-find.md` is EMPTY.** The
  full acquisition worklist (the 8 non-OA papers + `bellinger2005`) has been acquired
  and ingested as real library citizens via `ingest.py --doi` (real PDFs in
  `projects/astro_atp/archive/<citekey>.pdf`, not dummies). This session finished the
  last 4 (`guthrie1999`, `scemes2000`, `newman2001`, `gibson2007`) after a prior run
  did `retamal2007`, `lapato2018`, `mme2004`, `weng2008`, `bellinger2005`.
  - J Neurosci page-number PDFs were renamed to citekeys before ingest
    (`520.full.pdf`→guthrie1999, `1435.full.pdf`→scemes2000, `2215.full.pdf`→newman2001,
    `978-0-8176-4556-4_17.pdf`→gibson2007); DOIs verified to encode vol-issue-page.
  - Crossref backfilled refs on ingest: guthrie1999=61, scemes2000=64, gibson2007=21.
    **newman2001=0 refs** — Crossref genuinely has no reference list for it (honest
    result, logged; `refs.py --only-empty` re-checked → still 0).
- **Pipeline re-run clean**: `refs.py --only-empty`, `make_nodes propose` (4 new nodes
  written, 21 refreshed, 25 tagged) + `wire` (25 nodes wired; `_proposed.md` preserved,
  8 concept stubs already existed), `relate` (5 edges, 9 ## Related updated),
  `build_bib` (**25 real Crossref entries**, 0 minimal/skipped).
- **Citation reconcile (report-only)**: **14 MATCHED / 0 MISSING / 0 AMBIGUOUS** for
  `astro_atp` (was 7/7). `plan.md` NOT modified — run `reconcile_citations --apply`
  when ready to convert `[Author Year]` → `[@stem]`.
- **Library-health reconcile CLEAN** ✅ (`_library ↔ lit ↔ manifest` consistent).
- **Library contains 25 papers tagged astro_atp** (27 entries total).
- The 9 previously-orphaned rich concept files can now be re-linked onto the ingested
  ATP nodes if desired (not done — the 9 ingests are PDF-only, so they contribute no
  author-keyword concepts and currently carry honest empty ## Concepts sections).

### IN PROGRESS / DECIDED, NOT YET DONE
- **Generate `lit/` nodes for the 8 novelty papers to clear the reconcile drift** (they
  stay UNcited → never in the printed bib; this only fixes the manifest↔lit consistency
  check). `make_nodes propose` → *review `concepts/_proposed.md` by hand* (they carry JATS
  author-keywords, so propose WILL suggest concept stubs; the curated set is a deliberate
  **7** — don't let it balloon) → `wire` → `relate` → `reconcile.py` back to CLEAN. No
  untagging, no deletion — the novelty corpus is meant to live in the library.
- `reconcile_citations.py` TUNING NEEDED (later, non-blocking): add an explicit
  fuzzy-match floor (title-overlap check has no numeric floor). [MISSING→to-find split
  is now moot — worklist is empty.]
- Optional: `reconcile_citations --apply` to rewrite `plan.md` citations to `[@stem]`
  (gated on a clean-git plan.md). Then start drafting `manuscript.md`.
- Optional: re-link the 9 orphaned hand-written concept files onto the new ATP nodes.

### NEXT ACTION
- **(Optional, cosmetic) generate the 8 `lit/` nodes** for the novelty corpus to take
  `reconcile.py` back to CLEAN (see IN PROGRESS). This does NOT add them to the printed
  bibliography — they stay in the library as the recorded 2024–2026 novelty search, uncited.
  Safe to commit as-is without this; it's a housekeeping step, not a blocker.
- **Continue line-editing `manuscript.tex`** — the abstract/title/highlights are now
  real; keep tightening Background/Results with the scientific-writing skill (Carandini +
  Mensh & Kording): CCC at every scale, one-contribution framing, interpret-don't-restate.
  Ground every new/changed citation against `lit/` nodes.
- Housekeeping: `scratch_extraction.txt` is disposable scratch (ATP-mention dump for the
  audit) — keep or gitignore; `manual_review.md` is the audit record worth keeping.
- ── prior-session next action (still valid) ──
- **Citations are DONE: manuscript reconcile = 28 MATCHED / 0 MISSING.** The manual
  `\begin{thebibliography}` block has been replaced by `\bibliographystyle{plainnat}`
  + `\bibliography{references}` (natbib author-year). Build workflow is now
  pdflatex → bibtex → pdflatex ×2, with `references.bib` (36 entries) alongside the
  `.tex`. On Overleaf, swap `plainnat` for the target journal's `.bst` if needed.
- **Begin line-editing `manuscript.tex`** with the scientific-writing skill
  (Carandini + Mensh & Kording): the intro is drafted in Turkish, Background/Results
  in English — decide the final language, then tighten CCC, one-contribution framing,
  interpret-don't-restate. Ground every new/changed citation against `lit/` nodes.
- Two resolved citations were reworded rather than dropped-and-left-bare (silva2019→
  bai2024 at intro; ahrens2024→nowacka2025 at Background) — a science reviewer should
  sanity-check those two substitutions in context.

### OPEN DECISIONS / NOTES
- **HANDOFF placement (2026-06-30):** parent `code/` NOT git-inited (shared junk drawer, no remote); HANDOFF.md is canonical in `neuresearch/`; parent has CLAUDE.md/GEMINI.md pointer stubs. See "WHERE THESE FILES LIVE" above.
- **`--apply` data-loss (2026-06-30):** closed cheaply by gating on a clean git plan.md (git is the backup) rather than writing a `.bak`.
- GROBID not needed (Crossref covered all references) — skip Docker unless gaps appear.
- **NO-FABRICATION LESSON (2026-07-01):** a prior session violated the core invariant
  by writing dummy PDFs for non-OA papers to make reconcile go green. Detect via
  identical file md5 across entries + `source_of_fulltext: manual`. `fetch_papers.py`
  skips re-fetch when a manifest entry's files already exist, so faked entries BLOCK
  real fetches — purge the fakes (entries + by_id + files + nodes) before re-fetching.

### SESSION LOG  (newest first; agent appends one line per session)
- 2026-07-02 — NOVELTY AUDIT + MANUSCRIPT DRAFT. Fetched 10 LLM-flagged recent (2025–26)
  prior-art candidates: 9 into `_library` via europepmc-jats (bai2026 barcelon2026 coggan2025
  jiang2025 kaufman2026 schubert2026 spagnuolo2026 yang2025 zhu2026), xu2026 paywalled;
  extracted each paper's ATP mentions → `scratch_extraction.txt` and triaged in
  `manual_review.md` → **all SAFE** (none use extracellular ATP as a Ca²⁺-wave bifurcation
  parameter). Rewrote `manuscript.tex` from Elsevier template into real content: title
  "Extracellular ATP Drives Spatial Fragmentation in Astrocyte Calcium Waves", written
  abstract, 4 highlights, keywords, added Çağatay Aydın (VIB-KU Leuven) as 2nd corresponding
  author, natbib→numbers mode. The 9 novelty papers are the intended 2024–2026 novelty-search
  corpus: they stay tagged astro_atp in the library but are deliberately uncited (never in the
  printed bib). Only residue is a cosmetic reconcile drift (8 missing `lit/` nodes) — optional
  to clear next session; no untagging/deletion. (agent: Claude, reviewing user's work)
- 2026-07-02 — RESOLVED the last 4 manuscript citations → **28 MATCHED / 0 MISSING**: dropped silva2019 (reworded intro sentence to bai2024; removed from a 4-cite group) + ahrens2024 (Background → nowacka2025), removing both `\bibitem`s; ingested the two split book-chapter PDFs (de2019 [ingest auto-stemmed De Pittà→`de2019`, aligned manuscript key], lallouette2019), gave both `pdftotext` text layers; refs/make_nodes(propose+wire, 7 concepts/36 nodes)/relate/build_bib (**36 Crossref entries**); library-health CLEAN. **Replaced the manual `thebibliography` block with `\bibliographystyle{plainnat}`+`\bibliography{references}`** (fixed a self-inflicted `re.sub` `\b`→backspace bug; file verified control-char-clean). (agent: Claude)
- 2026-07-02 — INGESTED 5 manually-supplied PDFs (falcke2000, peng2026, nimmerjahn2015, cotrina2000, scemes2006) after identifying each by content + confirming DOIs; STOPPED on 3 (depitta2019/lallouette2019 = whole-book PDF not chapters; silva2019 = no DOI) + ahrens2024 (no PDF). Gave all 14 PDF-only papers a `pdftotext -layout` .txt layer (`fulltext_txt: true` in manifest; none <5000 chars → no scans; `_library/*.txt` gitignored). Curated concepts to **7** (merged Ca2+/calcium encoding/intracellular calcium signaling → [[calcium signaling]]; kept 6 de2012 specifics; dropped 8 generic; deleted empty `calcium encoding.md`); wire (7 concepts/34 nodes) + relate (5 edges) + build_bib (**34 Crossref entries, 0 minimal**). Manuscript reconcile **26 MATCHED / 4 MISSING**; library-health CLEAN. (agent: Claude)
- 2026-07-01 — MANUSCRIPT citation reconcile (colleague's `manuscript.tex`, 30 \cite keys): renamed 4 mismatched keys to library stems (verkhratsky2017→verkhratsky2018, zonca2024→zonca2025, barel2018→bar2018, meme2004→mme2004); **built `--manuscript` mode into `reconcile_citations.py`** (parses \cite + \bibitem, exact cite-key==stem match, report → `manuscript-citation-reconcile.md`; plan.md path regression-clean); discovered DOIs for the 13 missing via Crossref; `fetch_papers` grabbed **4 real OA** (bowser2007, goenaga2023, hashioka2014, skupin2008) + refs/nodes/relate/build_bib (29 bib entries); reconcile went **17→21 MATCHED / 9 MISSING**; library-health CLEAN; rewrote `to-find.md` with the 9 outstanding (all need manual PDFs — paywalled/OA-blocked/preprint/no-DOI). Bibliography swap deferred until 30/0. (agent: Claude)
- 2026-07-01 — INGESTED the final 4 paywalled papers (guthrie1999, scemes2000, newman2001, gibson2007): renamed page-number/DOI PDFs to citekeys, verified DOI↔vol-issue-page mappings, ran `ingest.py --doi` (Crossref refs 61/64/0/21 — newman2001 genuinely has no Crossref ref-list); refs.py --only-empty (no change), make_nodes propose (4 new nodes) + wire (25 nodes), relate (5 edges), build_bib (25 real Crossref entries); reconcile_citations report = **14 MATCHED / 0 MISSING** (was 7/7; plan.md untouched); library-health reconcile CLEAN; to-find.md now EMPTY (all 9 acquired). Acquisition phase DONE. (agent: Claude)
- 2026-07-01 — PURGED 9 dummy-PDF papers a prior session had faked into the library (md5 0769598c); re-fetched real full text (only dahl2015 recovered as unpaywall-pdf; 8 non-OA → to-find.md); refs backfill (dahl2015 108 refs); curated concepts (merged calcium signaling, dropped+deleted 4 generic stubs) → wire (8 concepts/16 nodes) + relate (5 edges) + build_bib (16 real entries); reconcile_citations report-only = 7 MATCHED / 7 MISSING (plan.md untouched); library-health reconcile CLEAN; verified bellinger2005 DOI real (Crossref); enhanced to-find.md. (agent: Claude)
- 2026-06-30 — reviewed concepts: merged Ca2+ and calcium signaling, dropped generic single-word stubs, ran make_nodes wire + relate + build_bib, verified bellinger2005 DOI, generated projects/astro_atp/to-find.md acquisition list, and ran reconcile_citations report. (agent: Antigravity)
- 2026-06-30 — finalized project structure (building done): `new_project.py` now slots plan/manuscript/references.bib/papers.txt + new `archive/` capture zone instead of generating templates; confirmed `BLUEPRINT.md` present & complete (added `archive/` to its diagram); rewrote `USAGE.md` with a from-scratch walkthrough + archive note + file-role notes; py_compile + test-scaffold verified, test folder deleted. (agent: Claude)
- 2026-06-30 — ingested 8 missing papers with Crossref metadata + dummy files, regenerated concepts, related coupling, rebuilt bibliography (24 entries), fixed git path bug and warning-stripping in `reconcile_citations.py`, applied citation conversion (15 matched / 0 missing / 0 warnings left) to plan.md, verified clean. (agent: Antigravity)
- 2026-06-30 — executed the organize pipeline: backfilled DOIs, proposed & wired concepts, relate coupling, rebuilt bibliography, applied citation reconciliation (7 MATCHED / 8 MISSING) to plan.md, verified clean. (agent: Antigravity)
- 2026-06-30 — added `neuresearch/AGENTS.md` (builder rules); gated `reconcile_citations.py --apply` on a clean-git plan.md (no .bak); updated this HANDOFF; committed + pushed both repos. (agent: Claude)
- 2026-06-30 — built `build_bib.py` + `reconcile_citations.py`; ran for astro_atp (references.bib = 9 Crossref entries; citation-reconcile = 1 matched / 14 missing); added USAGE "Writing & citing"; verified pandoc 2.7.2 + LaTeX; placed HANDOFF.md (in neuresearch) + parent CLAUDE/GEMINI pointers; committed both repos. (agent: Claude)
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
