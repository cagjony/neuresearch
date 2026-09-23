---
name: reviewing-manuscripts
description: Use when the user is a peer reviewer / referee for a submitted journal manuscript (a manuscript number like EAAI-26-18624, an Editorial Manager review page, a referee report form, "I am the reviewer of this paper", "write reviewer comments"), or asks whether a paper's claims, citations, benchmarks or generalization hold up. Also for checking suspected hallucinated text or fabricated references in someone else's paper.
---

# Reviewing manuscripts

## Overview
A review is a list of **verified** findings, each traceable to a page/line of the submission or a
table/cell of a source paper. Nothing goes into the report that was not checked against a document.
The reviewer's checklist below is ordered by priority. Work top to bottom and report in that order.
Name the standard a criticism rests on (leakage type, DOME, TRIPOD+AI) — see `references/evidence-standards.md`.

## Before accepting (bourne2006)
Decline if you cannot meet the deadline, or on any conflict of interest. **The manuscript is
confidential: never paste its text, figures or data into an external service, including a third-party
AI tool.** Only published reference metadata (a reference string, a DOI) may go to Crossref, OpenAlex
or Unpaywall. Never ask the authors to cite your own work.

## Setup (neubrain vault)
1. `python src/new_project.py --vault <neubrain> --name <MS-NUMBER>`. Write in `plan.md`: "this is a PEER REVIEW".
2. Put the submission in `archive/`. **It is confidential.** Never commit or push the PDF or the notes (`*.pdf` is gitignored), and ask before committing anything.
3. `pdfinfo` the PDF first: creator, dates, an assigned DOI or journal/volume in the metadata tell you whether you are really holding an unpublished manuscript. An anomaly there is a note **to the editor**, not to the authors.
4. `pdftotext -layout archive/<ms>.pdf review/ms.txt`. Read **all** of it before judging anything.
5. Render the pages with figures: `pdftoppm -r 200 -png`. Crop and zoom on every data figure. Re-render any page whose table drives a finding — it rules out a text-extraction artifact.
6. Fetch the cited papers: `fetch_papers.py`. It uses Europe PMC and misses most engineering journals, so a MISS does not mean paywalled. Try Unpaywall and arXiv next. Give the user a DOI list of what is still missing. The user may drop PDFs anywhere in `archive/`: identify each by the DOI printed inside, then run `ingest.py --file F --doi D`.

