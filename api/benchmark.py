"""Reproducible API-worker benchmark; timing and profiling run separately.

Run from api/: python benchmark.py --output /tmp/before.json
Compare: python benchmark.py --output /tmp/after.json --compare /tmp/before.json
"""

import argparse
import asyncio
import base64
import csv
import hashlib
import io
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import resource
import statistics
import tempfile
import time


def measured_process(connection, job, max_megapixels):
    """Observe the real child entrypoint without changing its result or timing."""
    from services.processing import _process

    started = time.perf_counter()
    connection.send(("benchmark_started", started))
    stages = {}
    previous = started

    class RecordingConnection:
        def send(self, message):
            nonlocal previous
            event, data = message
            now = time.perf_counter()
            if event == "progress":
                name = data["stage"]
                stages[name] = stages.get(name, 0) + now - previous
                previous = now
            elif event in ("completed", "failed"):
                connection.send(("benchmark_stats", {
                    "stages_s": stages,
                    "child_peak_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
                }))
            connection.send(message)

        def close(self):
            connection.close()

    _process(RecordingConnection(), job, max_megapixels)


def fixture(path, megapixels, pattern):
    import cv2
    import numpy as np

    side = int((megapixels * 1_000_000) ** 0.5)
    image = np.full((side, side), 255, np.uint8)
    margin = 20
    if pattern == "fragmented":
        for index, row in enumerate(np.linspace(margin, side - 170, 14).astype(int)):
            cv2.line(image, (margin, int(row)), (side - margin, int(row) + 150), 0, 5 + index % 5)
    else:
        for offset in np.linspace(margin, side - margin, 8).astype(int):
            cv2.line(image, (margin, int(offset)), (side - margin, side - int(offset)), 0, 7)
            cv2.line(image, (int(offset), margin), (side - int(offset), side - margin), 0, 9)
    cv2.imwrite(str(path), image)
    return side


def reference(document, table):
    """Compare numerical output and decoded pixels, excluding elapsed time."""
    import cv2
    import numpy as np

    entries = []
    for result in document["results"]:
        entry = dict(result)
        if "metrics" in entry:
            entry["metrics"] = {key: value for key, value in entry["metrics"].items() if key != "processingTimeMs"}
        for key in ("segmentedImage", "skeletonImage"):
            if entry[key] is not None:
                png = base64.b64decode(entry[key].split(",", 1)[1])
                pixels = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_UNCHANGED)
                entry[key] = {"shape": list(pixels.shape), "sha256": hashlib.sha256(pixels.tobytes()).hexdigest()}
        entries.append(entry)
    rows = list(csv.DictReader(io.StringIO(table)))
    for row in rows:
        row.pop("Computation.Time.s", None)
    return {"pipelineVersion": document["pipelineVersion"], "results": entries, "csv": rows}


def scenarios(sizes):
    for mp in sizes:
        for mode, pattern in (("broken_roots", "fragmented"), ("whole_root", "crossings")):
            for variant in ("plain", "preview", "pruned", "rois"):
                yield mp, mode, pattern, variant


def cgroup_limits():
    """Record the real Linux budget, not just the requested CLI options."""
    membership = Path("/proc/self/cgroup")
    if not membership.exists():
        return {}
    for line in membership.read_text().splitlines():
        if line.startswith("0::"):
            directory = Path("/sys/fs/cgroup") / line[3:].lstrip("/")
            return {name: (directory / name).read_text().strip()
                    for name in ("memory.max", "memory.swap.max", "cpu.max") if (directory / name).exists()}
    return {}


