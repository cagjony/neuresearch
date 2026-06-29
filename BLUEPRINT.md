# BLUEPRINT — system architecture & design rationale

> The durable design document. Read `HANDOFF.md` for current state, `USAGE.md`
> for how-to recipes, `AGENTS.md` for operating rules. This file explains *what
> the system is and why it's built this way* — it changes only when the
> architecture changes.

---

## 1. What this is

An AI-assisted system for taking a neuroscience/biomedical paper from a
**planyourscience plan** to a **finished, properly-cited draft**. It is not a
reference manager and not a literature-review tool — it is a *paper-writing
system* in which literature acquisition and organization are the supporting
layer beneath the writing.

The defining choice: papers, concepts, projects, and the manuscript live as
**plain files in one linked graph that an AI agent operates on directly** —
rather than locked inside an application's database. That openness (vs. Zotero's
closed library or ResearchRabbit's walled UI) is the whole point: a paper node
can be linked from a project, cited in a manuscript, and reasoned over by an
agent, all in one continuous, version-controlled fabric.

---

## 2. Design principles

These recur throughout and explain most decisions:

1. **State lives in files, not in an agent's head.** Every result is written to
   disk (manifest, nodes, logs). Any agent, on any machine, reconstructs context
   by reading files. This makes the system agent-portable (Claude ↔ Gemini) and
   machine-portable (server ↔ laptop) via Git.

2. **One source of truth; everything else is derived and regenerated.** The
   `manifest.json` is canonical. Logs, dashboards, `references.bib`, the Markdown
   library views — all are *projections* of it, regenerated on demand, never
   hand-maintained. Derived data is never patched incrementally (it drifts);
   it is recomputed from source (cheap at this scale).

3. **Never fabricate.** No invented citations, references, metadata, matches, or
   results the data don't show. A gap is surfaced (`⚠ no source`, a gap log, a
   `MISSING` entry), never papered over. Crash loudly on real errors; treat
   "not open access" / "no match" as expected *results*, not failures.

4. **Human-in-the-loop at every consequential step.** Tools default to
   report-only; writes to inputs require an explicit flag. Concept creation,
   paper approval, and citation rewrites all pass through human review. The user
   owns the science; the agent acquires, organizes, and line-edits.

