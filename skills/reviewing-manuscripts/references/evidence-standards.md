# Evidence standards for reviewing a data-driven / ML paper

Named standards to cite in a review, so a criticism is not just the reviewer's opinion.
All five sources are in the neubrain library, tagged to the `writing` project.

| Citekey | Use it for |
|---|---|
| `bourne2006` | Reviewer conduct: Ten simple rules for reviewers (PLoS Comput Biol). |
| `zyromski2025` | Practical order of reading a manuscript (Surgery Open Science primer). |
| `kapoor2023` | Leakage taxonomy + model info sheets (Patterns). |
| `walsh2021` | DOME: Data, Optimization, Model, Evaluation recommendations for supervised ML in biology (Nat Methods). |
| `collins2024` | TRIPOD+AI: reporting checklist for clinical prediction models, regression or ML (BMJ). |

## Leakage: the eight types (kapoor2023)
Leakage = a spurious relation between features and target created by collection, sampling or
preprocessing. It inflates reported performance. Ask which of these the paper rules out.

**L1 — training and test not cleanly separated**
- L1.1 no test set at all.
- L1.2 **preprocessing fitted on train+test** (imputation, normalisation statistics, smoothing, outlier
  removal, over/under-sampling). Removing outliers from the *target* across the whole dataset belongs here.
- L1.3 **feature selection on train+test**.
- L1.4 duplicate records split across train and test.

**L2 — illegitimate features**: a feature that proxies the outcome, or that would not be available at
prediction time.

**L3 — test set is not from the distribution the claim is about**
- L3.1 **temporal leakage**: test data predate training data while the claim is about the future.
- L3.2 **non-independence**: train and test share the same subject, animal, cell, site, device or family.
  The split must be at the level the claim generalises over.
- L3.3 **sampling bias in the test set**: one site, batch, protocol or an excluded "borderline" group,
  while the claim is broader.

## Evaluation and "state of the art" (walsh2021, DOME)
DOME names *"the method is falsely claimed as state-of-the-art"* as a standard failure. What to require:
- compare with public methods **and simple baselines**, **on the same dataset and the same splits**;
- a final **independent held-out** evaluation;
- **confidence intervals / error intervals and statistical tests**, not point estimates;
- state explicitly that the evaluation set was **not** used for feature selection, preprocessing or tuning;
- report performance on training *and* test data, and flag highly variable performance;
- release code, trained models, data, and the **exact splits**.
DOME also asks for parameter count `p`, feature count `f`, how they were chosen, and run time.

## Reporting checklists by paper type
- Supervised ML in biology → **DOME** (`walsh2021`).
- Clinical prediction model, regression or AI → **TRIPOD+AI** (`collins2024`): data sources and
  participants, sample size, missing data, model development, evaluation, fairness, **limitations
  including generalisability**, and data/code availability.
- Engineering ML application (no patients): DOME's Evaluation rules still apply; TRIPOD+AI does not.

## Reviewer conduct (bourne2006)
1. Accept only if you can meet the deadline; decline early otherwise.
2. Decline on any conflict of interest, even a possible one.
3. Write the review you would want as an author: every criticism supported by a concrete reason.
4. Your comments are part of authoring — they should make the paper better.
6. Read the whole manuscript before forming the review, then the journal's guide for authors.
7. Do not over-invest in a paper that is clearly weak; be useful, not exhaustive.
8. Keep anonymity: never suggest the authors cite your own work (the EAAI form says the same).
9. Neutral tone, succinct, point-by-point, **and decisive**.
10. Use the confidential comments to the editor — but only for points supported by the review itself.

**Confidentiality (why the tooling is built this way):** a manuscript under review is confidential.
Never paste its text, figures or data into an external service, including a third-party AI tool.
Only *published reference metadata* (a reference string, a DOI) may go to Crossref/OpenAlex/Unpaywall;
the manuscript's own text stays local, and its extracted text and page renders stay out of git.
