import asyncio
import shutil
from collections.abc import AsyncIterator
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import Field, TypeAdapter
from starlette.datastructures import UploadFile

from errors import ApiError, envelope
from schemas import Accepted, AnalysisDocument, AnalysisParams, ErrorEnvelope, Roi
from services.jobs import Job, Jobs
from services.uploads import save_upload, validated
from settings import Settings

router = APIRouter(prefix="/api/analyses", tags=["analyses"])
DPI = TypeAdapter(Annotated[float, Field(ge=50, le=4800, allow_inf_nan=False)])
ROIS = TypeAdapter(Annotated[list[Roi], Field(max_length=10)])
ERROR_RESPONSES = {code: {"model": ErrorEnvelope} for code in (400, 413, 415, 429, 500, 503)}
UPLOAD_SCHEMA = {"requestBody": {"required": True, "content": {"multipart/form-data": {"schema": {
    "type": "object", "required": ["image", "dpi"], "properties": {
        "dpi": {"type": "string", "example": "600"},
        "params": {"type": "string", "description": "JSON analysis parameters"},
        "rois": {"type": "string", "description": "JSON array of up to ten rectangles"},
        "image": {"type": "string", "format": "binary"},
    },
}}}}}


@router.post("", status_code=202, responses=ERROR_RESPONSES, openapi_extra=UPLOAD_SCHEMA)
async def submit(request: Request, preview: Literal["0", "1"] | None = None) -> Accepted:
    jobs: Jobs = request.app.state.jobs
    settings: Settings = request.app.state.settings
    address = request.client.host if request.client else "unknown"
    request.app.state.allowance.check(address)
    with jobs.reserve_upload():
        directory = None
        try:
            async with request.form(max_files=1, max_fields=3, max_part_size=256 * 1024) as form:
                if "dpi" not in form:
                    raise ApiError("INVALID_PARAMS", {"field": "dpi"})
                dpi = validated(DPI.validate_python, form["dpi"], "dpi")
                params = validated(AnalysisParams.model_validate_json, form.get("params", "{}"), "params")
                rois = validated(ROIS.validate_json, form.get("rois", "[]"), "rois")
                image = form.get("image")
                if not isinstance(image, UploadFile):
                    raise ApiError("INVALID_PARAMS", {"field": "image"})
                path, filename = await save_upload(image, settings.MAX_UPLOAD_BYTES)
                directory = path.parent
                job = Job(path, filename, dpi, params.model_dump(), [r.model_dump() for r in rois], preview == "1")
            position = jobs.enqueue(job, reserved=True)
            directory = None
            return Accepted(id=job.id, queuePosition=position, queuedAt=job.queued_at)
        finally:
            if directory is not None:
                await asyncio.to_thread(shutil.rmtree, directory, True)


async def sse_headers(response: Response) -> None:
    response.headers["Content-Encoding"] = "Identity"


@router.get("/{id}/events", response_class=EventSourceResponse, dependencies=[Depends(sse_headers)],
            description=("SSE events: queued, started, progress, completed, failed. "
                         "A late subscriber receives the current state and last progress, or the terminal event. "
                         "Completed data follows x-sse-events.completed; preview results omit metrics, bins and numSegments."),
            openapi_extra={"x-sse-events": {"completed": {"$id": "urn:sabugo:analysis-document", **AnalysisDocument.model_json_schema()},
                                           "failed": {"$id": "urn:sabugo:error-envelope", **ErrorEnvelope.model_json_schema()}}})
async def events(id: str, request: Request) -> AsyncIterator[ServerSentEvent]:
    jobs: Jobs = request.app.state.jobs
    job = jobs.jobs.get(id)
    if job is None:
        yield ServerSentEvent(event="failed", data=envelope("NOT_FOUND"))
        return
    listener = jobs.subscribe(job)
    try:
        while True:
            event, data = await listener.get()
            yield ServerSentEvent(event=event, data=data)
            if event in ("completed", "failed"):
                return
    finally:
        jobs.unsubscribe(id, listener)


@router.get("/{id}/export", responses={200: {"content": {"text/csv": {"schema": {"type": "string"}}}}, 404: {"model": ErrorEnvelope}})
async def download(id: str, request: Request, format: Literal["csv"] = "csv") -> Response:
    job = request.app.state.jobs.jobs.get(id)
    if job is None or job.status != "completed" or not job.csv:
        raise ApiError("NOT_FOUND")
    return Response(job.csv, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="sabugo-{id}.csv"'})
