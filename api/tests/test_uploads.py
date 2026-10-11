import asyncio
import io
from pathlib import Path
import threading

import httpx
import pytest
from starlette.datastructures import UploadFile
from starlette.requests import ClientDisconnect

from main import create_app
from services import uploads
from settings import Settings


def test_concurrent_upload_reserves_capacity_before_second_body_is_read():
    async def scenario():
        async def runner(job, emit):
            return {"pipelineVersion": "1.3.0", "results": []}, ""
        app = create_app(Settings(FASTAPI_ENV="test", MAX_QUEUE_DEPTH=1), runner=runner)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                started, release = asyncio.Event(), asyncio.Event()
                request = httpx.Request("POST", "http://test/api/analyses", data={"dpi": "300"},
                                       files={"image": ("a.png", b"\x89PNG\r\n\x1a\nrest")})
                payload = request.read()

                async def slow():
                    yield payload[:32]
                    started.set()
                    await release.wait()
                    yield payload[32:]

                async def unread():
                    raise AssertionError("second_body_read")
                    yield b""

                first = asyncio.create_task(client.post("/api/analyses", content=slow(), headers=request.headers))
                await asyncio.wait_for(started.wait(), 2)
                try:
                    assert app.state.jobs.uploading == 1
                    second = await client.post("/api/analyses", content=unread())
                    assert second.status_code == 503
                finally:
                    release.set()
                assert (await first).status_code == 202
                assert app.state.jobs.uploading == 0
                await app.state.jobs.task
    asyncio.run(scenario())


def test_cancelled_upload_waits_for_copy_and_removes_directory(tmp_path, monkeypatch):
    copying, release = threading.Event(), threading.Event()
    directories = []
    original_mkdtemp = uploads.tempfile.mkdtemp
    original_copy = uploads.shutil.copyfileobj

    def directory(**kwargs):
        result = original_mkdtemp(dir=tmp_path, **kwargs)
        directories.append(Path(result))
        return result

    def blocked_copy(source, target):
        copying.set()
        assert release.wait(3)
        assert not source.closed
        original_copy(source, target)

    monkeypatch.setattr(uploads.tempfile, "mkdtemp", directory)
    monkeypatch.setattr(uploads.shutil, "copyfileobj", blocked_copy)

    async def scenario():
        image = UploadFile(io.BytesIO(b"\x89PNG\r\n\x1a\nrest"), size=12, filename="scan.png")
        task = asyncio.create_task(uploads.save_upload(image, 1024))
        assert await asyncio.to_thread(copying.wait, 2)
        try:
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert directories and all(not path.exists() for path in directories)
        await image.close()
    asyncio.run(scenario())


def test_persistence_failure_closes_output_and_removes_directory(tmp_path, monkeypatch):
    original_mkdtemp = uploads.tempfile.mkdtemp
    monkeypatch.setattr(uploads.tempfile, "mkdtemp", lambda **kwargs: original_mkdtemp(dir=tmp_path, **kwargs))
    def fail(source, target):
        target.write(b"partial")
        raise OSError("disk_full")
    monkeypatch.setattr(uploads.shutil, "copyfileobj", fail)
    image = UploadFile(io.BytesIO(b"\x89PNG\r\n\x1a\nrest"), size=12)
    with pytest.raises(OSError, match="disk_full"):
        asyncio.run(uploads.save_upload(image, 1024))
    assert not list(tmp_path.iterdir())


def test_disconnected_multipart_closes_spool_and_releases_reservation(monkeypatch):
    import starlette.formparsers as parser
    original = parser.SpooledTemporaryFile
    files = []
    def tracked(*args, **kwargs):
        file = original(*args, **kwargs)
        files.append(file)
        return file
    monkeypatch.setattr(parser, "SpooledTemporaryFile", tracked)

    async def scenario():
        app = create_app(Settings(FASTAPI_ENV="test"))
        partial = (b'--b\r\nContent-Disposition: form-data; name="dpi"\r\n\r\n300\r\n'
                   b'--b\r\nContent-Disposition: form-data; name="image"; filename="a.png"\r\n\r\n'
                   b'\x89PNG\r\n\x1a\n' + b'x' * 1024)
        messages = iter([{"type": "http.request", "body": partial, "more_body": True},
                         {"type": "http.disconnect"}])
        async def receive():
            return next(messages)
        async def send(message):
            pass
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                 "method": "POST", "scheme": "http", "path": "/api/analyses", "root_path": "",
                 "query_string": b"", "headers": [(b"content-type", b"multipart/form-data; boundary=b")],
                 "client": ("127.0.0.1", 1234), "server": ("127.0.0.1", 3000)}
        async with app.router.lifespan_context(app):
            with pytest.raises(ClientDisconnect):
                await app(scope, receive, send)
            assert files and all(file.closed for file in files)
            assert app.state.jobs.uploading == 0
            assert not app.state.jobs.jobs
    asyncio.run(scenario())
