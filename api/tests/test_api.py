import asyncio
import io
import json
import struct
from contextlib import ExitStack

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from main import create_app
from services.uploads import is_multi_page_tiff, sniff_format
from settings import Settings


async def fake_runner(job, emit):
    await asyncio.sleep(0.01)
    emit("progress", {"stage": "load", "percent": 5, "region": "Full"})
    return {"pipelineVersion": "1.3.0", "results": []}, "File.Name,Region.of.Interest\r\nscan.png,Full\r\n"


@pytest.fixture
def image():
    image = np.full((80, 260), 255, np.uint8)
    image[30:50, 30:230] = 0
    return cv2.imencode(".png", image)[1].tobytes()


@pytest.fixture
def clients(tmp_path):
    (tmp_path / "index.html").write_text('<div id="app"></div>')
    (tmp_path / "404.html").write_text('<h1>404</h1>')
    (tmp_path / "asset.js").write_text('console.log("asset")')
    with ExitStack() as stack:
        def make(real=False, runner=None, ttl=300, **settings):
            app = create_app(Settings(FASTAPI_ENV="test", **settings),
                             runner=runner if runner is not None else (None if real else fake_runner),
                             client_dist=tmp_path, result_ttl=ttl)
            return stack.enter_context(TestClient(app))
        yield make


def upload(client, image, params=None, rois=None, dpi="300", filename="scan.png", preview=False):
    fields = {"dpi": dpi, "params": json.dumps(params or {})}
    if rois is not None:
        fields["rois"] = json.dumps(rois)
    return client.post("/api/analyses" + ("?preview=1" if preview else ""),
                       data=fields, files={"image": (filename, image, "image/png")})


def read_events(client, id):
    response = client.get(f"/api/analyses/{id}/events")
    result = []
    event = None
    for line in response.text.splitlines():
        if line.startswith("event: "):
            event = line[7:]
        elif line.startswith("data: "):
            result.append((event, json.loads(line[6:])))
    return response, result


def test_health_docs_static_and_api_404(clients):
    client = clients()
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/docs").status_code == 200
    paths = client.get("/api/openapi.json").json()["paths"]
    assert set(paths) == {"/api/health", "/api/analyses", "/api/analyses/{id}/events", "/api/analyses/{id}/export"}
    assert 'id="app"' in client.get("/").text
    assert client.get("/asset.js").status_code == 200
    assert client.get("/missing", headers={"Accept": "text/html"}).status_code == 404
    assert "<h1>404</h1>" in client.get("/missing", headers={"Accept": "text/html"}).text
    for path in ("/api", "/api/missing", "/api/asset.js"):
        response = client.get(path, headers={"Accept": "text/html"})
        assert response.status_code == 404
        assert response.json() == {"code": "NOT_FOUND", "message": "not_found"}


@pytest.mark.parametrize("mode,columns", [("broken_roots", 26), ("whole_root", 38)])
def test_real_analysis_sse_csv_and_images(clients, image, mode, columns):
    client = clients(real=True)
    response = upload(client, image, {"mode": mode})
    assert response.status_code == 202
    accepted = response.json()
    assert accepted["status"] == "pending" and accepted["queuePosition"] == 0
    response, events = read_events(client, accepted["id"])
    assert response.headers["x-accel-buffering"] == "no"
    assert response.headers["content-encoding"].lower() == "identity"
    event, document = events[-1]
    assert event == "completed"
    [entry] = document["results"]
    assert document["pipelineVersion"] == "1.3.0"
    assert entry["fileName"] == "scan.png"
    assert entry["metrics"]["totalRootLength"] > 0
    assert entry["segmentedImage"].startswith("data:image/png;base64,")
    assert entry["skeletonImage"].startswith("data:image/png;base64,")
    exported = client.get(f'/api/analyses/{accepted["id"]}/export')
    assert exported.status_code == 200
    assert len(exported.text.splitlines()[0].split(",")) == columns
    assert "attachment" in exported.headers["content-disposition"]
    assert read_events(client, accepted["id"])[1] == [events[-1]]
    assert not client.app.state.jobs.listeners


def test_real_preview_with_rois_has_no_export(clients, image):
    client = clients(real=True)
    rois = [{"name": "roi, name", "x": 20, "y": 20, "width": 220, "height": 50}]
    accepted = upload(client, image, rois=rois, preview=True).json()
    _, events = read_events(client, accepted["id"])
    assert events[-1][0] == "completed"
    entry = events[-1][1]["results"][0]
    assert entry["roiIndex"] == 0 and entry["roiName"] == "roi, name"
    assert "metrics" not in entry and "bins" not in entry
    assert entry["skeletonImage"] is None
    assert all(data.get("stage") != "skeletonize" for event, data in events if event == "progress")
    assert client.get(f'/api/analyses/{accepted["id"]}/export').status_code == 404


