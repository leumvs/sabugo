"""Run validation images through the application's public routes."""

import csv
import io
import json
import os
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from main import create_app
from settings import Settings


def export_images(images, dpi, params, output):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with TestClient(create_app(Settings(FASTAPI_ENV="test"))) as client, tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", dir=output.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            wrote_header = False
            for image in sorted(images):
                with image.open("rb") as source:
                    accepted = client.post("/api/analyses", data={"dpi": str(dpi), "params": json.dumps(params)},
                                           files={"image": (image.name, source)})
                accepted.raise_for_status()
                job_id = accepted.json()["id"]
                stream = client.get(f"/api/analyses/{job_id}/events")
                event = None
                for line in stream.text.splitlines():
                    if line.startswith("event: "):
                        event = line[7:]
                    elif line.startswith("data: ") and event == "failed":
                        raise RuntimeError(f"{image.name}: {json.loads(line[6:])['code']}")
                if event != "completed":
                    raise RuntimeError(f"{image.name}: missing_terminal_event")
                response = client.get(f"/api/analyses/{job_id}/export")
                response.raise_for_status()
                table = csv.reader(io.StringIO(response.text))
                header = next(table)
                writer = csv.writer(handle)
                if not wrote_header:
                    writer.writerow(header)
                    wrote_header = True
                for row in table:
                    # Dataset joins use the original name, not the API's bounded stem.
                    row[0] = image.name
                    writer.writerow(row)
            if not wrote_header:
                raise ValueError("no_validation_images")
        os.replace(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
