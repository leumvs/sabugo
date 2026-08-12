# ---- deps ----
FROM oven/bun:1-alpine AS deps
WORKDIR /app

COPY package.json bun.lock ./
COPY apps/api/package.json ./apps/api/
COPY apps/web/package.json ./apps/web/
RUN bun install --frozen-lockfile

# ---- build ----
FROM deps AS build
WORKDIR /app
COPY . .
RUN bun run build

# ---- runtime ----
# `opencv-contrib-python-headless` publishes no musl wheel, and on Alpine pip
# falls back to building OpenCV from source.
FROM oven/bun:1-debian AS runtime
WORKDIR /app
ENV NODE_ENV=production

# Debian's python is externally managed (PEP 668), so a venv rather than
# `pip install --break-system-packages`.
RUN apt-get update \
  && apt-get install -y --no-install-recommends python3 python3-venv \
  && rm -rf /var/lib/apt/lists/* \
  && python3 -m venv /opt/venv

# Bun keeps each workspace's dependencies under its own node_modules; the root
# holds only the root devDependencies, so copying it alone leaves hono unresolvable.
COPY --from=deps  /app/node_modules          ./node_modules
COPY --from=deps  /app/apps/api/node_modules ./apps/api/node_modules

COPY --from=build /app/apps/web/dist         ./apps/web/dist
COPY --from=build /app/apps/api/src          ./apps/api/src
COPY --from=build /app/apps/api/package.json ./apps/api/
COPY --from=build /app/package.json          ./

COPY apps/worker/pyproject.toml ./apps/worker/
COPY apps/worker/src            ./apps/worker/src
RUN /opt/venv/bin/pip install --no-cache-dir ./apps/worker

ENV WEB_DIST=/app/apps/web/dist
ENV PYTHON_BIN=/opt/venv/bin/python
ENV WORKER_CWD=/app/apps/worker
ENV PORT=3000
EXPOSE ${PORT}

USER bun

CMD ["bun", "run", "apps/api/src/index.ts"]
