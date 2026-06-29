---
name: scientific-writing
description: Use when drafting, structuring, or revising a scientific manuscript or any of its parts — title, abstract, introduction, results, discussion, figures, or a grant's Specific Aims. Grounds every move in two methodology papers held in the library: Mensh & Kording's "Ten simple rules for structuring papers" (structure) and Carandini's "Some Tips for Writing Science" (sentence- and word-level craft). Trigger on requests to write or restructure a paper, tighten an abstract, fix a rambling introduction, order results, sharpen a discussion, cut wordiness, or fix impenetrable prose.
---

# Scientific writing

This skill operationalises two methodology papers archived in the neubrain
library. When you need the primary source, read the JATS in `_library/` or the
node in `lit/`:

- [[mensh2017]] — Mensh & Kording, *Ten simple rules for structuring papers*, PLoS Comput Biol (2017). `[@mensh2017]`. **Owns structure** at every scale.
- [[carandini2022]] — Carandini, *Some Tips for Writing Science*, eNeuro (2022). `[@carandini2022]`. **Owns craft**: questions-as-pillars, sentences, words, figures.

Citations use the vault's citekeys; a `[@citekey]` with no `.bib` entry is an
error to flag, never to invent. Apply these papers' structure and craft — never
paste their text into a draft.

## The two load-bearing ideas

**One contribution, named in the title** [@mensh2017, Rule 1]. The "Rule of One":
focus on a single message; papers chasing multiple contributions are less
convincing about each and less memorable. The test of success — *a reader can
still describe your paper's main contribution to a colleague a year later.* The
title is the most-read sentence (think of the ratio of titles to papers you
read), so make it transmit the contribution, and return to hone it often. Before
writing or restructuring anything, make the author state it: *"This paper shows
that ___."*

**The questions are the pillars** [@carandini2022]. Center the paper on the
questions it addresses: *pose them in the Introduction, answer them in Results,
discuss the answers in Discussion.* Identifying these questions "takes surprising
effort" — during the work you followed gut feelings; writing forces them "from
the gut to the language areas of the cortex," and the paper may end up answering
different questions than you started with. Pin down the questions first;
everything else hangs on them.

## Structure: Context–Content–Conclusion [@mensh2017, Rule 3]

The same arc repeats at every scale — whole paper, section, paragraph:

- **Context** — why this; connect to what the reader already cares about.
- **Content** — the new thing (what was done / found).
- **Conclusion** — what it means; this becomes the *context* for what follows.

Missing context makes the reader ask *"Why was I told that?"*; missing conclusion,
*"So what?"* At the whole-paper scale: Introduction = context, Results = content,
Discussion = conclusion. At the paragraph scale: first sentence = context, body =
content, last sentence = conclusion. **Do not structure the paper chronologically**
— readers don't care about the path you took, only the claim and the logic
supporting it.

## Flow: avoid zig-zag, use parallelism, kill synonyms

- **Zig-zag** [@mensh2017, Rule 4]: only the central idea may recur; cover every
  other subject in exactly one place, and string related sentences together.
- **Parallelism** [@mensh2017, Rule 4]: communicate parallel ideas in parallel
  form so the syntax becomes transparent and the reader can focus on content.
- **No synonyms** [@carandini2022; @mensh2017, Rule 4]: once you name something,
  reuse those exact words. Varying them (the habit school taught us) makes readers
  wonder whether the second word means something new. "The game here is to ensure
  people follow our logic with minimal effort."

## The components [@mensh2017, Rules 5–8]

**Abstract — the complete story** [@mensh2017, Rule 5]. For most readers it is the
only part read. Structure: **context** (first sentence broad → narrowed until it
lands on the open question and why it matters) → **content** ("Here we…": the
method, then the executive summary of results) → **conclusion** (answer the posed
question, then the broader significance). Broad–narrow–broad. The common failure
is talking about results before the reader is ready; iterate until "the results
fill the gap like a key fits its lock."

