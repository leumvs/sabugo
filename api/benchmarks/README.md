# API performance — 2026-10-11

All eight 20 MP scenarios improved by **21–31%**. None of the 24 measured scenarios regressed. Metrics, CSV values at six decimals and decoded PNG pixels matched the saved reference; processing time is excluded from the semantic comparison.

## Measurements

Linux x86-64, Python 3.14.8, NumPy 2.5.4, OpenCV 5.0.0, FastAPI 0.143.0 and Pydantic 2.14.0. Both runs used two CPU cores, a CPU quota of 200%, 4 GiB memory and no swap. Each scenario ran ten times in a fresh child process; the table reports median total time, including process startup, transfer and cleanup. Profiling was run separately.

The deterministic fixtures cover fragmented broken roots and crossing whole roots, at 1/5/20 MP. Each mode exercises plain analysis, preview, pruning and two ROIs. `keep_largest=False` retains all fragments for the benchmark. These fixtures cover the complete cropped image area; they are not downloaded scientific validation scans.

| 20 MP scenario | Before | After | Improvement | Child peak before → after |
|---|---:|---:|---:|---:|
| Broken roots | 2.466 s | 1.776 s | 28.0% | 515 → 498 MiB |
| Broken roots, preview | 0.468 s | 0.347 s | 25.9% | 258 → 246 MiB |
| Broken roots, pruning | 3.582 s | 2.492 s | 30.4% | 568 → 498 MiB |
| Broken roots, two ROIs | 2.167 s | 1.709 s | 21.1% | 364 → 348 MiB |
| Whole root | 3.700 s | 2.695 s | 27.1% | 1119 → 765 MiB |
| Whole root, preview | 0.481 s | 0.354 s | 26.5% | 266 → 266 MiB |
| Whole root, pruning | 5.538 s | 3.802 s | 31.3% | 1119 → 765 MiB |
| Whole root, two ROIs | 3.405 s | 2.627 s | 22.9% | 665 → 490 MiB |

The kernel-reported budget in `after.json` is `memory.max=4294967296`, `memory.swap.max=0`, `cpu.max="200000 100000"`. The baseline used the same systemd properties. Source fingerprints identify the measured implementations; the archived baseline permits rerunning the original code even though the API migration was uncommitted.

## 50 MP and production

All eight 50 MP cases completed three times under the same budget. The largest child RSS was **1725 MiB**. Adding the parent and child high-water marks gives a conservative upper bound of **2234 MiB (2.18 GiB)**; their peaks are not necessarily simultaneous. The benchmark parent's RSS includes fixture generation and PNG decoding used for comparison. JSON fields ending in `_mb` report MiB on Linux.

The built production image also processed a 49.999 MP crossing fixture through HTTP upload, SSE, PNG results and CSV in both modes, plus preview. CSV had 26/38 columns and preview had no metrics or export. The complete container's kernel `memory.peak` was **1924030464 bytes (1.79 GiB)**, below the 3 GiB target, with the 4 GiB limit and no swap enforced. During these jobs, 163 health requests succeeded, with **p95 2.65 ms**. Temporary upload directories were removed and completion logs were present. The temporary container was stopped after verification.

These are measured fixture results, not a latency or memory guarantee for arbitrary scans or accumulated result-cache workloads. Real root density, topology, pixel depth and options affect cost. Keep the 50 MP default when using the 4 GiB Compose budget; measure the intended scans before increasing it.

## Reproduce

From `api/`, using the locked environment:

```bash
systemd-run --user --scope --quiet \
  -p MemoryMax=4G -p MemorySwapMax=0 -p CPUQuota=200% \
  "$PWD/.venv/bin/python" "$PWD/benchmark.py" \
  --output /tmp/sabugo-after.json --compare benchmarks/before.json

systemd-run --user --scope --quiet \
  -p MemoryMax=4G -p MemorySwapMax=0 -p CPUQuota=200% \
  "$PWD/.venv/bin/python" "$PWD/benchmark.py" \
  --sizes 50 --repeats 3 --output /tmp/sabugo-50mp.json

uv run python benchmark.py --sizes 20 --profile /tmp/sabugo.prof
uv run python -m pstats /tmp/sabugo.prof
```

`--cpus 2` is the default and sets affinity before importing NumPy/OpenCV. On systems without a user systemd manager, run the Python command directly for affinity-only measurements or enforce the budget with a container. Timing thresholds are not CI assertions.

To rerun the original implementation, extract `before-source.tar.gz` into a separate directory, run `uv sync --locked` in its `api/` directory, and run its `benchmark.py` with the same systemd properties. The archive includes the original runtime, benchmark, manifest, lockfile and licence. Compare performance on the same hardware and dependency versions.

Stage intervals are measured between progress messages. Import work moved from module loading into the child entrypoint, so the split between `startup_s` and the `load` interval changed; use total durations for before/after comparisons. Each scenario stores one representative numerical/CSV/pixel reference, all ten timing samples, median stages, startup, RSS and result size.

## Evidence and checks

- [before.json](before.json): original measurements and references.
- [after.json](after.json): final measurements, comparisons, versions and kernel budget.
- [50mp.json](50mp.json): eight large-image cases, three repetitions each.
- [production.json](production.json): HTTP smoke-test timings, health and whole-container peak.
- [before-source.tar.gz](before-source.tar.gz): original source snapshot.

The full suite passed **271 tests**. Five physical-wire tests remain skipped because `validation/data/` is absent. Added checks cover block seams and global skeleton connections, preview without distance calculation, concurrent admission, disconnect/cancellation and persistence failures, ROI bounds, native pre-decode limits, late SSE subscriptions, child crashes, cleanup and schema/default consistency. No dependency was added or upgraded.