@pytest.mark.parametrize("params", [
    {"diameter_ranges_mm": [5, 2]}, {"diameter_ranges_mm": [2, 2]},
    {"diameter_ranges_mm": [0, 2]}, {"diameter_ranges_mm": list(range(1, 13))},
    {"diameter_ranges_mm": []}, {"threshold_value": 256}, {"threshold_value": "200"},
    {"invert_image": "false"}, {"medial_axis_width": 21}, {"root_pruning_threshold": -1},
    {"max_background_noise_mm2": float("inf")},
])
def test_invalid_parameters_are_tokens(clients, image, params):
    response = upload(clients(), image, params)
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_PARAMS"
    assert " " not in response.json()["details"]["reason"]


@pytest.mark.parametrize("dpi", ["49", "4801", "nan", "inf", "nope"])
def test_dpi_limits(clients, image, dpi):
    assert upload(clients(), image, dpi=dpi).status_code == 400


def test_required_dpi_invalid_json_and_roi_limits(clients, image):
    client = clients()
    assert client.post("/api/analyses", files={"image": ("scan.png", image)}).status_code == 400
    for field in ("params", "rois"):
        response = client.post("/api/analyses", data={"dpi": "300", field: "broken"}, files={"image": ("scan.png", image)})
        assert response.status_code == 400
        assert response.json()["details"] == {"field": field, "reason": "not_json"}
    roi = {"name": "roi", "x": 0, "y": 0, "width": 10, "height": 10}
    assert upload(client, image, rois=[roi] * 11).status_code == 400
    assert upload(client, image, rois=[dict(roi, x=-1)]).status_code == 400
    assert upload(client, image, rois=[dict(roi, width=0)]).status_code == 400
    assert client.post("/api/analyses?preview=yes", data={"dpi": "300"}, files={"image": ("scan.png", image)}).status_code == 400


def test_filename_sanitization_defaults_and_field_order(clients, image):
    seen = []
    async def runner(job, emit):
        seen.append(job)
        return await fake_runner(job, emit)
    client = clients(runner=runner)
    response = client.post("/api/analyses", files=[("image", ("../../scan $04.png", image)), ("dpi", (None, "300"))])
    assert response.status_code == 202
    read_events(client, response.json()["id"])
    assert seen[0].filename == "scan__04.png"
    assert seen[0].params["threshold_value"] == 200
    assert seen[0].params["diameter_ranges_mm"] == [2, 5]


def test_magic_bytes_not_extension_or_content_type(clients):
    response = upload(clients(), b"an executable", filename="scan.png")
    assert response.status_code == 415
    assert response.json()["details"]["reason"] == "magic_bytes"


@pytest.mark.parametrize("order,header", [("<", b"II*\0"), (">", b"MM\0*")])
def test_tiff_page_detection_and_upload(clients, order, header):
    for next_ifd in (0, 20, 500):
        data = header + struct.pack(order + "IHI", 8, 0, next_ifd) + bytes(20)
        assert is_multi_page_tiff(io.BytesIO(data), len(data)) == (next_ifd == 20)
        response = upload(clients(), data)
        assert response.status_code == (415 if next_ifd == 20 else 202)
    assert sniff_format(b"II") is None
    assert sniff_format(b"\xff\xd8") is None
    assert not is_multi_page_tiff(io.BytesIO(b"II*\0"), 4)


def test_file_and_chunked_body_limits(clients, image):
    client = clients(MAX_UPLOAD_BYTES=16)
    assert upload(client, image).status_code == 413
    boundary = b"testboundary"
    payload = b"--" + boundary + b'\r\nContent-Disposition: form-data; name="image"; filename="a.png"\r\n\r\n' + bytes(1024 * 1024 + 32) + b"\r\n--" + boundary + b"--\r\n"
    response = client.post("/api/analyses", content=(payload[i:i+8192] for i in range(0, len(payload), 8192)), headers={"Content-Type": "multipart/form-data; boundary=testboundary"})
    assert response.status_code == 413
    assert response.json()["code"] == "IMAGE_TOO_LARGE"


def test_capacity_and_rate_limit_do_not_read_body(clients, image):
    def unread():
        raise AssertionError("body_read")
        yield b""
    client = clients(MAX_QUEUE_DEPTH=1)
    client.app.state.jobs.waiting.append(None)
    try:
        response = client.post("/api/analyses", content=unread(), headers={"Content-Type": "multipart/form-data; boundary=x"})
        assert response.status_code == 503
    finally:
        client.app.state.jobs.waiting.clear()
    client = clients(UPLOADS_PER_HOUR=1)
    assert upload(client, image).status_code == 202
    assert client.post("/api/analyses", content=unread()).status_code == 429
    assert upload(client, image).json()["message"] == "rate_limited"
    assert client.post("/api/analyses", data={"dpi": "300"}, files={"image": ("scan.png", image)}, headers={"X-Forwarded-For": "another, proxy"}).status_code == 429


