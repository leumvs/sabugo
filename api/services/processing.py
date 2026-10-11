import asyncio
import base64
import io
import logging
import multiprocessing
import os
import time
from typing import TYPE_CHECKING

from errors import ApiError, ERROR_STATUS, envelope
from services.jobs import Emit, Job, Payload

if TYPE_CHECKING:
    from collections.abc import Callable
    from multiprocessing.connection import Connection

    import numpy as np

    from settings import Settings


def png_data_uri(image: "np.ndarray") -> str:
    import cv2
    from imaging.pipeline import PipelineError

    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise PipelineError("INTERNAL_ERROR")
    return "data:image/png;base64," + base64.b64encode(encoded).decode("ascii")


def analyse_upload(job: Job, max_megapixels: float,
                   emit: "Callable[[Payload], None] | None" = None) -> tuple[Payload, str]:
    from imaging import export, jsonout, render
    from imaging.analysis import analyse, regions
    from imaging.pipeline import Params, load_image, segment_mask
    from imaging.progress import Progress

    options = job.params
    params = Params.from_options(options, job.rois)
    image = load_image(str(job.image_path), int(max_megapixels * 1_000_000))
    progress = Progress(emit, max(len(params.rois), 1))
    progress.stage("load")
    output = io.StringIO(newline="")
    table = None if job.preview else export.writer(output, params.diameter_ranges_mm, params.mode)
    results = []
    for index, (name, region) in enumerate(regions(image, params)):
        if job.preview:
            seg = segment_mask(region, job.dpi, params)
            progress.stage("segment", name)
            values, skeleton = None, None
        else:
            values, seg, skeleton = analyse(region, job.dpi, params, progress, name)
        pictures = {"segmented": png_data_uri(render.segmented(seg.mask)), "skeleton": None}
        if skeleton is not None:
            pictures["skeleton"] = png_data_uri(render.skeleton_picture(
                seg.mask, seg.dt, skeleton, seg.mm_per_px, params.diameter_ranges_mm,
                pen=options["medial_axis_width"], holes=options["show_holes"],
                hull=options["show_convex_hull"], contour=options["show_contours"],
                contour_width=options["contour_width"], show_distance_map=options["show_dist_map"],
                medial_axis=options["show_medial_axis"], colour_by_class=options["show_medial_axis_diameter"],
            ))
        progress.stage("render", name)
        roi_index = -1 if not params.rois else index
        if values is None:
            entry = jsonout.preview(job.filename, name, roi_index, seg.threshold_value_used, pictures)
        else:
            table.writerow(export.row(job.filename, values, params.diameter_ranges_mm, name, params.mode))
            entry = jsonout.result(job.filename, name, roi_index, values, seg.threshold_value_used, pictures, params.mode)
        results.append(entry)
        progress.unit_done()
    return jsonout.document(results), output.getvalue()


def _process(connection: "Connection", job: Job, max_megapixels: float) -> None:
    # OpenCV reads this once at import. Keep imaging imports inside the child
    # entrypoint so its decoder can reject oversized headers before allocation.
    os.environ["OPENCV_IO_MAX_IMAGE_PIXELS"] = str(int(max_megapixels * 1_000_000))
    from imaging.pipeline import PipelineError

    try:
        result = analyse_upload(job, max_megapixels, lambda data: connection.send(("progress", data)))
        connection.send(("completed", result))
    except PipelineError as error:
        code = str(error)
        connection.send(("failed", envelope(code, error.details) if code in ERROR_STATUS else envelope("INTERNAL_ERROR")))
    except Exception:
        logging.exception("analysis_failed")
        connection.send(("failed", envelope("INTERNAL_ERROR")))
    finally:
        connection.close()


async def run_analysis(job: Job, emit: Emit, settings: "Settings") -> tuple[Payload, str]:
    context = multiprocessing.get_context("spawn")
    incoming, outgoing = context.Pipe(duplex=False)
    process = context.Process(target=_process, args=(outgoing, job, settings.MAX_MEGAPIXELS))
    deadline = time.monotonic() + settings.JOB_TIMEOUT_SECONDS
    try:
        process.start()
        outgoing.close()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ApiError("PROCESSING_TIMEOUT")
            if await asyncio.to_thread(incoming.poll, min(remaining, 0.1)):
                try:
                    event, data = await asyncio.wait_for(
                        asyncio.to_thread(incoming.recv), max(deadline - time.monotonic(), 0.001)
                    )
                except EOFError:
                    raise ApiError("INTERNAL_ERROR") from None
                except TimeoutError:
                    raise ApiError("PROCESSING_TIMEOUT") from None
                if event == "completed":
                    return data
                if event == "failed":
                    raise ApiError(data["code"], data.get("details"))
                emit(event, data)
            elif not process.is_alive():
                raise ApiError("INTERNAL_ERROR")
    finally:
        if process.pid is not None:
            if process.is_alive():
                process.kill()
            await asyncio.to_thread(process.join)
        incoming.close()
        outgoing.close()
        process.close()
