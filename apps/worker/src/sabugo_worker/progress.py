"""Stage reporting on stderr, so stdout stays free for the human report."""

from __future__ import annotations

import json
import sys


class Progress:
    """One NDJSON line on stderr per finished stage. stdout carries the human
    report, so the two streams stay separable."""

    STAGES = {
        "load": 5,
        "segment": 20,
        "skeletonize": 60,
        "prune": 65,
        "topology": 75,
        "aggregate": 85,
        "render": 95,
    }

    def __init__(self, enabled: bool = False, units: int = 1) -> None:
        self.enabled = enabled
        self.units = max(units, 1)  # image x region pairs
        self.done = 0

    def stage(self, name: str, region: str = "Full") -> None:
        if not self.enabled:
            return
        percent = (self.done + self.STAGES[name] / 100.0) / self.units * 100.0
        # Unbuffered: the API reads this line by line while the process runs.
        print(
            json.dumps({"stage": name, "percent": round(percent, 1), "region": region}),
            file=sys.stderr,
            flush=True,
        )

    def unit_done(self) -> None:
        self.done += 1
