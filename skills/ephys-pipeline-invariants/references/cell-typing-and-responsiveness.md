# Cell Typing, Responsiveness, Depth, Sample Rate & Quality Metrics

Durable *methods* — the procedures the pipeline uses, independent of any paper's
results. Read before editing `compute_waveform_width.py`, `rsfs_classify.py`,
`kilosort_metrics.py`, `responsive_perodor.py`, `firing_rates_responsive.py`,
`main_pipeline.py`, or the MATLAB alignment/responsiveness scripts.

## RS/FS cell typing

**Metric:** trough-to-peak **duration in ms** of the primary-channel template
waveform, cubic-upsampled (×10) to remove the 1/fs discretization. The primary
channel is the most-negative one (`argmin` of the per-channel minimum).

```
trough = argmin(w)
peak   = trough + 1 + argmax(w[trough+1:])
ttp_ms = (peak - trough) / (fs * upsample) * 1000
```

**Cutoff:** ~**0.4 ms**. Narrow (below cutoff) = fast-spiking interneuron; broad
(at/above) = regular-spiking principal cell. The cutoff is obtained as the
decision boundary between the two means of a 2-component Gaussian mixture fit to
the trough-to-peak distribution; a fixed published cutoff may be passed
explicitly, but it is still a **time** in ms.

**Never type cells with the amplitude ratio.** The peak/trough *amplitude* ratio
(`p2t_ratio` / `p2t_amp_ratio`) is recorded for reference only. Using it — or any
cutoff in ratio units — for RS/FS is a category error and the regression this
rule prevents. Half-width (ms) is likewise a descriptor, not the classifier.

**Neuropixels only.** Type cells from NP probes; exclude probe families whose
trough-to-peak distribution is not bimodal (fails a Hartigan dip test). Mixing a
non-bimodal probe family into the GMM corrupts the cutoff.

**Validation pattern (kept, but not a hardcoded number):** template-derived width
is cross-checked against the raw sorter `duration` on the sessions that have it;
agreement is judged on the **classification** (same side of the cutoff), not on
per-cell correlation — RS cells cluster tightly so the raw correlation is low even
when the split agrees. Disagreements should concentrate within a narrow band
around the cutoff.

## Sample rate — from source, never defaulted

Read each recording's sample rate from its `params.py` (`sample_rate = …`), or
accept an explicit `--fs`. **If neither is available, raise** — do not assume a
rate. A single assumed rate is wrong for a mixed-hardware dataset (different
acquisition systems run at different rates, sometimes within one folder). Use the
rate only to *recognize* hardware downstream (e.g. one system runs at 32 kHz,
another at 30 kHz), never to fill a gap. The canonical implementation is
`main_pipeline._read_fs()`, which raises `ValueError` rather than default;
copy that behavior. (A standalone helper with a fallback default exists for a
narrow tool — treat that fallback as a latent hazard, not a pattern to spread.)

## Depth — continuous COM from `pc_features`, measured from the tip

Per cluster, compute a center-of-mass depth from the first PC feature
(`pc_features[:, 0, :]`), weighting each contributing channel's y-coordinate by
its squared feature value:

```
w = pc_features[idx, 0, :] ** 2
depth = mean( sum(y_coords * w, axis=1) / sum(w, axis=1) )   # guard /0 with 1e-10
```

This depth is measured **from the probe tip**, then interpolated **continuously**
along the shank's terminus→insertion line as a span-fraction (so it is
pitch-independent). Never reintroduce a fixed µm-per-channel step: a stepped
conversion mis-scales any probe whose pitch differs from the assumed step, and
that error then flows straight into the atlas lookup.

## Per-stimulus responsiveness & firing-rate windows

Responsiveness is computed **per stimulus**, then OR-ed across stimuli — not
pooled across all trials. For each cell × each odor (`trial_chem_id`):

- **Drop the first 3 occurrences** of that odor (`occur > 3`) — early
  presentations carry a sniff/novelty confound.
- Require **≥4 remaining trials** for the rank-sum.
- **Response window:** `[aligned_onset, +0.4 s]` (rate = spikes / 0.4).
- **Baseline window:** keep it fixed and *consistent across every script*.
  Different scripts may legitimately offer more than one baseline definition
  (e.g. a pipeline window vs a "seconds-prior" window), but a given analysis must
  pick one and use it everywhere — silently mixing two baseline windows shifts
  every firing-rate statistic.
- **Statistic:** Mann-Whitney U → auROC = `U / (n1·n2)` (two-sided p). A cell is
  **responsive** if *any* odor reaches p<0.05; **excited** if auROC>0.5 & p<0.05.

Pooling all trials instead of going per-stimulus gives a *different, generally
larger* responsive count — they are not interchangeable. When comparing to an
older population, state which method produced each number.

## Spike-quality metric conventions

From `kilosort_metrics.py` — keep these constants stable; they define
comparability across sessions:

- **ISI violations:** refractory period **1.5 ms** (`0.0015 s`); percentage of
  ISIs below it. `NaN` if <2 spikes (a real undefined, not a fallback).
- **L-ratio / isolation distance:** features within **68 µm** of the primary
  channel; noise spikes subsampled to a cap (default 100 000); `NaN` on singular
  covariance or too few spikes — preserve these NaNs.
- **Firing rate / presence ratio:** over the global recording span; presence
  ratio is the fraction of 100 time-bins containing ≥1 spike.
- **Amplitude cutoff:** approximate fraction of spikes missing from the amplitude
  histogram, capped at 0.5; `NaN` if <10 spikes.

These functions return `NaN` for genuinely-undefined cases by design. That is the
correct behavior — do not "fix" a NaN by substituting a number.
