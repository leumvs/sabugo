"""Upload validation and persistence. File I/O stays off the event loop."""

import asyncio
from collections.abc import Callable
from pathlib import Path
import re
import shutil
import struct
import tempfile
from typing import BinaryIO, TypeVar

from pydantic import ValidationError
from starlette.datastructures import UploadFile

from errors import ApiError

EXTENSIONS = {"bmp": "bmp", "jpeg": "jpg", "png": "png", "tiff": "tif"}
T = TypeVar("T")


def sniff_format(data: bytes) -> str | None:
    if data.startswith(b"BM"):
        return "bmp"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith((b"II*\0", b"MM\0*")):
        return "tiff"
    return None


def is_multi_page_tiff(handle: BinaryIO, size: int) -> bool:
    handle.seek(0)
    header = handle.read(8)
    if len(header) < 8 or sniff_format(header) != "tiff":
        return False
    order = "<" if header.startswith(b"II") else ">"
    first = struct.unpack(order + "I", header[4:])[0]
    if first < 8 or first + 2 > size:
        return False
    handle.seek(first)
    entries = struct.unpack(order + "H", handle.read(2))[0]
    offset = first + 2 + entries * 12
    if offset + 4 > size:
        return False
    handle.seek(offset)
    following = struct.unpack(order + "I", handle.read(4))[0]
    return 0 < following < size


def safe_stem(filename: str | None) -> str:
    base = re.split(r"[/\\]", filename or "")[-1]
    stem = re.sub(r"\.[^.]*$", "", base)
    return re.sub(r"[^A-Za-z0-9._-]", "_", stem)[:80] or "image"


def validated(parser: Callable[..., T], value: object, field: str) -> T:
    try:
        return parser(value)
    except ValidationError as error:
        issue = error.errors()[0]
        reason = "not_json" if issue["type"] == "json_invalid" else issue["type"]
        if reason == "value_error" and "error" in issue.get("ctx", {}):
            reason = str(issue["ctx"]["error"])
        raise ApiError("INVALID_PARAMS", {"field": field, "reason": reason}) from None


def _persist(image: UploadFile, max_bytes: int) -> tuple[Path, str]:
    if image.size is None or image.size > max_bytes:
        raise ApiError("IMAGE_TOO_LARGE")
    image.file.seek(0)
    image_format = sniff_format(image.file.read(16))
    if image_format is None:
        raise ApiError("UNSUPPORTED_FORMAT", {"reason": "magic_bytes"})
    if image_format == "tiff" and is_multi_page_tiff(image.file, image.size):
        raise ApiError("UNSUPPORTED_FORMAT", {"reason": "multi_page_tiff"})
    image.file.seek(0)
    directory = Path(tempfile.mkdtemp(prefix="sabugo-job-"))
    extension = EXTENSIONS[image_format]
    path = directory / ("image." + extension)
    try:
        with path.open("wb") as handle:
            shutil.copyfileobj(image.file, handle)
        return path, safe_stem(image.filename) + "." + extension
    except BaseException:
        shutil.rmtree(directory, ignore_errors=True)
        raise


async def save_upload(image: UploadFile, max_bytes: int) -> tuple[Path, str]:
    task = asyncio.create_task(asyncio.to_thread(_persist, image, max_bytes))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        # A thread cannot be cancelled. Keep the multipart file open until its
        # copy finishes, then delete the result before propagating cancellation.
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not task.cancelled() and task.exception() is None:
            path, _ = task.result()
            cleanup = asyncio.create_task(asyncio.to_thread(shutil.rmtree, path.parent, True))
            while not cleanup.done():
                try:
                    await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    continue
            cleanup.result()
        raise
