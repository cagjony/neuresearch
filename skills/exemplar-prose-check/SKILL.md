---
name: exemplar-prose-check
description: >-
  Use when asked whether a manuscript draft reads well, reads like a human wrote it, or reads like
  a Nature / Science / Neuron paper — "is our writing good", "does this sound AI-written", "humanise
  this", "compare our prose to top papers", "style check", "benchmark the draft". Measures the draft
  (.md or .tex) against highly cited exemplar papers held as JATS in the neubrain library, section
  by section, with `neuresearch/src/style_bench.py`, then reads exemplar passages from the same field
  side by side. Report-only: proposes edits with line numbers, never rewrites the draft silently.
  For structure (contribution, C-C-C, ordering) use the scientific-writing skill; this skill is for
  how the prose reads.
---

# Exemplar prose check

The question "is our writing good?" gets an answer grounded in papers the field
has already rewarded: research articles in top journals in the vault's own
`_library/`, cited heavily per year. Two passes — numbers first, to know where to
look; then reading, because only reading can judge prose.

## 1. Corpus (rebuild when the library has grown)

```bash
conda run -n neuresearch python3 /…/neuresearch/src/style_bench.py --vault /…/neubrain \
  corpus --email <contact> --exclude-project EAAI-26-18624
```

Selects research articles with a separate Introduction, Results and Discussion,
in a top-journal list (Nature, Science, Cell, Neuron, Nat Neurosci, Nat Methods,
Nat Commun, eLife, PLoS Biol, Curr Biol, PNAS, J Neurosci, Cell Rep), at
≥ 15 citations/year (OpenAlex, cached in `logs/style-citations.json`). Writes
`logs/style-corpus.md` (the exemplar list — read it) and `logs/style-corpus.json`.
`--exclude-project` drops papers that belong *only* to an off-field project
(EAAI-26-18624 is a refereed battery-modelling manuscript, not our field). If the
list shows other off-field papers, exclude their project the same way and say so.

## 2. Measure the draft

```bash
conda run -n neuresearch python3 /…/neuresearch/src/style_bench.py --vault /…/neubrain \
  check /…/neubrain/projects/<p>/draft/manuscript.md
```

Writes `style-report.md` next to the draft. Per section (abstract, intro, results,
discussion): each metric against the exemplars' p25–p50–p75, ⚑ outside p10–p90;
words used far more than the exemplars use them; every sentence with a known
machine-prose tell, with its line number.

**Read the flags; do not chase the median.** What a ⚑ usually means:

| Flag | Usual meaning | Usually not a problem when |
|---|---|---|
| tells high | LLM-register words ("crucial", "furthermore", "novel", "underscores", "shed light") — the strongest humanisation signal | the word is a defined technical term |
| self-praise high | "important", "novel", "remarkable" — tell the reader what to think [@carandini2022] | — rarely fine |
| dashes high | aside dashes (em dash, spaced " – ", " - ", LaTeX `---`), a machine-prose habit; exemplars median 0 | (unspaced en dashes in ranges and name pairs — 50–100 µM, FitzHugh–Nagumo — are not counted) |
| sentence patterns high | each hit is listed by line and pattern name, with draft vs exemplar rate: trailing ", underscoring/highlighting/reflecting …" riders; "not merely X" / "is not X, but Y"; "stands as" / "serves as" / "represents a significant"; "studies have shown" / "it is well established" with **no citation in the same sentence**; stacked hedges ("could potentially"); recap closers ("Ultimately,", "future studies are needed"); chatbot residue (`oaicite`, `[cite: 1]`) — the last is never legitimate | a real contrast ("changes in kind, not merely in rate") is a scientific move; judge each hit, and act on the rate |
| same-word opener runs | three sentences in a row starting "The …" / "We …" — monotone | — |
| connective openers high | "However, … Moreover, … Notably, …" sentence after sentence | — |
| sentence length high | sentences carrying too many ideas | Methods-like passages |
| sentence-length CV high / low | low = every sentence the same length (monotone, machine-like); high = choppy fragments next to monsters | — |
| paragraph length low | thin, one-idea-per-two-sentences paragraphs; topic sentence + one supporting line | Abstract, short Discussion items |
| paragraph length high | paragraph doing two jobs — split at the second topic | Abstract (exemplar abstracts are one paragraph too) |
| passive low in Results | often *good* (active, "we" + strong verb [@carandini2022]) | almost always |
| hedges low in Discussion | overclaiming — check each claim against the data | the claim is a direct measurement |
| hedges high | stacked hedges ("may potentially suggest") | — |
| nominalisations high | "the activation of", "the performance of the measurement" → use the verb | — |
| over-used word | a tic (a filler word repeated) | it is the paper's key term — **reusing the exact term is a rule, not a fault** [@mensh2017, Rule 4; @carandini2022] |

## 3. Read exemplars side by side

```bash
… style_bench.py --vault /…/neubrain passages --section intro --n 3 --paragraphs 2 --project <p>
```

`--project` prefers exemplars from the draft's own project (closest field), else
the most-cited overall. Read the draft section next to them and compare **moves**,
not words:

- **First sentence**: concrete and specific (Paukert 2014: "Astrocytes are an
  essential component of neural circuits in vivo.") vs. throat-clearing
  ("In recent years, there has been growing interest in…").
- **Topic sentences**: does each paragraph open on its claim and end on the answer?
- **How they hedge**: one calibrated qualifier on the claim that needs it, not a
  hedge on every clause.
- **How they cite figures and numbers**: claim first, figure in parentheses.
- **Rhythm**: a long sentence followed by a short one; lists of three used only
  when there are three things.

Machine-prose patterns no regex catches — look for them by reading:
paragraphs that all end in a summary sentence ("Together, these results
demonstrate…", "X therefore Y"); triads of adjectives and lists of three where
there are not three things; **synonym cycling** (one entity under rotating names —
the mirror image of the reuse-the-key-term rule); every paragraph the same length;
"This suggests that" opening a sentence about nothing in particular; abstract nouns
as subjects ("The investigation of X revealed…") where a person or a cell could act;
signposting ("In this section, we…").

The sentence patterns are our own regexes, after the catalogues in Wikipedia
"Signs of AI writing", blader/humanizer and jdkato/voices (checked 2026-10-11).
Generic humaniser rules that are wrong for science are deliberately absent: no
penalty on passive voice in Methods, on "associated with", on "robust", or on
hedges. Never use detector-bypass "humanisers" (they rewrite to evade AI
detection and send the text to outside services).

## 4. Report

Give the author a short list, most consequential first. Each item: line number(s),
what reads wrong, the exemplar evidence (metric vs. exemplar range, or a named
exemplar `[[stem]]` that does it better), and a proposed rewrite of that sentence
in the author's own words and meaning. Propose; the author applies. In a shared
document, the author's own edits go in blue (vault convention).

## Never

- Call a text "AI-written" or "human-written". The numbers flag patterns; they do
  not identify the author.
- Edit to move a number toward the median. A draft can sit at p90 and be excellent.
- Copy exemplar sentences into the draft — read them for moves, then write.
- Replace a repeated key term with a synonym to make an "over-used" flag go away.
- Change a claim, number, citation or hedge that carries scientific meaning while
  "polishing" — flag it for the author instead (vault AGENTS.md: never fabricate).
