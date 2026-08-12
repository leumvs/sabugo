# Sabugo worker

The image pipeline. It reads a root scan and measures it — length, diameter, surface area and volume, globally and per diameter class — writing a `features.csv` row per image or per region of interest, plus the segmented and feature images.

What those numbers are worth is the subject of most of this file. They are checked against three kinds of external ground truth, beside the three established tools in the field, and every table below is generated from versioned results rather than typed.

This is not a Bun workspace. It has its own manifest, its own virtual environment and its own test runner, and it never goes in the root `workspaces` array.

> **Licence and provenance.** Parts of the pipeline are ported from [RhizoVision Explorer](https://github.com/predictivephenomics/RhizoVisionExplorer) and from the `cvutil` library beside it, both GPL-3.0, Copyright (C) Noble Research Institute, LLC. The modules carrying ported code declare it in their header, and the licence section of [`../README.md`](../README.md) records what the derivation obliges. That is where some of the code came from. It is not what the measurements are judged against: below, RVE is one of three tools compared against ground truth, on the same footing as WinRhizo™ and IJ_Rhizo.

## How it was built

**Two repositories, and the more important one is not the obvious one.** `RhizoVisionExplorer` carries the feature extraction, the topology and the pruning — `feature_extraction.cpp`, `roottopology.cpp`, `rootsegmentprop.cpp`. But **skeletonization is not in that repository at all**: ridge detection and steepest ascent live in `cvutil/cvutil_bwskel.cpp`, a separate GPL-3.0 library by the same authors. Anyone looking for the hardest algorithm in this project in the RVE repository will not find it.

| Module here | Translated from |
|---|---|
| `skeleton.py` | `location::isridge`, `bwskel_helper::bwskel` in `cvutil/cvutil_bwskel.cpp` |
| `pipeline.py`, `smooth_contours` | `linesim()` in `cvutil/cvutil_linesim.cpp` |
| `topology.py` | `getroottopology()` in `roottopology.cpp` |
| `pruning.py` | the pruning loop in `roottopology.cpp` |
| `segments.py` | `getrootlength_new()` in `rootsegmentprop.cpp` |

The C++ is scalar and AVX2; this is the same logic vectorised over NumPy. There is no C, C++ or Qt component here — what is derived is the logic, translated, not compiled or linked code.

**The published paper describes the method at a high level and goes silent exactly where one implementation diverges from another**: plateau tie-breaking in ridge detection, the criterion that starts the ascent, the order pruning iterates in. At those points the implementation derives from reading the source rather than the paper. And where the source and the paper disagree with what the measurement shows, the measurement wins — the paper has the angle axis wrong, and the evidence is [below](#whole-root--the-fan).

### The pipeline, in order

1. Red channel of the colour image — the channel a root scan separates best on. 16-bit grey is reduced by division by 257, a linear full-range rescale and never a min–max normalization, which would make the threshold content-dependent.
2. Regions of interest, if any: one sub-image per region, each analysed on its own, each producing its own output row.
3. Threshold — `gray < t`, root dark on a light background — with `--threshold-method otsu` as an alternative.
4. Background and foreground noise filters, by connected-component area in mm².
5. Keep the largest component, unless `--no-keep-largest`.
6. Contour smoothing: simplify the outline and rasterize it again.
7. Distance transform of the mask, which is what carries the diameter everywhere downstream.
8. Skeletonization: ridge detection over the distance transform, steepest ascent to join the fragments, pinhole fill, Guo–Hall thinning.
9. Topology: classify every skeleton pixel as an end, a segment or a branch point by its neighbourhood.
10. Polylines between notable points.
11. Pruning of spurs, by a threshold relative to the local radius.
12. Length by simplified polyline, and aggregation into the four diameter-class histograms.
13. The two derived images: the segmented mask and the skeleton coloured by diameter class.

### Two conventions that are easy to get wrong

**Every mean and every histogram is weighted by length, never by pixel count.** A digital line of euclidean length `L` holds `L·max(|cos α|, |sin α|)` pixels, so a root at 45° carries **29% fewer pixels** than an axis-aligned one of the same length. Counting pixels was a real defect here, in `average_diameter` and in the three angle frequencies — a fan of three equal thirds reported 37/27/36. It is fixed, and both the fix and the mechanism that was wrong are tests.

**Angles are measured from the horizontal**, with agronomic naming: 0° is a horizontal root (*shallow*), 90° a vertical one (*steep*). The paper's wording reads as if it were measured from the vertical, and that is wrong — proven by construction on fans of known angle, [below](#whole-root--the-fan). The insidious part: the frequencies come out **identical under both conventions**, because the bin name compensates for the axis swap. Only `average_root_orientation` betrays it, coming out as `90 − θ`.

### Operational limits

Enforced here, in the worker, because the pipeline is where the cost is:

| Limit | Value | Error |
|---|---|---|
| Resolution | 100 megapixels | `IMAGE_TOO_LARGE` |
| Formats | BMP, JPEG, PNG, TIFF, by magic bytes; multipage TIFF refused | `UNSUPPORTED_FORMAT` |
| Regions of interest | 10 per analysis | `INVALID_PARAMS` |
| DPI | 50–4800, with a warning outside 300–1200 | `INVALID_PARAMS` |

Auto-resizing an oversized image was rejected rather than not implemented: it silently changes the scientific result, because thin roots disappear.

## Layout

```
apps/worker/
  pyproject.toml       distribution sabugo-worker; numpy + opencv-contrib-python-headless 5.0
  .venv/               the only virtual environment in the repo
  src/sabugo_worker/   the package — src layout, so pytest imports what ships and not the cwd
  tests/               pytest
  validation/          the pipeline against external ground truth, next to the three other tools
    compare.py           simulated roots, 800 and 1200 DPI
    wires.py             copper wires, 600 DPI, two thresholds
    synthetic.py         rendered shapes whose truth is exact — no download
    metrics.py           R², RMSE, MBE, and the README tables
    xlsx.py              a minimal .xlsx reader, so no dependency for one workbook
    data/                the downloads. ~2 GB, gitignored
    results/             the CSVs that come out. Versioned, because the images are not
```

**`validation/` is the ground truth of this project**, and it is external on purpose: a growth model's own geometry, a copper wire's gauge, and shapes whose length and diameter are exact by construction. Agreement with any particular tool is not a target — where the established tools disagree with the truth, and they do, agreeing with them would be the wrong result.

`src/` layout is not decoration: without it pytest imports the working directory instead of the installed package, and the suite passes against code that is not what ships.

## Running

```bash
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"
```

### The CLI

No Redis, no database. This is the development loop for the algorithm, and it is what the validation drives.

```bash
python -m sabugo_worker.cli image.jpg --dpi 600 --threshold 220 --segment --feature
python -m sabugo_worker.cli folder/ --dpi 1200 -o features.csv
python -m sabugo_worker.cli scan.jpg --dpi 600 --roipath rois.csv --prune --smooth
python -m sabugo_worker.cli scan.jpg --dpi 600 --preview --segment   # the mask, and stop
```

Pre-processing, feature extraction and output display are all exposed as flags, including `--threshold-method otsu`. `--help` lists them.

`--preview` is RVE's *Preview segmented image*: it segments and returns, skipping `skeletonize` — the dominant stage, about 880 MB of the ~1 GB peak — so it writes no metrics, no CSV and no feature image.

#### The three flags the API drives

The backend runs this same CLI as a subprocess, one process per image — there is no second entry point. Three flags exist for it and are worth knowing, because they are also useful by hand:

```bash
python -m sabugo_worker.cli scan.jpg --dpi 600 --json out.json --progress --max-megapixels 100
```

- **`--json <path>`** writes the result the API republishes verbatim to the browser: `{"pipelineVersion": …, "results": [{"roiIndex": …, "metrics": {…}, "bins": {…}}]}`, with the metric names in camelCase. It carries `thresholdValueUsed` and `numSegments`, which `features.csv` does not, and it reports **where the derived pictures were written** rather than leaving the caller to rebuild the filename from `--ssuffix`/`--fsuffix`. `jsonout.py` reads its per-mode key set from `export.py`, so the CSV and the JSON cannot come to describe different metrics.
- **`--progress`** writes one NDJSON line per finished stage on **stderr** — `{"stage": "skeletonize", "percent": 60, "region": "Full"}` — flushed line by line, which is what lets a reader show progress instead of receiving it all at the end. stderr and not stdout, because stdout is the human report the validation parses. With several regions the percentage is scaled over all of them and never goes backwards.
- **`--max-megapixels`** sets the resolution ceiling that `load_image` has always taken as a parameter and nothing could reach from the command line. The API passes what its environment configures; without the flag the compiled-in 100 MP applied silently no matter what was configured.

### What one image costs

A 20 MP scan at 600 DPI takes **4.4 s** and peaks around **1 GB**. Time is not the constraint; memory is, and it scales with the image: a 54 MP scan is roughly 2.5 GB, which is above the default limit of most containers. Worth knowing before the queue is sized.

| Stage | Peak |
|---|---|
| `load_image` | 40 MB |
| `segment`, steps 1–8 | 200 MB |
| **`skeletonize`** | **880 MB** |
| `classify` | 250 MB |
| `extract` | 130 MB |
| `aggregate` | 1 MB |

Skeletonization is nine tenths of it and the reason is structural: the ridge test and the climb-start gate each materialise 8 shifted copies of the distance map and of the mask, because the whole of it is vectorised over the image rather than looped per pixel. Getting under that means working in tiles, which is real work and should wait for a real memory limit to aim at.

It used to be 1636 MB. Three `np.pad` calls sat inside list comprehensions and rebuilt a full-image copy on each of the eight turns; hoisting them out cut the peak by 46% and changed no pixel of the skeleton.

**`load_image` refuses anything over 100 MP** — `MAX_PIXELS`, around 4.8 GB of peak, which is the ceiling for processing one image at a time. The check is here rather than only at upload because **a limit on the file bounds nothing**: an A4 page scanned at 1200 DPI is 97 MP and compresses to **0.6 MB** as PNG. That is not a crafted payload, it is what a scanner produces, and without the check it reaches skeletonization and dies there instead of returning `IMAGE_TOO_LARGE`.

### Tests

```bash
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"
.venv/Scripts/pytest
```

That is the whole suite — pytest over `tests/`, configured by `testpaths` in `pyproject.toml`, no markers and no `conftest.py`. It is separate from the backend's: `bun test` never runs pytest and pytest never runs `bun test`.

Everything runs anywhere except `tests/test_wire_tables.py`, which skips itself when `validation/data/` is absent — which is most of the time, since the copper wire archive is 1 GB and gitignored. Run a single file with `.venv/Scripts/pytest tests/test_segments.py`, and a single case with `-k`.

**An image pipeline without tests is indistinguishable from a wrong pipeline, because the output looks plausible either way.** So most fixtures are shapes whose truth is analytic, and a measurement that drifts fails the suite rather than only code that stops running:

| Fixture | What it pins |
|---|---|
| **Capsule** — a disc of radius `r` swept along a curve | the medial axis **is** the curve, so length, diameter, area and volume are exact by construction. The most valuable one here: it separated the three parts of the length error and refuted four hypotheses |
| **Crossing** — two capsules at a known angle | occlusion, exact on both sides: the length is the sum of the two, the volume is the two cylinders minus `16r³/(3·sin θ)` |
| **Fan** — `2n` capsules from one point | every whole-root truth in closed form: orientation is the mean of the angles, depth is `L·sin(max) + 2r`, width is `2(L·cos(min) + r)` |
| 200×20 px rectangle at 254 DPI | the mask metrics. ⚠️ the medial axis of a rectangle is **not** its centreline — it sends four arms of `w/2·√2` into the corners, so the length is ~23.7 mm and not 20 |
| Disc of radius 50 px | `network_area` ≈ π·50², `max_diameter` ≈ 100 px |
| A 45° diagonal line | the √2 correction; without it the error is 41% |
| A "Y", and a "Y" with a short arm on a thick trunk | 3 tips and 1 branch point; and that pruning is relative to the local radius |
| The same image at 300 and 600 DPI | the mm metrics have to coincide — this is what catches a unit conversion error |
| The same image at 8 and 16 bits | identical metrics, which is what validates the /257 reduction; a min–max normalization fails here |
| A colour image with divergent R, G, B | segmentation depends on the red channel and nothing else |
| The same image twice | identical output on every key — see the `distanceTransform` trap at the end of this file |
| Blank image, unreadable file, salt-and-pepper noise | `NO_ROOTS_DETECTED` and `INVALID_IMAGE` rather than an exception, and that the noise filter removes noise |

Beside those, property tests: the four totals equal the sums of their own diameter bins, the three angle frequencies sum to 1, length never increases when the noise filter does, and the means are fractions of length rather than of pixels — that last one with a counter-proof that recomputes it unweighted and shows the middle third being lost, so the mechanism stays documented instead of becoming folklore.

**There is no parity test against another tool, and that was a decision.** `fixtures/` once held RVE outputs and the suite treated them as the target: when Python disagreed, Python was wrong. That stopped being valid when validation moved to external ground truth, and it fell in practice when the better length estimator broke parity by construction.

**A test that does not go red when you break what it guards is testing nothing.** After writing a test for an invariant, break the invariant on purpose and confirm it fails.

> ⚠️ **Do that check with `python -B` and no `__pycache__`.** An edit that keeps the file the same size — `min` for `max`, `<` for `<=` — can leave the byte count unchanged, and the import machinery decides staleness from size and mtime. Rewrite twice within one second and the interpreter reuses the old `.pyc`: the mutant never runs, the suite passes, and the survivor looks equivalent. It produced one wrong conclusion already (`best = min(values)` in `validation/metrics.py`). Same-length edits are the most common kind in a mutation check, so this is not an edge case.

### Validation

```bash
.venv/Scripts/python validation/compare.py
.venv/Scripts/python validation/wires.py
.venv/Scripts/python validation/synthetic.py
```

The first runs the pipeline over the 100 renderings at 800 and 1200 DPI and crosses it with the model's ground truth; the second over the 27 copper wire scans at 600 DPI, at **both thresholds** the paper publishes (191 and 222). Both print R², RMSE and MBE for the four tools side by side, then the README table.

Each skips the pipeline when its output CSV already exists (`results/simulated-{dpi}.csv`, `results/wires-{threshold}.csv`). **To re-run, delete the file** — otherwise a changed threshold does nothing.

The third renders its own shapes and needs no download, so its tests run in CI like any unit test.

## The validation data — what to download and where

Not redistributed here: Zenodo, CC-BY, and 1 GB of it. `validation/data/` is gitignored; what enters the repository is the **result**, not the input.

| Zenodo record | File | Size | Extract to |
|---|---|---|---|
| [1159845](https://zenodo.org/records/1159845) | `ground_truth_data_2D.csv` | 17 KB | `validation/data/simulated/` |
| [1159845](https://zenodo.org/records/1159845) | `images.zip` | 35 MB | `validation/data/simulated/` — **flatten it**: the zip nests `images/images/*.jpg`, and the 200 `.jpg` go directly in `simulated/`. Discard `__MACOSX/` |
| [4677553](https://zenodo.org/records/4677553) | `RhizoVisionData_and_stats.zip` | 2.3 MB | its `Inputs/` folder becomes `validation/data/competitors/` |
| [4677546](https://zenodo.org/records/4677546) | `copper_wire_images_data.zip` | 1.02 GB | `validation/data/wires/` — the `.tif`, `RVE_metadata.csv` and the two ground-truth files directly inside |

So the tree ends up as:

```
validation/data/
  simulated/     ground_truth_data_2D.csv + 200 renderings (100 systems × 800 and 1200 DPI)
  competitors/   WinRhizo, IJ_Rhizo and RVE tables — nobody has to re-run the competitors
  wires/         27 usable copper wire scans + RVE_metadata.csv + the physical ground truth
```

The first two are the 100 ArchiSimple simulated root systems of Rose & Lobet (2018) with the model's own ground truth — where branching and overlap appear, so where skeletonization is actually exercised. The third carries WinRhizo™, IJ_Rhizo and RVE already tabulated, so nobody has to re-run three tools to compare against them. The **copper wires** are *physical* truth — gauge for the diameter, a ruler for the length — and are the anchor set: trivial geometry exercises binarization and calibration and barely touches the skeleton, which is precisely the axis where the 800 DPI defect was hiding.

## Results

Every table is generated by the scripts from `validation/results/*.csv` and re-rendered by `tests/test_readme_table.py`, which demands they match. A README number typed by hand is a number that starts lying on the second run.

### Where Sabugo stands

Sixteen cells with external ground truth — four metrics, two datasets, two settings each — ranking the four tools by RMSE:

| Tool | Mean rank | Cells won | Length | Diameter | Surface area | Volume |
|---|---|---|---|---|---|---|
| **Sabugo** | **2.00** | 5 | 2.50 | **1.75** | 2.25 | **1.50** |
| RVE | 2.25 | 4 | **2.00** | 2.25 | 2.25 | 2.50 |
| IJ_Rhizo | 2.50 | **6** | 2.50 | 3.00 | **1.75** | 2.75 |
| WinRhizo | 3.25 | 1 | 3.00 | 3.00 | 3.75 | 3.25 |

Best mean rank of the four, best on volume and on diameter, worst of its own four columns on length. The length column is the interesting one and has a section of its own below.

**The acceptance criterion passes in all sixteen**, on RMSE and on bias. The criterion, fixed before measuring, is to land inside the span the best and the worst of the three established tools already cover between them — not a `< 5%` picked out of the air, and it concedes that the three established tools already disagree with each other. This is the first time all sixteen pass; volume at 1200 DPI on the simulated roots and surface area at threshold 191 on the wires were the two that failed before the length method changed.

### Simulated roots — RMSE against the model's geometry, lower is better, **bold is the best of the row**

<!-- validation:start - generated by apps/worker/validation/compare.py, do not edit by hand -->
| Metric | DPI | **Sabugo** | RVE | WinRhizo | IJ_Rhizo |
|---|---|---|---|---|---|
| Total root length (mm) | 800 | 131.775 | 119.457 | 168.089 | **95.564** |
| Total root length (mm) | 1200 | 94.062 | 74.860 | 137.721 | **58.180** |
| Average diameter (mm) | 800 | 0.020 | **0.019** | 0.025 | 0.024 |
| Average diameter (mm) | 1200 | 0.010 | 0.013 | **0.008** | 0.018 |
| Surface area (mm²) | 800 | 46.221 | **38.705** | 81.271 | 40.254 |
| Surface area (mm²) | 1200 | 20.096 | **14.963** | 55.600 | 42.402 |
| Volume (mm³) | 800 | **3.855** | 4.377 | 5.528 | 5.250 |
| Volume (mm³) | 1200 | 4.153 | 4.966 | 3.566 | **3.315** |
<!-- validation:end -->

Of the 100 systems the comparison runs on 98 at 1200 DPI and 95 at 800: one of the tools reports `NA` on the rest, and the set is always the one all four measured.

#### The 800 DPI binarization, and why the threshold is 144

The metric that **does not pass through the skeleton** is what exposed this. `network_area` comes out of threshold, crop and contour and nothing else, and at 800 DPI it was 8.7% fatter than the same renderings measured by the other tools, while at 1200 DPI it agreed exactly. Sweeping `gray < t` over the 95 systems:

| `t` | median deviation | worst case | sd | identical masks |
|---|---|---|---|---|
| 143 | −0.099% | 0.85% | 0.12 | 0/95 |
| **144** | **−0.000%** | **0.04%** | **0.00** | **94/95** |
| 145 | +0.100% | 0.47% | 0.06 | 1/95 |
| 200 (the default) | +8.78% | 19.09% | 2.24 | 0/95 |

**`t = 144` reproduces the published run's mask pixel for pixel on 94 of the 95 systems.** A fitted constant does not go pixel-exact on 94 independent images: this is the value the published run used, recovered from the data, and the paper's R script never recorded it.

**The truth agrees, independently of any tool.** The ink integral — `Σ(255−gray)/255`, no threshold at all — against the model's `Σ L·d`:

| | ink (no threshold) | mask at 144 | mask at 200 |
|---|---|---|---|
| 1200 DPI | −8.5% | −8.6% | −8.6% |
| 800 DPI | **−27.6%** | −26.4% | **−20.0%** |

At 1200 DPI the mask touches the ink ceiling at any threshold. At 800 the renderings hold **19 points less root** than the 1200 ones of the same systems, before any binarization — and threshold 200 collects **7.6 points more area than there is ink in the image**. That was halo, not recovered root; 144 sits 1.2 points above the ink, which is the normal rounding of a binary mask against a soft edge.

So 144 is right on its own terms, and it also makes the comparison fair: until it was found, the four tools were being compared under different binarizations at 800 DPI and the difference was being read as an algorithm divergence. The value lives in `THRESHOLD` in `compare.py`; the pipeline default stays 200.

At 1200 DPI the sweep is inert — the renderings are effectively binary (223 mid-grey pixels in 761 million) and `gray < 144` and `gray < 200` give **bit-identical masks on all 100**.

#### What is left at 1200 DPI

Three hypotheses were measured and discarded along the way, recorded so nobody redoes them:

| Hypothesis | Measurement | Verdict |
|---|---|---|
| roots too thin to resolve (dt ≤ 1 px) | correlation **−0.02** with the error | discarded |
| the crossing pixel counted twice by the topology | worth **0.06 to 0.12%** of the volume | discarded — and confirms that not implementing the dedup is harmless |
| skeletonization shortens the ends | measured on exact truth below: the end term is never negative | discarded |

What remains is **2D occlusion**, and it is the one candidate that explains the signs of two different errors at once. Roots that cross become a single blob: the distance transform reports a fat radius there, and the skeleton runs through the blob once instead of twice. So volume comes out **too high** and length comes out **too short**, which is exactly the pattern. The volume error correlates **+0.78** with the ground truth's `overlap` column, and it is not a translation defect — the other tools carry the same bias (Sabugo +8.8% against RVE's +11.9% at 1200 DPI). It is measured directly, on exact truth, [further down](#two-roots-that-cross).

Volume is the metric Sabugo now measures best of the four, and both resolutions improved when the length method changed: at 800 DPI the volume bias is **−1.5%** and at 1200 DPI **+8.8%**.

> **Two reading choices that change who the competitors are**, both following the paper's own R script: the sheet is `all_analyses_fixed` and not the `all_analyses_automatic` beside it (with the wrong one, IJ_Rhizo goes from best to worst on length — RMSE 58 becomes 710); and WinRhizo reports cm and cm³, with the three conversion factors that script applies. The Kimura length is already in mm and takes no conversion.

> **Surface and volume ground truth is derived, and that has to be said.** The Zenodo table carries length and diameter of primary and lateral roots separately, not area and volume. Here both come from treating each root as a cylinder, from those same lengths and diameters. The paper's script uses a table of its own (`Inputs/all_D.Rdata`, columns `Sum_length, diam, sufa, vol`) that **is referenced but was not distributed** in the Zenodo archive. Length and average diameter depend on no derivation; area and volume do, and every tool's column is compared against exactly the same derivation, so the comparison between tools stays fair even if the absolute RMSE shifts.

### Copper wires — physical ground truth, 27 scans, 600 DPI

<!-- wires:start - generated by apps/worker/validation/wires.py, do not edit by hand -->
| Metric | Threshold | **Sabugo** | RVE | WinRhizo | IJ_Rhizo |
|---|---|---|---|---|---|
| Total root length (mm) | 191 | 71.441 | **45.630** | 66.668 | 107.396 |
| Total root length (mm) | 222 | **24.948** | 44.072 | 25.264 | 107.396 |
| Average diameter (mm) | 191 | **0.042** | 0.046 | 0.050 | 0.064 |
| Average diameter (mm) | 222 | 0.069 | 0.072 | 0.103 | **0.064** |
| Surface area (mm²) | 191 | 79.018 | 142.080 | 99.836 | **39.692** |
| Surface area (mm²) | 222 | 219.511 | 290.314 | 344.773 | **39.692** |
| Volume (mm³) | 191 | **24.405** | 39.648 | 284.545 | 279.950 |
| Volume (mm³) | 222 | **64.649** | 84.051 | 233.164 | 279.950 |
<!-- wires:end -->

Against a physical dimension — a micrometer for the diameter, string and a ruler for the length — Sabugo takes **three of the eight cells** and all eight pass the criterion. Volume is the clearest: 24.4 and 64.6 against the next tool's 39.6 and 84.1.

IJ_Rhizo wins surface area at both thresholds, and the reason has to be stated: it computes `π·d·l` from a mean diameter, and **a copper wire is exactly a cylinder**. Its model coincides with the object; on a real root system it does not, which is why it places third on surface area on the simulated roots.

This is also the set where the paper itself varies the threshold, which is why both thresholds stay. The 800 DPI section had just shown that a wrong threshold disguises itself as a volume error; here the effect is measured on purpose, across four tools at once. The table readings — the `LMY` (measured) column and not the nominal one beside it, WinRhizo's three conversions, and the exclusion of the twelve-wire scan — are the paper's R script's, and each has a test in `tests/test_wire_tables.py`.

#### What the wires found, and no other set would have

**First: run the published settings, not ours.** `RVE_metadata.csv` ships beside the images and records the published run — pruning **on** at 5 px, background noise filter at 8 mm². Running the defaults put **196 root tips on a single wire against the published 2**, and the comparison was reading spur suppression as a length error. Same methodological error as the 800 DPI threshold: comparing tools under different settings and calling the difference an algorithm divergence.

**Second, and this is the finding: the diameter error has two separable parts, and only one is the threshold.** Sweeping the threshold against the physical projected area — which passes through no skeleton:

| threshold | projected area vs truth | implied diameter bias |
|---|---|---|
| 170 | −5.6% | −0.018 mm |
| 180 | −1.2% | −0.006 mm |
| **≈182** | **0** | **0** |
| 191 (published) | +4.0% | +0.006 mm |
| 222 (published) | +23.8% | +0.052 mm |

Binarization at 191 explains **+0.006 mm** of diameter. The `average_diameter` we report is **+0.028 mm** off on average. That leaves **+0.022 mm**, which at 600 DPI is **+0.52 px of diameter** — and at 222 the same arithmetic leaves +0.26 px. A part that does not move with the threshold is not binarization.

**But it is not a constant either.** Wire by wire, over the twelve single-gauge scans, the error in pixels depends on the thickness:

| gauge | true width | diameter error |
|---|---|---|
| G_10 | 61 px | **−0.89 / −1.06 px** |
| G_16 | 30 px | −0.43 / −0.31 px |
| G_22 | 15 px | +0.53 / +0.44 px |
| G_28 | 7.3 px | +0.28 / +0.32 px |
| G_32 | 4.5 px | +0.39 / +0.43 px |
| G_40 | 1.65 px | **+0.64 / +0.45 px** |

Mean +0.07 px, sd 0.56 px. A thin wire reads **half a pixel too wide**, a thick one up to **a pixel too narrow**, and the crossing sits around 20 px of width. The `+0.59 px` above is the mean of a set dominated by thin wires, not a constant of the method — and that is why the half pixel of `cv2.distanceTransform` (which measures pixel-centre to pixel-centre, so inscribed radius **plus** half a pixel) explains the thin end of the table and not the thick one.

> **A fixed −0.25 px correction on the radius was tried and rejected.** It fits the mean of a set and misses the structure: it would help thin roots and hurt thick ones, which is exactly the pattern observed. The next section measured what that structure actually is — **not a width-dependent bias of the shaft, but the two ends diluting a mean** — which rules the offset out rather than deferring it.

#### What the wires **cannot** answer, and why nobody should try again

The end shortening once blamed for the length deficit **is not measurable on this set**. Per-scan length error has a spread of 6.3%, and all four tools err **in the same direction on each scan**:

| correlation of per-scan length error | |
|---|---|
| Sabugo × RVE | **+0.9998** (the difference between the two has a spread of 0.12%) |
| Sabugo × WinRhizo | +0.972 |
| Sabugo × IJ_Rhizo | +0.961 |

When all four disagree with the truth the same way, the scatter is in the truth and not in the tools: the wire length was measured with **string and a ruler** (it says so in `copper_wire_ground_truth_method.txt`), and ±6% is what that is worth. The diameter, measured with a **micrometer**, is precise — which is why the finding above is about diameter and not about length.

Separating end shortening from the digitization surplus needs a target whose truth is exact rather than measured. That is the next section, and it settled both: there is no end shortening, and the digitization surplus was +8.4%.

### Synthetic shapes — truth by construction

The wires answer *how close are we to a physical object*. They cannot answer *which part of the error is which*, because their length truth is string and a ruler. A rendered shape has no such limit.

Stamp a disc of radius `r` along a curve `C`. The shape is every point within `r` of `C`, and while `r` stays under the curve's radius of curvature the medial axis of that shape **is** `C`. So `total_root_length` is an arc length, `average_diameter` is `2r`, and surface and volume follow from the same cylinder model every tool integrates — none of it measured. `validation/synthetic.py` sweeps width, length, angle and curvature, with pruning off and on, and needs no download.

`average_diameter` is a mean over every skeleton pixel, and the pixels near the two ends carry a smaller radius than the shaft, so a short thick shape reads narrower than a long one. Regressing the error on `1/L` splits the two: the intercept is what the shaft alone reads, and the difference from the 400 px column is what the ends cost. Numbers in pixels, pruning on at 5 px:

<!-- synthetic:start - generated by apps/worker/validation/synthetic.py, do not edit by hand -->
| True diameter (px) | Shaft diameter error (px) | At 400 px long (px) | Length error at the ends (px) |
|---|---|---|---|
| 1.5 | +0.50 | +0.50 | +1.24 |
| 3 | +1.00 | +0.99 | +1.00 |
| 4.5 | +1.50 | +1.49 | -1.00 |
| 7 | +1.00 | +0.93 | +6.43 |
| 15 | +1.00 | +0.99 | +0.00 |
| 30 | -0.00 | -0.00 | +0.83 |
| 60 | -0.11 | -1.55 | +31.00 |
<!-- synthetic:end -->

**The shaft error is a rounding step, not a width trend.** It stays in `[0, +1.5]` px from 1.5 px wide to 60, never goes negative, and has no slope. The mechanism is exact: the distance transform counts whole pixels out from the axis, so a band `n` px wide reports `n` rounded up to even — 15 px reads 16, 30 px reads 30. That is a quantization of at most one pixel with no sign preference, and it is locked as a test.

**So the −0.25 px radius correction was wrong in shape and in sign.** It was fitted to a per-gauge table that ran from −0.89 px at 61 px wide to +0.64 px at 1.65 px, and read as a width-dependent bias of the measurement. It is not. The shaft has no such trend; what the wire table was showing is the last column above — at 60 px wide and a few hundred long, the ends pull the reported mean diameter down by 1.5 px, and they dilute as the object gets longer. A constant offset cannot represent a dilution, and subtracting one would make the shaft wrong in order to fix the ends.

**And skeletonization does not shorten the ends.** The standard explanation attributes the length deficit to lost tips. On a target whose length is known exactly the end term is never negative at any width — it is zero or positive, and strongly positive for thick shapes, where the digital cap sprouts branches that pruning at 5 px cannot reach (+31 px on a 60 px wide shape). That was the first of the three candidates to fall, and the ink integral above took the other two.

#### Whole root — the fan

Both ground-truth datasets run **broken roots**: the copper wires are loose segments and the simulated systems are measured that way. Depth, width, solidity, the holes and the root angles had unit shapes and nothing else — and the angles are exactly what the published paper gets wrong, so it was the half of the pipeline with the least evidence behind the most known danger.

A fan closes it. Stamp the same disc along `2n` segments leaving one point, `n` angles taken to the left and to the right, and every whole-root truth falls out in one line: the orientation is the mean of the angles, the frequencies are how they split across the bins, the depth is `L·sin(max) + 2r` and the width is `2(L·cos(min) + r)`. Three fans, one landing entirely in the shallow bin, one spread across all three, one entirely steep:

<!-- crowns:start - generated by apps/worker/validation/synthetic.py, do not edit by hand -->
| Fan, from the horizontal | Orientation | Shallow / medium / steep | Depth | Width |
|---|---|---|---|---|
| 10/20/25° | 18.3° → 18.9° | 1.00/0.00/0.00 → 0.96/0.04/0.01 | +0.2 px | +0.1 px |
| 15/45/75° | 45.0° → 44.5° | 0.33/0.33/0.33 → 0.34/0.33/0.33 | +0.2 px | +0.4 px |
| 70/80/85° | 78.3° → 76.8° | 0.00/0.00/1.00 → 0.01/0.03/0.96 | +0.1 px | +0.8 px |
<!-- crowns:end -->

**The angle axis is now constructed rather than inferred.** It reads within 1.5° of six roots at once on all three fans. The other convention would put the first fan at 71.7° and the third at 11.7°, which is not a tolerance question. The bounding box is exact to under a pixel.

**And the fixture found a bias in the frequencies on its first run.** They were fractions of skeleton **pixels**, and a digital line of euclidean length `L` holds `L·max(|cos α|, |sin α|)` of them — so a root at 45° carries **29% fewer pixels** than an axis-aligned one of the same length and was under-counted by that much. The middle fan showed it exactly: three equal thirds of root length reported as `0.371 / 0.267 / 0.361`, against a pixel-weighted prediction of `0.366 / 0.268 / 0.366`.

Each angle now carries the step it opens, simplified the same way the length is — the weighting `aggregate` already applies to all four histograms. The same fan reads `0.34 / 0.33 / 0.33`, and `average_root_orientation` is a weighted mean for the same reason. Both the fixed behaviour and the mechanism that was wrong are tests, so it cannot come back quietly.

What is left is the **hub**: the `0.96` where the truth is `1.00`, and the 1.5° on the steep fan. Where six roots meet, the ±20 px chord the angle is read over spans two of them, and the angle it returns belongs to neither. That is inherent to measuring an angle at a junction rather than a defect of the walk, and it is bounded — on a real crown the junctions are a small share of the skeleton, and this fan is nearly the worst case for it.

#### The same bias, in the other average

The fan settled the angle frequencies. The mean diameter had it too, and for the same reason: `average_diameter` and `median_diameter` were means over skeleton **pixels**, so an axis-aligned root counted up to 41% more heavily than a diagonal one of the same length.

Two roots of equal true length, one horizontal at 20 px wide and one at 45° at 8 px, put the truth at 14.0 px. Counting pixels reads **15.0**; the pipeline read 15.1, the 0.1 being the end caps. Weighted by the step each pixel opens — the same weight the four histograms use — it reads **14.2**.

Unlike the angle fix, this one moves the tables, so it was run against both datasets before being kept:

| | RMSE before → after | Bias before → after |
|---|---|---|
| Wires, threshold 191 | 0.047 → **0.042** | +0.031 → **+0.028** |
| Wires, threshold 222 | 0.074 → **0.069** | +0.066 → **+0.063** |
| Simulated, 1200 DPI | 0.012 → **0.010** | +0.009 → **+0.007** |
| Simulated, 800 DPI | 0.019 → 0.020 | −0.006 → −0.008 |

The correction pulls the diameter **down** everywhere, which is what a bias that over-weights the thick axis-aligned primaries predicts. Three of the four improve, including both copper wire thresholds, where the truth is a micrometer. The one that gets worse is 800 DPI, where the reading was already **under** the truth — the same renderings that hold 19 points less ink than the 1200 DPI ones of the same systems.

Mean rank over the sixteen cells goes **2.06 → 2.00**, the diameter column **2.00 → 1.75**, and all sixteen still pass the criterion on RMSE and on bias. Nothing else moved: length, surface area and volume were already weighted by length.

#### Two roots that cross

The correlation with the `overlap` column says occlusion is *involved*. It does not say how much, and no dataset with real roots can: nothing there is a controlled crossing. Two straight capsules of the same radius crossing at a known angle are, and both truths stay exact — the length is the sum of the two, and the volume is the two cylinders minus the solid they share, `16r³/(3·sin θ)`.

Against the truth of two roots that do **not** touch, pruning on, pooled over the three widths:

<!-- crossings:start - generated by apps/worker/validation/synthetic.py, do not edit by hand -->
| Crossing angle | Length | Volume | Branch points |
|---|---|---|---|
| 15° | -5.94% | +36.29% | 2.0 |
| 30° | -1.66% | +17.90% | 2.0 |
| 45° | +0.06% | +10.39% | 2.0 |
| 60° | +1.22% | +7.56% | 2.3 |
| 90° | +0.91% | +25.39% | 2.0 |
<!-- crossings:end -->

**Volume is over at every angle, by 7.6% to 36% of a single crossing.** That settles the sign and the order of magnitude, and it is the same direction the simulated roots show. The +25% at 90° is not a break in the trend: a perpendicular crossing has the *smallest* shared solid to subtract, and the largest blob for the distance transform to read a radius in — the two effects pull opposite ways and the curve is not monotone.

**Length is a shallow-angle effect and nothing else.** At 15° the two capsules run close to parallel and merge along a stretch, and 5.9% of the pair goes missing. By 45° it is gone: the skeleton crosses in one pixel, there is nothing to lose, and the number turns slightly positive like any other straight line. So occlusion is a full explanation for the volume bias and a **partial** one for the length deficit — it accounts for what happens where laterals leave their parent at a narrow angle, which on a real root system is most of the crossings, and for nothing else.

Both signs are locked as tests, so a change that quietly stops merging blobs, or starts merging more of them, fails the suite.

### The length method, and what changing it cost

A digital line that is neither axis-aligned nor diagonal is a staircase. Measuring it by walking every pixel step — the chain code, `1` for an orthogonal step and `√2` for a diagonal one — charges for the staircase instead of the line it stands for. Running Douglas–Peucker over the polyline first, at ε = 0.71, collapses it:

<!-- angles:start - generated by apps/worker/validation/synthetic.py, do not edit by hand -->
| Angle | `total_root_length` | Chain code, replaced |
|---|---|---|
| 0° | +0.00% | +0.00% |
| 15° | +0.22% | +6.92% |
| 22.5° | +0.46% | +8.42% |
| 30° | -0.36% | +6.79% |
| 45° | +0.37% | +0.40% |
<!-- angles:end -->

Both columns come off the same skeleton, on shapes whose length is exact. The surplus is a percentage of the length, peaks near 22.5°, and vanishes at 0° and 45° where there is no staircase. **On a straight line it was +8.4%, an order of magnitude above either pixel-sized effect in the table before it** — and the left column is what the pipeline reports now.

#### What ε is worth, and where the sweep stops answering

ε = 0.71 was inherited rather than fitted, and it is now the constant the main metric runs through, so it gets the same treatment the 800 DPI threshold got. Same skeleton every time, only the simplification varying; the straight-line column is the fitted slope, so the end term is out of it, and the arc column is not fitted — arcs vary their curvature too — but the end term is the same for every row, so the comparison between rows holds.

<!-- epsilon:start - generated by apps/worker/validation/synthetic.py, do not edit by hand -->
| Epsilon | Mean \|surplus\| on straight lines | Worst angle | On arcs |
|---|---|---|---|
| 0 | 4.50% | 22.5° (+8.42%) | +7.60% |
| 0.25 | 4.50% | 22.5° (+8.42%) | +7.60% |
| 0.5 | 1.39% | 22.5° (+3.57%) | +4.48% |
| **0.71** | 0.28% | 22.5° (+0.46%) | +2.60% |
| 1 | 0.28% | 30° (-0.50%) | +2.11% |
| 1.5 | 0.28% | 30° (-0.50%) | +1.33% |
| 2 | 0.28% | 30° (-0.48%) | +1.15% |
| 3 | 0.27% | 30° (-0.44%) | +0.88% |

<!-- epsilon:end -->

Two readings, and the second is the honest one.

**0.71 is the point where straight lines stop improving.** Below it the surplus is barely touched — under half a step, Douglas–Peucker keeps every staircase corner — and 0.5 still leaves 3.6% at the worst angle. At 0.71 the whole angular sweep is inside half a percent, and nothing above it does better. That the value is roughly `1/√2`, the offset one staircase step makes against its own line, is why the floor sits there.

**But arcs keep improving past it, and the sweep never found where that stops.** Going from 0.71 to 3 takes the arc surplus from +2.60% to +0.88% at no cost on straight lines. The arcs were tightened to curvature radius 15 px specifically to catch over-simplification flattening real curvature, and it did not appear. So the sweep does **not** establish 0.71 as optimal — it establishes that it is on the floor for straight lines and that the tested alternatives above it are better on curves.

Two things this fixture cannot see explain why. Its arcs are smooth and a real root is not, so nothing here penalises flattening the tortuosity a real root carries between its crossings. And `simplified_length()` is also what pruning measures a spur with, so raising ε moves the tip and branch counts in the same breath as the length.

**So it was run against ground truth, at ε = 1.5, and 1.5 lost.** Both datasets, both settings each:

| ε = 0.71 → 1.5 | Length | Surface area | Volume |
|---|---|---|---|
| Simulated, 800 DPI | 131.8 → **140.4** | 46.2 → **51.1** | 3.86 → 3.59 |
| Simulated, 1200 DPI | 94.1 → **100.9** | 20.1 → **23.7** | 4.15 → 3.86 |
| Wires, threshold 191 | 71.4 → **79.3** | 79.0 → 59.4 | 24.4 → 20.2 |
| Wires, threshold 222 | 24.9 → **31.8** | 219.5 → 195.4 | 64.6 → 53.7 |

Mean rank over the sixteen cells goes **2.06 → 2.12** and cells won **5 → 4**; average diameter does not move at all, and volume improves in RMSE without changing rank, because it was already the best of the four. Every cell that got worse is a length or a length-derived area.

The reason is the one the smooth arcs could not show. On a real skeleton more simplification removes more length, and length is the metric Sabugo already reads **short** — at 1200 DPI the bias goes from −8.6% to −9.5%. So ε = 1.5 spends the weakest column to improve the strongest one. **0.71 stays, and this is why, rather than because it was inherited.** All sixteen cells still pass the acceptance criterion at 1.5, so this was a choice between two acceptable values and not a rescue.

The simplification is applied **per step, not to the total**. Douglas–Peucker measures a polyline whole and knows nothing about diameter classes, so each step is scaled by the ratio its own simplified span lost, and keeps the radius of the pixel it leaves. Summing the scaled steps returns the simplified length exactly, which is what keeps `total_root_length` equal to the sum of its own histogram — and what puts surface area and volume on the same ruler as length instead of leaving them with an 8% surplus.

**What it cost, stated plainly.** The change moved every cell that integrates a length. On the simulated roots at 1200 DPI:

| | RMSE before | RMSE after | Bias before | Bias after |
|---|---|---|---|---|
| Total root length (mm) | 71.75 | **94.06** | −26.76 | **−43.49** |
| Surface area (mm²) | 14.87 | **20.10** | +0.38 | **−10.02** |
| Volume (mm³) | 5.08 | **4.15** | +2.15 | **+1.53** |
| Average diameter (mm) | 0.012 | 0.012 | +0.009 | +0.009 |

Length and surface area got **worse** against the simulated roots; volume got better and crossed into the acceptance band. On the wires the same change took volume from 40.4 to 24.4 at threshold 191 and surface area from 144.4 to 79.0, while length at 191 went from 45.6 to 71.4.

**The estimator did not get worse — a second error stopped being hidden.** Against exact truth the chain code overshoots by up to +8.4% and the simplified length by under half a percent; there is no ambiguity about which of the two measures a length. What the simulated roots show is that Sabugo was already reading **short** on real skeletons, and the staircase surplus was cancelling part of it. Removing the surplus leaves the deficit alone and visible: the length bias at 1200 DPI moves from −5.3% to **−8.6%**.

That deficit turned out not to be ours. See below.

#### The length deficit is the dataset's

The metric that passes through no threshold and no skeleton settles it, the same way it settled the 800 DPI binarization. The ink integral `Σ(255−gray)/255` is the projected root area the rendering actually contains; the model publishes its own `Σ L·d`, which is the same quantity. They do not agree.

| 1200 DPI, 100 systems | |
|---|---|
| Ink in the image vs the model's own `L·d` | **−8.48%** |
| Length we measure vs the model's length | −6.31% |
| Correlation between the two, system by system | **+0.852** |
| Slope | 0.91 |
| Our length error with the ink deficit removed | **+2.17%** |

At 800 DPI the correlation is stronger still, **+0.966**, with the ink at −27.6% and the length at −17.1%.

**The renderings hold less root than the CSV shipped beside them says**, and our deficit tracks that system by system at nearly one to one. Net of it we read slightly **long**. That closes the question the length column had left open, and it explains what nothing else did: why the synthetic shapes show no deficit at all — we render those ourselves, so the ink matches by construction — and why all four tools carry the same bias, having all read the same images.

Two candidates died on the way, both recorded so nobody redoes them:

| Candidate | Measurement | Verdict |
|---|---|---|
| thin laterals lost before skeletonization | with pruning off we find **49 tips against the 29** the model declares | discarded — we find too many, not too few |
| occlusion at crossings | alone it correlates −0.325, but its coefficient **flips sign** once lateral count and total length are in the fit | discarded as the driver; it is real geometry, measured on the crossing fixture, but it is not what makes this number |

The slope is the honest caveat. Ink measures area, `L·d`, and length is `L`, so equating the two relative errors assumes the diameter was drawn as declared. The 0.91 at 1200 DPI fits **root missing outright**, which loses area and length together; the 0.66 at 800 DPI says roots are also being drawn thinner there. Which mechanism inside the dataset removes the ink — sub-pixel laterals lost to antialiasing, a crop, or a mismatch between the table and the images — is not tested here.

**None of it changes the comparison between tools.** All four read the same renderings, so the ranking stands; what changes is the reading of the absolute bias.

`validation/ink.py` reproduces the table, `DPI=800` for the other resolution. It is a one-off rather than part of the sweep, so unlike every other number in this file these are transcribed by hand.

Two consequences worth being explicit about. The pipeline **no longer emits `simplified_root_length`**: after the change it would be bit-for-bit `total_root_length`. And the chain code is kept in `stepwise_length()` for one purpose only — producing the right-hand column above.

## The export contract

One `features.csv` row per image, or per region of interest when `--roipath` is given. Names follow the convention the other tools emit, so a Sabugo sheet lines up with theirs column by column: dots for spaces, the unit as a suffix, and **the diameter classes are numbered, not named** — the header says nothing about which boundaries produced it, so two sheets with different ranges are indistinguishable by their columns alone.

```
File.Name,Region.of.Interest,Number.of.Root.Tips,…,Computation.Time.s,
Root.Length.Diameter.Range.1.mm,…,Volume.Diameter.Range.3.mm3
```

**Column counts.** Broken roots: 26 = 2 leading (`File.Name`, `Region.of.Interest`) + 12 global + 4 histograms × 3 classes. Whole root: 38 = 2 leading + 24 global + 4 histograms × 3 classes. In general that is `12 + 4·(n+1)` and `24 + 4·(n+1)`, for `n` inner diameter boundaries. Whole root has 24 globals, not 26 — it drops `Number.of.Branch.Points` and `Branching.frequency.per.mm`, which appear only in the broken-roots row. Both headers are asserted literally in `tests/test_export.py`.

**Four identities hold across the row**, and they make the column order verifiable by anyone from any single output:

| Check |
|---|
| Branching frequency = branch points / total root length |
| Width-to-depth ratio = maximum width / depth |
| Solidity = network area / convex area |
| The three angle frequencies sum to 1 |
| Each of the four totals equals the sum of its own diameter bins |

The last one is not free: it is what the per-step simplification above exists to preserve, and `tests/test_aggregate.py` fails without it.

## Traps

Two that already cost time here and are not guessable from the code:

- **`cv2.distanceTransform` straight after the bbox crop.** The crop guarantees the mask touches all four borders, so those pixels have no background to measure against and a solid band comes back as ~3.7e18. Pad 1 px, transform, unpad. Silent on real roots, fatal on a rectangle fixture, and the DT feeds the skeleton.
- **`cv2.distanceTransform` with `DIST_MASK_PRECISE` is not reproducible** (OpenCV 5.0.0). The same input returns one of two arrays, differing by one ULP on a few hundred pixels; it tracks the allocation, not the thread count, so `setNumThreads` does not help. Harmless for the metrics, fatal for ridge detection, which compares distances for equality — it flipped 20 ridge pixels and 6 fragments on one fixture. Every exact euclidean distance is the root of an integer, so `sqrt(rint(d²))` snaps it back: `snap_to_exact` in `src/sabugo_worker/pipeline.py`.
