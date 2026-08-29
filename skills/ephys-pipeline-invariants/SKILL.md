---
name: ephys-pipeline-invariants
description: >-
  Integrity rules and durable methodology for an in-vivo single-cell
  electrophysiology pipeline: Kilosort spike-sorting outputs → HERBS/Allen-CCF
  anatomical mapping → RS/FS cell typing → sniff/odor alignment → firing-rate &
  responsiveness statistics → spike-quality metrics. Use this WHENEVER you edit
  or reason about anything in py_tools/, workaround/, paper/, func_preprocess_*,
  func_post_*, run_pipeline, atlas_mapper, main_pipeline, kilosort_metrics, or
  any analysis that emits unit counts, firing rates, voxel coordinates, region
  or layer labels, or RS/FS splits — even when the user only asks to "fix",
  "refactor", "rerun", "speed up", or "add a number to" one of these. It encodes
  the fail-loud philosophy and the locked methods (the HERBS-RAS→Allen-CCF
  coordinate transform with its axis flips, trough-to-peak RS/FS typing, the
  per-source sample-rate rule, COM depth, per-stimulus responsiveness) whose
  violation has previously produced silently wrong results. Consult it before
  changing coordinate transforms, sample rates, region/layer assignment,
  response/baseline windows, or cell-typing cutoffs, and to judge whether a
  computed number is physically plausible before trusting it. These are pipeline
  invariants, not findings of any one paper — paper numbers live in the
  manuscript; dataset-specific facts live in references/.
---

# Electrophysiology Pipeline — Integrity Invariants

Institutional memory for a MATLAB+Python pipeline that turns Kilosort spike
sorting + HERBS histology + behavioral events (sniff, odor, novelty) into
publication figures for extracellular recordings in mouse cortex. This skill
holds **durable methodology**: rules about how the pipeline must behave so its
outputs stay correct. It deliberately contains **no paper findings** (firing-rate
benchmarks, population counts, effect sizes) — those are results, not
invariants, and belong in the manuscript. Dataset-specific facts (which sessions
exist, which are known-bad) live in `references/dataset-*.md` and load only when
you work on that dataset.

The governing idea: **every quantity the pipeline emits has a physically
plausible range for the recording and region it came from.** A voxel inside the
brain, a cortical firing rate that isn't 200 Hz, an RS/FS cutoff in time units,
a unit count consistent with the probe. Compute the expected range from the
recording itself — never hardcode a remembered value — and treat anything
outside it as a bug to trace, not a fact to report.

## The non-negotiable philosophy: fail loud, never paper over

This is research code whose outputs go into a paper. A silent wrong number is
far more expensive than a crash, because it can survive into a figure.

- **Never suppress an error or warning to "keep going."** No bare `except:`, no
  `warnings.filterwarnings("ignore")`, no MATLAB `try/catch` that swallows and
  continues. If something the analysis depends on is missing or malformed, raise
  and stop with a non-zero exit.
- **Never invent a fallback value to fill a gap.** A guessed sample rate, a
  hardcoded default coordinate, a "mean of the others" substitute, or an
  `'Unknown'` region placeholder all let a broken recording masquerade as a good
  one. The model to copy is a loader that *raises* when it cannot determine the
  sample rate rather than assuming one — because a single assumed rate is simply
  wrong for a mixed-hardware dataset.
- **Trace every surprising number to root cause.** Do not patch a symptom
  downstream. When a count, rate, or coordinate looks off, find the line that
  produced it. Symptom-patching buries the real defect and leaves the wrong
  number in the figure.
- **`NaN` is a legitimate, honest "undefined" — a fallback number is not.**
  Returning `NaN` when a quantity is genuinely undefined (too few spikes for an
  ISI, singular covariance for a cluster metric) is correct: NaN propagates
  visibly and gets excluded from means, whereas a fabricated `0.0` or `30000.0`
  silently corrupts them. Preserve real NaNs; never *manufacture* a non-NaN to
  dodge one.

If a user asks you to "just make it run" by adding a try/except or a default,
push back and name the invariant it would hide.

## Sanity-checking computed numbers (no hardcoded benchmarks)

Do not memorize paper values. Instead, for any quantity, derive the plausible
range from first principles and the recording, then check:

- **Coordinates** must land *inside the brain*. After a correct atlas transform,
  the fraction of cells mapped outside the annotation should be ~0. A large
  outside-brain fraction (especially near 100%) is the signature of an axis-order
  error in the coordinate transform — see `references/coordinate-mapping.md`.
- **Region/layer labels** must come from the authoritative histology source, not
  be silently overwritten by an atlas lookup used for QC. A region count that
  suddenly balloons usually means a whole probe track was relabeled — trace it.
- **Firing rates** must be physiologically plausible for the cell class and
  region (cortical principal cells are slow; interneurons faster). A population
  mean that jumps is usually a *selection* artifact (a spike-amplitude or
  quality threshold) or a cell-type mix change, not biology — trace it before
  believing it.
- **RS/FS cutoff** must be in **time** units (~0.4 ms trough-to-peak), never in
  amplitude-ratio units. A cutoff "around 0.4" applied to the ratio metric is a
  category error — see `references/cell-typing-and-responsiveness.md`.
- **Counts** (sessions, units, trials) must match the known inputs. Compare to
  the dataset reference, not to memory.

When a value is out of range, **stop and trace** — that is the whole point.

## The locked methods (do not re-derive or "tune" these)

Each links to a reference; read it before editing the relevant code.

