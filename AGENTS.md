# AGENTS.md — neuresearch (the BUILDER)

Rules for the code/capabilities in this repo. The vault has its own rules in
`neubrain/AGENTS.md` (nodes/papers/concepts) — these govern the TOOLS that act on
it. See `BLUEPRINT.md` for rationale and `HANDOFF.md` for current state.

- **Purpose.** neuresearch is the builder: tools in `src/`, the writing know-how in
  `skills/`. It operates on the neubrain vault via `--vault /…/neubrain`. It is NOT
  the data — papers, nodes, and the manifest live in the vault, never here.

- **Invariants.** Never fabricate a citation, a reference, a metadata field, or a
  result the data don't show. Crash loudly on real errors; treat "not open access"
  / "no match" as expected RESULTS (logged), not failures. Report-only tools NEVER
  modify their inputs — they write only their own generated report files.

- **Conventions.** One **stem = citekey = archive filename = node filename**
  (surname+year, letter-suffixed on collision, e.g. `fujii2017`, `fujii2017a`). The
  **manifest is the source of truth**; `references.bib`, logs, and dashboards are
  derived and regenerated from it — never hand-edited.

- **Environment.** Runs in the conda env `neuresearch`. Invoke tools with
  `conda run -n neuresearch python3 src/<tool>.py …` (or activate the env first).

- **Skills.** Source of truth is `neuresearch/skills/`. Deploy to `~/.claude/skills/`
  with `sync_skills.py` — real copies, not symlinks (NFS can't symlink). Edit here,
  then sync.

- **Networking.** Public APIs only — Europe PMC, Crossref, OpenAlex, Unpaywall. Be
  polite: a fixed inter-call delay and a contact email in the User-Agent. No
  paywall circumvention; paywalled PDFs enter only via `ingest.py` (the human
  supplies them through their own access).