## The checklist (priority order)
| # | Check | How |
|---|---|---|
| 1 | Hallucinated text | Look for parameters, modules or facts that do not exist (e.g. a "sparse selection parameter of Mamba"). Look for author names that differ from the reference entry, captions that contradict the text, text that contradicts its own figure, and "Author et al." with no number. |
| 2 | Hallucinated references | **Always run the full sweep, never spot-check:** `python <neuresearch>/src/verify_refs.py review/ms.txt review/refs_check.tsv`. It needs only `ms.txt`, so it works with no vault project and costs one call. Resolve every low `title_sim` by hand. Spot-checking "the two decision-relevant" references is how a fabricated one survives. |
| 3 | Claim is in the cited paper | Open the source and find the sentence or table. Verdicts: supported / unrelated / wrong source / wrong reference number. |
| 4 | Generalization | List every generalization claim in the abstract, introduction and contributions, next to the splits actually used. Within-dataset splits are not generalization. Ask what the claim generalises **over** (subject, animal, site, device, protocol, chemistry) and whether the split is at that level — otherwise it is leakage L3.2. A single site/batch/protocol test set under a broader claim is L3.3. Find out whether other papers on the **same datasets** ran cross-dataset, cross-site or small-sample tests; cite them as the expected standard. Count the actual test units. |
| 5 | Arbitrary numbers & leakage | Look for unstated hyperparameters (window length, filter settings, "predefined rules") and design choices selected on **test** results. Walk the leakage list in `references/evidence-standards.md`: preprocessing or feature selection fitted on train+test (L1.2/L1.3), duplicates (L1.4), illegitimate features (L2), temporal leakage (L3.1). Outlier removal applied to test targets is L1.2. |
| 6 | Figures overselling | Compare box plots with table means (best baseline seeds vs. the proposed model's mean). Check that text claims match the figures. Look for truncated axes, results placed in the introduction, and unexplained asterisks. |
| 7 | p-values | Look for test shopping, or no test at all behind the word "significant". What is the unit of replication (cell, seed, sample)? DOME asks for confidence intervals and tests, not point estimates. |
| 8 | Open data / code | Is it "on request" only? Are ablations run only on private data? DOME asks for code, trained models, data **and the exact splits**. |
| 9 | AI-use declaration | Check whether the journal requires one (Elsevier does). |
| 10 | Novelty | Compare equations with known sources for uncredited modules. Is the gain within the seed spread? Is a more important result left unshown? |
| 10b | Internal arithmetic | Recompute **every** average, percentage improvement and "X% better" claim from the paper's own tables. A prose average that does not match the printed rows is a real finding (verified case: a claimed baseline mean of 0.0469 / "37.5% improvement" where the table's four values average 0.0450 → 34.9%). Check the base of each percentage too. |
| 10c | Repeated values | Scan results tables for values that repeat where independent runs should differ: a proposed method matching a baseline to 4 decimals, or one row duplicating another across several models. This is a data-integrity flag — ask for per-run logs. Re-render the page as an image before reporting it. |
| 11 | Benchmark fairness | Trace **every** number in each comparison table to the source's table, cell or trial (see below). DOME names "falsely claimed as state-of-the-art" as a standard failure and asks for comparison against public methods **and simple baselines on the same splits**. Check every baseline is **named and cited**: a comparator that appears only as an acronym with no reference is unverifiable. |
| + | Padding / self-citation | Compare OpenAlex affiliations of the references with the authors' institution. In a blind submission, infer the institution from an in-house dataset. Also flag off-topic citations. |

## Tracing benchmark numbers (check 11)
For each copied value, record: source table, row, and whether the value is a **published mean**, a **single
best cell/trial/batch/setting**, or a **chimera** (best MAPE and best RMSE taken from different runs). Also record the
source's **task** (estimation, forecasting, transfer, out-of-distribution, small-sample, partial-charge). Then say
which direction any bias runs: copying a competitor's best cell flatters the *competitor*. The finding is
**non-comparability**, and the request is to re-run the baselines on identical test cells.

## Reporting standards to cite
Supervised ML in biology → DOME (`walsh2021`). Clinical prediction model → TRIPOD+AI (`collins2024`),
whose checklist includes limitations and generalisability. Leakage → `kapoor2023`. Details and citekeys:
`references/evidence-standards.md`.

## Output
- `draft/manuscript.md`. **Part A:** reviewer notes, ordered by the checklist, with evidence (ms line refs, source table/cell). **Part B:** one section per field of the journal's form.
- `review/submission_answers.txt`: plain text (no markdown) in the order of the submission page, generated from Part B.
- Comments to authors: a neutral summary, then major comments ordered by importance, then minor comments. Each comment says what is wrong, where, the evidence, and the exact fix requested. Never ask authors to cite the reviewer's own work.
- The recommendation is the user's decision. Suggest one, with the reason — but be decisive in the writing (bourne2006 rule 9), and keep the confidential comments consistent with the comments to the authors (rule 10).
- Do not over-invest in a clearly weak paper: enough evidence to support each point, then stop (rule 7).

## Common mistakes
- Calling values "cherry-picked in the authors' favour" before checking which direction the bias runs.
- Trusting a fetch MISS or a top Crossref hit without opening the paper.
- Spot-checking a couple of references instead of running the full sweep (check 2) — cheap, and it is how a fabricated reference survives.
- Treating a matched reference *title* as proof that the cited *claim* is supported.
