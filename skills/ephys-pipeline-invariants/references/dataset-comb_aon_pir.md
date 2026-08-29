# Dataset-Specific Facts — `comb_aon_pir` (AON/aPCx revision)

These facts are true for the **current** dataset only; they are not general
pipeline invariants. Load this when working on `comb_aon_pir`. Verify against the
data before relying on any count — do not treat these as eternal.

- **Dataset root:** `/mnt/sysfs01/users/cagatay/aon_pir_rev/comb_aon_pir`
  (processed structs under `processed_data/`).
- **Canonical session set:** authoritatively enumerated in
  `rederive_vox.SESSIONS`, drawn from three sources:
  - `aon_pir_KILO/KILO_data`: MB019, MB018×2, MB021, MB022×2, MB023, MB026,
    MB050 (181114 only), MB053×2
  - `aon_pir_KILO2/KILO_data`: MB107, MB110, MB111, MB112, RDP009, MB118
  - `260422_track/KILO_data`: RDP144, RDP145, RDP146, RDP147, RDP148
  Two paper-era sessions are **excluded by design** (see below): `181115_MB050`
  (uncurated) and `181122_MB052_1` (known-bad).
- **Raw-metrics sessions:** RDP144/145/146/147/148 are Neuropixels and carry a
  sorter `metrics.csv` with a `duration` column (used to validate template
  trough-to-peak widths).
- **Hardware is mixed:** Neuralynx 31-ch recordings run at **32000 Hz**,
  Neuropixels at **30000 Hz**, sometimes within the same KILO folder. Always read
  the rate from `params.py` (see the sample-rate rule in
  `cell-typing-and-responsiveness.md`).

## Known-bad / quirky sessions — do not "clean up" without confirming

- **`181115_MB050` is excluded by design — uncurated.** Its KILO_data has no
  `spike_clusters.npy` (only raw `spike_templates.npy`), so there is no curated
  unit table; `main_pipeline.py` now *raises* rather than substitute raw
  templates. It is **not** in `rederive_vox.SESSIONS`.
  (181114_MB050, the prior day for the same animal, is included.)
  Do not re-add without curation.
- **`181122_MB052_1` is a known-bad session.** Hardcoded skips for it exist
  throughout the pipeline. **Do not remove those skips without asking the user.**
- **RDP145 (`240303_RDP145_5`) and RDP146 (`240419_RDP146_5`) have NO fired novel
  trials.** Their novelty CSVs list novel odors, but those valves were never
  actually fired in the experiment. Never treat their "novel" valves as
  presented; any novelty analysis on these two is meaningless.
  - RDP145 presented valves `[1 3 4 5 6 8 9 10 13 14 19 23 27 28]`.
  - RDP146 presented valves `[1 3 4 8 10 11]`.
- **RDP147 / RDP148** novelty mappings were corrected in
  `user_input/novelty_RDP*.csv` (RDP148 = 10 novel odors, RDP147 = 2).

## Probe geometry quirks

- **Custom 31-ch probe** (`haesler_31ch_probe.json`): y=0 at the probe tip
  (deepest), y=500 µm at the headstage end. COM depth from `chan_pos[:,1]` is
  distance from the tip.
- **Neuropixels 2 multi-shank** (KILO2 / track): 15 µm channel pitch, 4 shanks;
  shank assignment from `chan_pos[:,0]` against bounds `[0, 250, 500, 750, ∞]`.

## Recording modality

These are **acute** recordings (different cells per session/day), not chronic —
do not treat inter-session variability as an artifact to correct away.
