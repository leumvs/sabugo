import logging
from contextlib import asynccontextmanager
from functools import partial
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.formparsers import MultiPartException
from starlette.types import ASGIApp, Receive, Scope, Send

from errors import ApiError, envelope
from routers import analyses
from services.jobs import Jobs, Runner, UploadAllowance
from services.processing import run_analysis
from settings import Settings


class BodyLimit:
    def __init__(self, app: ASGIApp, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"].rstrip("/") != "/api/analyses":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        try:
            declared = int(headers.get(b"content-length", b"0"))
        except ValueError:
            return await JSONResponse(envelope("INVALID_PARAMS", {"field": "content-length"}), status_code=400)(scope, receive, send)
        if declared < 0:
            return await JSONResponse(envelope("INVALID_PARAMS", {"field": "content-length"}), status_code=400)(scope, receive, send)
        if declared > self.max_bytes:
            return await JSONResponse(envelope("IMAGE_TOO_LARGE"), status_code=413)(scope, receive, send)
        received = 0

        async def bounded_receive():
            nonlocal received
            message = await receive()
            received += len(message.get("body", b""))
            if received > self.max_bytes:
                # The multipart parser closes spooled files for this exception.
                raise MultiPartException("image_too_large")
            return message

        await self.app(scope, bounded_receive, send)


def create_app(settings: Settings | None = None, runner: Runner | None = None,
               client_dist: str | Path | None = None, result_ttl: float = 300) -> FastAPI:
    settings = settings or Settings.from_environment()
    jobs = Jobs(runner or partial(run_analysis, settings=settings), settings.MAX_QUEUE_DEPTH, result_ttl)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            yield
        finally:
            await jobs.close()

    app = FastAPI(title="Sabugo", version="0.1.0", lifespan=lifespan,
                  openapi_url="/api/openapi.json", docs_url="/api/docs", redoc_url=None)
    app.state.settings = settings
    app.state.jobs = jobs
    app.state.allowance = UploadAllowance(settings.UPLOADS_PER_HOUR)
    app.add_middleware(BodyLimit, max_bytes=settings.MAX_UPLOAD_BYTES + 1024 * 1024)

    @app.exception_handler(ApiError)
    async def api_error(request: Request, error: ApiError) -> JSONResponse:
        return JSONResponse(error.envelope, status_code=error.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        issue = error.errors()[0]
        return JSONResponse(envelope("INVALID_PARAMS", {"field": str(issue["loc"][-1]), "reason": issue["type"]}), status_code=400)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException) -> JSONResponse:
        if request.url.path == "/api" or request.url.path.startswith("/api/"):
            if error.detail == "image_too_large":
                return JSONResponse(envelope("IMAGE_TOO_LARGE"), status_code=413)
            code = "NOT_FOUND" if error.status_code == 404 else "INVALID_PARAMS"
            return JSONResponse(envelope(code), status_code=404 if code == "NOT_FOUND" else 400)
        return JSONResponse({"message": "not_found"}, status_code=error.status_code)

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, error: Exception) -> JSONResponse:
        logging.exception("request_failed")
        return JSONResponse(envelope("INTERNAL_ERROR"), status_code=500)

    @app.get("/api/health", tags=["infra"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(analyses.router)

    @app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"], include_in_schema=False)
    @app.api_route("/api", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"], include_in_schema=False)
    async def missing_api(request: Request):
        raise ApiError("NOT_FOUND")

    directory = Path(client_dist) if client_dist is not None else settings.client_dist
    app.frontend("/", directory=directory, fallback="404.html", check_dir=settings.FASTAPI_ENV == "production")
    return app


app = create_app()