**Introduction — why the paper matters** [@mensh2017, Rule 6]. Progressively
specific paragraphs that culminate in the gap: field gap → subfield gap → the
specific untested gap you fill → a final paragraph summarising what the paper
does. Each paragraph is itself C-C-C. **No broad literature review** beyond the
motivation. Carandini adds [@carandini2022]: open with a *vivid* first sentence
(his favourite, Barlow 1961: *"A wing would be a most mystifying structure if one
did not know that birds flew."*); keep the Introduction under ~500 words; and
**don't call your questions "interesting," "important," or "understudied"** — let
the reader conclude that ("understudied" even backfires: maybe it's understudied
because unimportant).

**Results — a logical sequence of claims** [@mensh2017, Rule 7]. Sketch the
logical structure first and turn it into declarative subsection headers (or figure
titles). The first results paragraph summarises the overall approach and the gist
of the methods (most readers skip Methods). Each later paragraph: open by setting
up the question it answers, give data and logic in the middle, and **end on the
sentence that answers it** — so the paper reads like a chain of theorems. Figure
titles state the *conclusion* of the analysis; legends explain *how*. Carandini
[@carandini2022]: distribute brief method descriptions across Results so the reader
can go straight from Introduction to Results; refer to figures only in parentheses
(*"The brain is wet (Fig. 1)"*, never "Fig. 1 shows…"); proceed exemplar → general
within a figure; and **minimise ink** (Tufte) — every mark must carry information.

**Discussion — fill, bound, advance** [@mensh2017, Rule 8]. First paragraph
summarises the key findings; following paragraphs each take a weakness or strength,
link it to the literature, and often close on a future direction; the section
culminates in how the work moves the field forward. Carandini [@carandini2022]:
the Discussion's real job is to draw **conclusions** (higher-level, independent of
the specific procedures) as opposed to summaries; return explicitly to the
Introduction's questions; keep using the same words; and state the limitations
plainly. Aim for a paper understandable from **title, abstract, and figures alone**.

## Craft: sentences, words, numbers [@carandini2022]

- **Old before new.** A sentence is far easier to read when its beginning links to
  prior (given) information and the **new information arrives at the end**, where
  readers expect it (Gopen & Swan 1990). Carandini calls this "often the single but
  devastating reason why scientific prose is impenetrable" — when a paragraph won't
  parse, reorder each sentence old→new first.
- **Omit needless words** (Strunk & White). Pass over every word; if cutting it
  doesn't change the meaning, cut it. Reflexively drop "respectively," "recent,"
  "very."
- **Active voice, strong verbs.** *"We implanted the widget,"* not *"the
  implantation of the widget was performed."* *"A depends on B,"* not *"A is
  dependent on B."* Use the passive only as a conscious choice when the acted-upon
  is the real subject.
- **Topic sentences** [@carandini2022]: the paragraph is the unit of text; each
  makes one point, summarised in its first sentence. If you can't write that
  sentence, the paragraph needs splitting. Topic sentences in sequence form a
  summary of the paper — a first draft of the abstract. (Carandini bolds every
  topic sentence until the paper is done; this style is "assert/justify" — assert,
  then justify for those who care.)
- **Numbers**: move statistics, CIs, and p-values into tables/legends/Methods; keep
  precision reasonable and consistent (61%, not 61.37%).

## Process [@mensh2017, Rules 9–10]

- **Allocate time where readers are**: title, abstract, figures, and the outline —
  Methods is read least, so budget accordingly.
- **Outline before prose**: one informal sentence per planned paragraph; start from
  the result descriptions that become the results headers. Scrutinise each
  paragraph's role at the outline stage to avoid wordsmithing paragraphs that won't
  survive.
- **Iterate with feedback**: reduce, reuse, recycle; don't get attached — trashing
  and rewriting a paragraph often beats incremental editing. If you can't describe
  the whole outline to a colleague in a few minutes, distill further. Use
  [@mensh2017]'s Table 1 (signs each rule is violated) as a review rubric.
- **Grant Specific Aims** [@carandini2022]: pour effort into the first page;
  Carandini's "10 key sentences" — (1) what the project achieves, (2) why it
  matters, (3–5) the three aims as questions/hypotheses, (6) the general approach,
  (7–9) the three aims as specific approaches, (10) how the world differs once done.

## Two modes of use

**Drafting.** Start from the contribution sentence and the list of questions.
Outline at the claim level (title → abstract C-C-C beats → one topic sentence per
results paragraph) before any prose. Draft section by section, applying C-C-C and
old-before-new.

**Reviewing.** Diagnose *structure* before wording — reordering and cutting beat
line-editing. Name the rule you invoke ("Rule 7: end the paragraph on the sentence
that answers its question") so the author learns the principle. Read top-down as a
naïve reader: from title → abstract → figures, can they reconstruct the
contribution? Use this fast diagnostic (from [@mensh2017] Table 1):

| Symptom | Likely rule broken |
|---|---|
| Reader can't give a one-sentence summary | Rule 1 (one contribution) |
| Reader doesn't "get" the paper | Rule 2 (write for the naïve reader) |
| "Why are you telling me this?" / "So what?" | Rule 3 (C-C-C) |
| Reader stumbles over one passage | Rule 4 (flow) / old-before-new |
| No elevator pitch after the abstract | Rule 5 (abstract) |
| Little interest in the paper | Rule 6 (intro never names the gap) |
| Reader disputes the conclusion | Rule 7 (results don't justify it) |
| Unanswered objections linger | Rule 8 (discussion) |

## Never

- Invent results, citations, or `[@citekey]`s, or overstate a finding to make the
  story cleaner — flag the gap instead (consistent with the vault's AGENTS.md).
- Rewrite the author's meaning or voice into your own; tighten, don't replace.
- Add a figure, panel, or supplementary item the text never walks the reader
  through — if it isn't mentioned, it probably shouldn't be in the paper.