def test_declared_body_limit_does_not_read_body(clients):
    def unread():
        raise AssertionError("body_read")
        yield b""
    response = clients(MAX_UPLOAD_BYTES=16).post("/api/analyses", content=unread(),
                                              headers={"Content-Length": str(1024 * 1024 + 17)})
    assert response.status_code == 413
    assert response.json()["code"] == "IMAGE_TOO_LARGE"


@pytest.mark.parametrize("roi", [
    {"name": "outside", "x": 260, "y": 0, "width": 1, "height": 1},
    {"name": "partial", "x": 250, "y": 0, "width": 11, "height": 10},
    {"name": "bottom", "x": 0, "y": 79, "width": 10, "height": 2},
])
def test_outside_roi_fails_after_acceptance_and_queue_recovers(clients, image, roi):
    client = clients(real=True)
    response = upload(client, image, rois=[roi])
    assert response.status_code == 202
    assert read_events(client, response.json()["id"])[1][-1] == (
        "failed", {"code": "INVALID_PARAMS", "message": "invalid_params",
                   "details": {"field": "rois", "reason": "roi_out_of_bounds", "index": 0}})
    accepted = upload(client, image).json()
    assert read_events(client, accepted["id"])[1][-1][0] == "completed"


def test_completed_sse_schema_describes_analysis_and_preview(clients):
    operation = clients().get("/api/openapi.json").json()["paths"]["/api/analyses/{id}/events"]["get"]
    schema = operation["x-sse-events"]["completed"]
    assert schema["properties"]["pipelineVersion"]["type"] == "string"
    assert set(schema["$defs"]["AnalysisResult"]["required"]) >= {"metrics", "bins", "numSegments"}
    assert "metrics" not in schema["$defs"]["PreviewResult"]["properties"]


def test_failure_unknown_job_export_and_expiry(clients, image):
    client = clients(real=True, MAX_MEGAPIXELS=0.01)
    accepted = upload(client, image).json()
    assert read_events(client, accepted["id"])[1][-1] == ("failed", {"code": "IMAGE_TOO_LARGE", "message": "image_too_large"})
    assert client.get(f'/api/analyses/{accepted["id"]}/export').status_code == 404
    assert client.get(f'/api/analyses/{accepted["id"]}/export?format=json').status_code == 400
    assert read_events(client, "unknown")[1] == [("failed", {"code": "NOT_FOUND", "message": "not_found"})]
    client = clients(ttl=0.03)
    id = upload(client, image).json()["id"]
    read_events(client, id)
    client.portal.call(asyncio.sleep, 0.06)
    assert client.get(f"/api/analyses/{id}/export").status_code == 404
    assert id not in client.app.state.jobs.jobs


def test_production_requires_build_and_environment_validation(tmp_path, monkeypatch):
    with pytest.raises(RuntimeError):
        create_app(Settings(FASTAPI_ENV="production"), client_dist=tmp_path / "missing")
    monkeypatch.setenv("PORT", "bad")
    with pytest.raises(ValueError, match="PORT"):
        Settings.from_environment()


def test_real_timeout_recovers_for_next_upload(clients, image):
    import multiprocessing
    before = {child.pid for child in multiprocessing.active_children()}
    client = clients(real=True, JOB_TIMEOUT_SECONDS=0.001)
    first = upload(client, image).json()["id"]
    assert read_events(client, first)[1][-1][1]["code"] == "PROCESSING_TIMEOUT"
    client.app.state.settings.JOB_TIMEOUT_SECONDS = 5
    second = upload(client, image).json()["id"]
    assert read_events(client, second)[1][-1][0] == "completed"
    assert {child.pid for child in multiprocessing.active_children()} == before
    async def settled():
        await client.app.state.jobs.task
    client.portal.call(settled)
    assert all(not job.image_path.parent.exists() for job in client.app.state.jobs.jobs.values())


def test_unexpected_failure_is_sanitized_and_queue_continues(clients, image):
    calls = 0
    async def runner(job, emit):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("private_path=/secret/input.png")
        return await fake_runner(job, emit)
    client = clients(runner=runner)
    first = upload(client, image).json()["id"]
    assert read_events(client, first)[1][-1] == ("failed", {"code": "INTERNAL_ERROR", "message": "internal_error"})
    second = upload(client, image).json()["id"]
    assert read_events(client, second)[1][-1][0] == "completed"