1. **Anatomical coordinate transform — HERBS-RAS → Allen-CCF.**
   The single most damaging class of bug. The transform is *locked by a
   geometric proof*, not chosen by hit-rate. See
   `references/coordinate-mapping.md`.
2. **RS/FS cell typing — trough-to-peak duration, ~0.4 ms, Neuropixels-only;
   amplitude ratio is reference-only.** See
   `references/cell-typing-and-responsiveness.md`.
3. **Per-stimulus responsiveness + firing-rate windows — per-odor, drop early
   trials, fixed windows.** Same reference.
4. **Sample rate from source, never defaulted; COM depth from `pc_features`
   measured from the probe tip, continuous (pitch-independent).** Same
   reference.

Spike-quality metric conventions (ISI refractory period, L-ratio radius, etc.)
are also in `references/cell-typing-and-responsiveness.md`.

## Quick rules you can apply without opening a reference

- **Coordinate transform is fixed, not searched.** HERBS `insertion_vox`/
  `terminus_vox` are native **RAS order `[ML, AP, DV]`**. To Allen `asr`:
  `ap=(N_AP-1)-AP`, `dv=(N_DV-1)-DV`, `ml=(N_ML-1)-ML` — **reorder + flip all
  three axes** (Allen 10 µm dims `N_AP,N_DV,N_ML = 1320,800,1140`). Register
  against **`allen_mouse_10um`**, *not* a Kim atlas. Never tune this against
  hit-rate; it is fixed by the bregma proof (the implied bregma is identical for
  every session).
- **Histology label precedence:** the registered histology label (pkl) is
  authoritative for region and layer. The atlas lookup is QC only and lives in a
  separate field — it must never override the histology label, and a non-target
  cell must never fall back to a string that *contains* a target acronym.
- **Cell typing uses trough-to-peak duration (cubic-upsampled ×10), cutoff
  ~0.4 ms.** Narrow=FS interneuron, broad=RS principal cell. The peak/trough
  amplitude ratio is *reference only* — never type cells with it. Type
  **Neuropixels cells only**; exclude probe families that fail a bimodality
  (Hartigan dip) test.
- **Every DAQ stream carries its own sample rate; read each from its own
  metadata, never share one rate across streams or hardcode it.** A session has
  three independent clocks that do **not** match:
  - **spikes (imec AP):** `params.py` `sample_rate` / `.ap.meta` `imSampRate`
    (~30 kHz), or an explicit `--fs`. If none is available, **raise** — do not default.
  - **NIDQ aux (SpikeGLX events):** `.nidq.meta` `niSampRate`.
  - **TDMS events:** `srate = 1/wf_increment` (the channel's `wf_increment`
    property) — never a hardcoded 1000 Hz.
  A correct spike rate does **not** imply a correct events rate: MB107 session 1's
  TDMS is 3000 Hz while its spikes are 30 kHz, and the old hardcoded 1000 Hz
  stretched that session's event timing 3×. (TDMS is only a sync cross-check, but
  a silently-wrong rate makes a good recording look mis-synced.) Use a rate only
  to *recognize* hardware (32 kHz vs 30 kHz flags the acquisition system), never
  to assume one.
- **Responsiveness is per-stimulus, not pooled:** for each odor drop the first 3
  occurrences (early sniff/novelty confound), require ≥4 remaining trials, and
  compare a baseline window to the response window with a rank-sum auROC
  (`U/(n1·n2)`). A cell is responsive if **any** stimulus reaches p<0.05; excited
  if auROC>0.5 & p<0.05. Keep the response and baseline windows fixed and
  *consistent across scripts* — silently mixing two baseline windows shifts every
  firing-rate statistic.
- **Depth is COM-weighted from `pc_features[:,0,:]`, measured from the probe tip
  (= `terminus`),** interpolated *continuously* along terminus→insertion as a
  span-fraction (pitch-independent). Never reintroduce a fixed µm-per-step depth
  conversion — it mis-scales probes whose pitch differs from the assumed step.

## How to use this skill in practice

When you are about to edit pipeline code or report a result:
1. Identify which locked method (if any) the change touches.
2. Open the matching reference and confirm the invariant before *and* after your
   edit.
3. After running anything, derive the expected range for each output and compare.
   An out-of-range value is a stop-and-trace, not a footnote.
4. If you must add error handling, make it *louder*, never quieter.
5. For dataset-specific facts (which sessions, which are known-bad), consult the
   relevant `references/dataset-*.md` rather than assuming.

## Repo hygiene & file lifecycle

Pipeline code and throwaway code must never mix. A debug script left in a
production directory gets imported, scheduled, or trusted by accident — exactly
the kind of silent contamination the fail-loud philosophy exists to prevent.

- **All experimental, test, debug, or one-off scripts live ONLY in `scratch/`.**
  Name them `YYYYMMDD_<intent>.py` (e.g. `20260619_check_mb050_clusters.py`) so
  the date and purpose are obvious at a glance.
- **Never create test or debug scripts in `py_tools/`, `workaround/`, or the
  repo root.** Those directories hold only production pipeline code. If you need
  to poke at something there, write the probe in `scratch/` and import from the
  real module — do not drop a scratch file beside it.
- **When a script has served its purpose, move it to `archive/`** with a
  one-line header comment stating what it was for and whether it's worth keeping
  (e.g. `# 20260619 one-off: verified MB050 has no spike_clusters.npy. Keep as
  reference for the curation backstop.`).
- **Never silently delete a script.** Moving it to `archive/` is the *only* way
  to retire one — that preserves the record of what was tried and why. Deleting
  destroys that history; if a script truly looks worthless, archive it with a
  note saying so rather than removing it.
