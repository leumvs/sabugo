FROM oven/bun:1-alpine AS web
WORKDIR /app/web
COPY web/package.json web/bun.lock web/bunfig.toml ./
RUN bun install --frozen-lockfile
COPY web ./
RUN bun run build

FROM python:3.14-slim AS runtime
COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /usr/local/bin/uv
WORKDIR /app/api
ENV FASTAPI_ENV=production \
    WEB_DIST=/app/web/dist \
    PORT=3000 \
    UV_COMPILE_BYTECODE=1
COPY api/pyproject.toml api/uv.lock api/.python-version ./
RUN uv sync --locked --no-dev --no-cache
COPY api/main.py api/settings.py api/schemas.py api/errors.py ./
COPY api/routers ./routers
COPY api/services ./services
COPY api/imaging ./imaging
COPY --from=web /app/web/dist /app/web/dist
RUN useradd --create-home --uid 10001 sabugo
USER sabugo
EXPOSE 3000
CMD ["sh", "-c", "exec .venv/bin/uvicorn main:app --host 0.0.0.0 --port \"${PORT:-3000}\""]
