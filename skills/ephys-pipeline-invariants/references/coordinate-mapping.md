# Anatomical Coordinate Mapping — HERBS RAS → Allen CCF

Read this before touching `atlas_mapper.py`, `main_pipeline.py`, `rederive_vox.py`,
or anything that turns a probe trajectory + cell depth into a region label or
voxel coordinate. This is the most damaging bug-class in the pipeline: when it is
wrong, **every** anatomical assignment is wrong, usually invisibly.

## The locked transform (do not search or tune it)

HERBS exports each probe's `insertion_vox` / `terminus_vox` in its **native RAS
axis order `[ML, AP, DV]`** (origin left / bottom / back). The Allen CCF
annotation is queried in **`asr` order `(AP, DV, ML)`**. The conversion is a
reorder **plus a flip of all three axes**:

```
# vox is HERBS RAS [ML, AP, DV]; returns Allen asr index (ap, dv, ml)
ml, ap, dv = vox
ap_idx = (N_AP - 1) - ap
dv_idx = (N_DV - 1) - dv
ml_idx = (N_ML - 1) - ml
```

with Allen 10 µm volume dimensions:

```
N_AP, N_DV, N_ML = 1320, 800, 1140
```

Register against **`allen_mouse_10um`** (BrainGlobe), **not** a Kim atlas. The
probe voxels are Allen voxels; querying a different atlas sends every cell to
annotation id 0 (outside brain).

## Why it is *locked*, not fitted

The transform is fixed by a geometric proof, so it must never be re-chosen to
maximize a hit-rate (that would be circular). For every session,

```
bregma = insertion_vox - insertion_coords / 10
```

comes out **identical** across all sessions, with the ML component at the volume
midline (`N_ML // 2`) and the DV component at the dorsal surface (`≈ N_DV - 1`,
where bregma sits). Those are not free parameters — they are forced by anatomy —
so the single convention above is the only one consistent with the data. The ML
flip is always applied (RAS left-origin → asr right-origin) and *preserves* true
laterality; the sign of `insertion_coords[0]` agrees with the asr-ML hemisphere
for every session.

## The bug this prevents (regression test in narrative form)

The original pipeline assumed the probe voxels were already in Allen `asr` order
and flipped only the DV axis. Result: ~100% of cells landed in hindbrain or
outside the brain (annotation id 0), and the stored `AP/DV/ML_vox` were
meaningless. Earlier "depth-direction" and "DV-flip" patches were partial
workarounds and are **superseded** — do not reintroduce them. The tell-tale
signature of this regression is a **high outside-brain fraction**; after the
correct transform it should be ~0 for every session.

### Guardrails

- Do not change axis order or which atlas is queried without re-deriving the
  bregma proof above; if bregma is no longer session-invariant, your change is
  wrong.
- Keep the outside-brain fraction as a **hard QC tripwire** (e.g. flag any
  session above a few percent). A jump here means the transform broke.
- Per-cell positions are interpolated **continuously** along
  insertion→terminus, depth measured from the tip (= terminus). Do not replace
  this with a fixed-µm-per-channel step; a stepped conversion mis-scales probes
  whose channel pitch differs from the assumed step.

## Histology labels are authoritative; the atlas lookup is QC only

Region and layer come from the **registered histology label** (the HERBS pkl),
not from the atlas voxel lookup:

- Target structures are remapped to project-standard acronyms with their layer
  (e.g. piriform → `PCX` + layer, AON family → `AON`), and the histology label
  wins.
- **Every other cell takes its `Broad_Region` = its own histology acronym**
  (e.g. `AIv5`, `EPd`, `CP`). This is deliberate: a real acronym never
  spuriously matches a target substring (`pir`/`pcx`/`aon`) in a downstream
  region selection, which is exactly how non-target cells used to leak into a
  target population.
- The Allen atlas region from the voxel lookup is retained **only** in the QC
  fields (`Atlas_Name` / `Acronym`). It must never override the histology label.
- Never let a non-target cell fall back to `'Unknown'` or to any string
  containing a target acronym. Region selection downstream is substring-based, so
  a sloppy placeholder silently inflates a population.

### Layer subdivision within a flat histology segment

When the histology marks a flat target segment (e.g. `PIR`) without a sublayer,
subdivide it by **relative depth within the segment** using atlas-derived layer
proportions, oriented by the probe-depth convention (tip = deepest). Keep the
boundary fractions in one named constant and document which end is deep vs
superficial — the orientation is easy to invert and produces a plausible-looking
but wrong layer assignment.

## Files

- `py_tools/atlas_mapper.py` — `vox_to_allen_asr`, `HERBSTrajectoryMapper`,
  `remap_pkl_region`, layer subdivision.
- `py_tools/main_pipeline.py` — orchestration; applies `vox_to_allen_asr` then
  the histology-authoritative label precedence.
- `py_tools/rederive_vox.py` — standalone re-derivation + independent QC
  (outside-brain %, label agreement, hemisphere); the locked transform and the
  bregma proof are documented in its header. Use it as the QC reference after any
  change here.