async def run(args):
    # Affinity is inherited by spawned children and respected by OpenCV.
    if hasattr(os, "sched_getaffinity"):
        os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:args.cpus])
    from schemas import AnalysisParams
    from services.jobs import Job
    import services.processing as processing
    from settings import Settings

    processing._process = measured_process
    report = {
        "python": platform.python_version(), "cpus": args.cpus, "repeats": args.repeats,
        "platform": platform.platform(), "cgroup": cgroup_limits(),
        "dependencies": {name: version(name) for name in ("numpy", "opencv-contrib-python-headless", "fastapi", "pydantic")},
        "source_sha256": hashlib.sha256(b"".join(
            path.read_bytes() for path in sorted(Path(__file__).parent.rglob("*.py"))
            if ".venv" not in path.parts and "tests" not in path.parts and "validation" not in path.parts
        )).hexdigest(),
        "scenarios": {},
    }
    with tempfile.TemporaryDirectory(prefix="sabugo-benchmark-") as directory:
        for mp, mode, pattern, variant in scenarios(args.sizes):
            name = f"{mp}mp/{mode}/{variant}"
            if args.scenario and name not in args.scenario:
                continue
            path = Path(directory) / "scan.png"
            side = fixture(path, mp, pattern)
            options = AnalysisParams(mode=mode, keep_largest=False, enable_root_pruning=variant == "pruned").model_dump()
            rois = [] if variant != "rois" else [
                {"name": f"roi-{i}", "x": 0, "y": i * (side // 2), "width": side, "height": side // 2}
                for i in range(2)
            ]
            durations, samples = [], []
            saved_reference = None
            result_size = 0
            for _ in range(args.repeats):
                job = Job(path, "scan.png", 600, options, rois, variant == "preview")
                stats = {}
                started = time.perf_counter()

                def observe(event, data):
                    if event == "benchmark_started":
                        stats["startup_s"] = data - started
                    elif event == "benchmark_stats":
                        stats.update(data)

                document, table = await processing.run_analysis(job, observe, Settings(JOB_TIMEOUT_SECONDS=600, MAX_MEGAPIXELS=mp))
                durations.append(time.perf_counter() - started)
                stats["parent_peak_mb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
                samples.append(stats)
                if saved_reference is None:
                    saved_reference = reference(document, table)
                    result_size = len(json.dumps(document, separators=(",", ":")).encode()) + len(table.encode())
                del document, table
            stages = {stage: statistics.median(sample["stages_s"].get(stage, 0) for sample in samples)
                      for stage in samples[0]["stages_s"]}
            entry = {
                "median_s": statistics.median(durations), "samples_s": durations,
                "startup_s": statistics.median(sample["startup_s"] for sample in samples),
                "child_peak_mb": max(sample["child_peak_mb"] for sample in samples),
                "parent_peak_mb": max(sample["parent_peak_mb"] for sample in samples),
                "stages_s": stages, "result_bytes": result_size, "reference": saved_reference,
            }
            report["scenarios"][name] = entry
            # Save after every case so a long run can be inspected or resumed.
            args.output.write_text(json.dumps(report, indent=2) + "\n")
            print(f"{name}: {entry['median_s']:.3f}s, child {entry['child_peak_mb']:.0f} MiB", flush=True)
    if args.compare:
        baseline = json.loads(args.compare.read_text())
        for name, entry in report["scenarios"].items():
            before = baseline["scenarios"][name]
            if before["reference"] != entry["reference"]:
                raise AssertionError(f"output_changed: {name}")
            entry["improvement_percent"] = (1 - entry["median_s"] / before["median_s"]) * 100
            print(f"{name}: {entry['improvement_percent']:+.1f}%", flush=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")


def profile(args):
    import cProfile
    from schemas import AnalysisParams
    from services.jobs import Job
    from services.processing import analyse_upload

    if hasattr(os, "sched_getaffinity"):
        os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:args.cpus])
    with tempfile.TemporaryDirectory(prefix="sabugo-profile-") as directory:
        path = Path(directory) / "scan.png"
        fixture(path, args.sizes[0], "crossings")
        job = Job(path, "scan.png", 600, AnalysisParams(mode="whole_root", keep_largest=False).model_dump(), [])
        profiler = cProfile.Profile()
        profiler.runcall(analyse_upload, job, args.sizes[0])
        profiler.dump_stats(str(args.profile))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", nargs="+", type=int, default=[1, 5, 20])
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--cpus", type=int, default=2)
    parser.add_argument("--scenario", action="append", help="Only run an exact scenario, e.g. 20mp/broken_roots/plain")
    parser.add_argument("--output", type=Path, default=Path("/tmp/sabugo-benchmark.json"))
    parser.add_argument("--compare", type=Path)
    parser.add_argument("--profile", type=Path, help="Write cProfile data instead of timing samples")
    args = parser.parse_args()
    if min(*args.sizes, args.repeats, args.cpus) <= 0:
        parser.error("sizes, repeats and cpus must be positive")
    if args.profile:
        profile(args)
    else:
        asyncio.run(run(args))