5. **Build for need, not for elegance.** Capabilities are added when a real need
   appears (GROBID was speced but skipped once Crossref covered all references;
   the xml/pdf split was deferred when one PDF didn't justify it). Garnish
   (graph visuals) is recognized as garnish.

6. **Each format has one job.** XML = structured text & references (machine).
   PDF = figures (human, for writing). Markdown nodes = the navigable graph.
   `.bib` = citation backbone. None is forced to do another's job.

---

## 3. Architecture

Two repositories, one system. **`neubrain` is what `neuresearch` builds.**

```
code/                         ← work from here; both repos in view
├── HANDOFF.md  CLAUDE.md  GEMINI.md   (pointers → shared state/rules)
│
├── neubrain/                 THE VAULT (data / output) — Obsidian
│   ├── _library/             flat: <stem>.xml, <stem>.pdf, manifest.json (truth)
│   ├── lit/                  paper NODES: <stem>.md (metadata + claim + links)
│   ├── concepts/             concept notes (human-curated graph glue)
│   ├── projects/<name>/      plan.md, papers.txt, manuscript.md, references.bib
│   ├── logs/                 fetch-log.md, library-status.md (generated)
│   ├── dashboard.md          Dataview live tables
│   └── AGENTS.md             vault rules
│
└── neuresearch/              THE BUILDER (capabilities)
    ├── src/                  Python tools (operate on the vault via --vault)
    ├── skills/               scientific-writing skill (→ deployed to ~/.claude/skills/)
    ├── HANDOFF.md            canonical dynamic state (tracked, laptop-portable)
    └── README / USAGE / BLUEPRINT / AGENTS
```

The repos stay separate because they have genuinely different lifecycles: the
vault is content (committed often, prose) with big files gitignored; the builder
is code + capabilities (committed deliberately, reusable across vaults). They
operate *as one system* by always launching the agent from the parent `code/`.

---

## 4. Data model

- **Stem = citekey = archive filename = node filename.** One identifier ties a
  paper's XML (`_library/fujii2017.xml`), its node (`lit/fujii2017.md`), its
  citation (`[@fujii2017]` / `\cite{fujii2017}`), and its bib entry. Collisions
  get a letter suffix (`fujii2017a`).

- **Manifest entry** (per paper): doi, pmid, pmcid, title, authors, year,
  `source_of_fulltext` (europepmc-jats | unpaywall-pdf | manual), `refs_source`
  (jats | crossref | grobid | none), `cited_dois` (the citation network data),
  `projects` (membership — a paper can belong to several), `files`, `fetched_at`.

- **Project membership** is recorded in the manifest `projects` field (machine
  truth) and expressed through `lit/` links + citekeys (human/graph). A paper
  exists once; projects reference it — no file duplication.

- **The citation network** is built from `cited_dois`, resolved JATS → Crossref →
  GROBID(optional). This decouples network membership from full-text access: a
  paper joins the network from its DOI's reference list even when its full text
  is paywalled.

---

## 5. Components

**Acquisition & organization (neuresearch/src/):**
- `fetch_papers.py` — OA fetch (Europe PMC JATS + Unpaywall PDF), manifest, logs.
- `refs.py` — backfill `cited_dois` (Crossref-first, GROBID fallback).
- `ingest.py` — absorb a manually/legally-acquired PDF as a full citizen.
- `make_nodes.py` — two-phase: propose nodes + concepts, then wire approved links.
- `relate.py` — bibliographic coupling (shared refs + direct citation) → `## Related`.
- `reconcile.py` — read-only integrity check of the paper subsystem.
- `suggest.py` — discovery via OpenAlex citation-graph + plan keywords (review file).
- `export_project.py` — materialize a project's papers on demand.
- `new_project.py` — scaffold a new project's front door.
- `sync_skills.py` — deploy skills/ → ~/.claude/skills/.

**Writing layer:**
- `build_bib.py` — manifest → `references.bib` (Crossref BibTeX, keyed by stem).
- `reconcile_citations.py` — wire a draft's citations to the library; report +
  `to-find.md`; `--apply` rewrites.
- **scientific-writing skill** — Carandini + Mensh & Kording canon (CCC at every
  scale, one contribution, interpret-don't-restate); drafting + review modes;
  carries the no-fabrication invariants.

**Surfaces:**
- Obsidian + Dataview — live, sortable library/coverage dashboards; the graph view.
- VS Code — where the manuscript is written and the agent line-edits.

---

## 6. The four workflows

1. **Acquire.** `papers.txt` (identifiers) → `fetch_papers.py` → OA XML/PDF in
   `_library/` + manifest. Paywalled/manual → `ingest.py`. References →
   `refs.py` (Crossref).

2. **Organize.** `make_nodes.py` (propose → human-curate concepts → wire) →
   `relate.py` (coupling edges). Result: a linked graph of nodes + concepts,
   viewable in Obsidian, auditable via `reconcile.py`.

3. **Discover.** `suggest.py` seeds OpenAlex with the project's DOIs (citation
   neighborhood) + `plan.md` keywords (argument gaps) → ranked `suggestions.md`
   → human approves → into `papers.txt`. (Heavy discovery can be outsourced to
   ResearchRabbit/Litmaps, feeding DOIs back into `papers.txt`.)

4. **Write.** Manuscript in Markdown (`[@stem]`) or LaTeX (`\cite{stem}`) in VS
   Code. The user writes the science; the agent line-edits selected paragraphs
   (English, structure, grounded citations) under the writing skill.
   `build_bib.py` → `references.bib` → pandoc preview (PDF/HTML) or Overleaf for
   final. Upstream thought-restructuring is done in a separate tool (e.g. Gemini).

---

## 7. Scope & honest boundaries

- **Open-access only** for automated fetch. Paywalled papers are acquired by the
  human through legitimate institutional access, then `ingest`ed. No paywall
  circumvention, ever.
- **Discovery is partly outsourced.** Mature free tools (ResearchRabbit, Litmaps)
  do citation-graph discovery better; `suggest.py` is a lightweight in-pipeline
  version. The system's differentiator is the *writing* layer, not discovery.
- **The agent edits; it does not author.** It polishes prose and grounds
  citations; the human supplies and understands the science.
- **The graph is navigation, not reasoning.** Obsidian's graph view is a useful
  surface, not an analytical engine. Value lives in the nodes, the citations, and
  the writing checks.
- **NFS constraint:** no symlinks (errno 95) — derived copies and deploys are
  real copies, not links.

---

## 8. Continuity & portability

The system is designed to survive switching agents and machines. `HANDOFF.md`
holds dynamic state; `CLAUDE.md`/`GEMINI.md`/`AGENTS.md` are front doors pointing
to it. The discipline: end a session by updating `HANDOFF.md`, commit + push both
repos, then the next agent (any tool, any machine) reads it and continues. Switch
tools only after pushing; never run two agents on the repos at once. Git carries
the text layer between machines; a future Google-Drive sync of `_library/pdf/`
carries figures; the manifest can re-fetch the OA library from scratch on a new
machine.
