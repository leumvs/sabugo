# Sabugo

Open-source web tool for root and fiber image analysis. Bun workspaces: `apps/api/` (Hono API, also serves the client build) and `apps/web/` (Svelte SPA). The image pipeline is the Python worker in `apps/worker/`. Everything that deploys the thing — `Dockerfile`, `docker-compose.yml` — is in `infra/`.

The project carries **exactly two READMEs and no other prose**: [README.md](README.md) says what Sabugo is, how it compares against the established tools, and how to run it in development and in production; [apps/worker/README.md](apps/worker/README.md) is the entry point for the pipeline. Both are in English. Do not add a third document — what would go in one belongs in one of those two, or in the code.

## Commands

```bash
bun run dev      # web (:5173, proxies /api) + api (:3000)
bun run build    # web build into apps/web/dist
bun run start    # api in production, serving apps/web/dist
bun run test     # bun test
bun run check    # biome + typecheck — what CI runs
bun run format   # biome check --write
```

## Code rules

**English everywhere** — identifiers, comments, file names, commit messages, both READMEs, and every string the API returns. Portuguese belongs in conversation with the author and nowhere in the repository.

**Comments: the default is not to write one, and the ones that stay are about mechanism.** A comment earns its place when the code cannot say it on its own — a library that misbehaves, an order that breaks if swapped, an invariant nothing enforces. It does **not** earn its place by narrating a decision: no history, no measurements, no "this was chosen over that", no justifying a UI choice. Never restate what the code already does, and **never point at a document** — a pointer rots the moment the document moves, and a reader who has to open another file to understand a line has not been helped. What the measurements settled belongs in `apps/worker/README.md`; the code says how it works:

```ts
// Errors thrown mid-stream never reach Hono's `onError`: the response has
// already started, so the handling has to be streamSSE's third argument.
```

**API text is snake_case, never prose.** Every string the API returns is a machine-readable token that the client translates:

```json
{ "message": "storage_quota_exceeded" }
```

The client translates the token and never displays raw text. Emitting tokens instead of sentences removes the chance of displaying raw text by accident.

**Research the technology before implementing.** When reaching for a library, a runtime API, or a tool flag, check the current documentation first. Do not trust memory for signatures, flags, or version behavior.

This is not ceremony. Four decisions in this repo changed because of it: Postgres compresses `bytea` when it TOASTs it, so image columns need `SET STORAGE EXTERNAL` to stop it burning CPU recompressing PNGs, `@hono/node-ws` is deprecated in favor of built-in support in `@hono/node-server`, Biome only parses the `<script>` block of `.svelte` files, and `bun test` has `--pass-with-no-tests`. Assuming any of them from memory would have cost rework.

## Repository traps

Each of these already cost time here, and none is guessable from reading the code.

| Trap | What happens if ignored |
|---|---|
| Route sub-apps must be `OpenAPIHono`, not `Hono` | mounts and responds fine, but silently disappears from the API docs |
| `app.doc()` goes on the root app, **after** mounting | paths lose the `/api` prefix and the docs point at routes that 404 |
| A **Zod** schema on a `multipart/form-data` request body | `@hono/zod-openapi` attaches `zValidator("form", …)`, which calls `c.req.parseBody()` and reads the whole request into memory — the one thing the upload route must not do. A **plain** OpenAPI schema object is documented and skipped (`if (!isZod(schema)) continue`), which is how `POST /api/analyses` stays in the docs without a validator |
| `serveStatic` mounts **after** the routes | swallows the entire API |
| `serveStatic({ path })` still needs `root` | `path` is joined against `root`, which defaults to `"./"`. An absolute path without a root resolves relative on POSIX and 404s — passing on Windows, failing in Docker and CI |
| Biome reads only the `<script>` block of `.svelte` | `noUnusedVariables` is off for those files only; it still applies to `.ts` |
| A `$state` value exported as a reassigned `let` | the importing module keeps the old value — reassigning a binding notifies nobody across a module boundary. Export a **property of a `$state` proxy**. Same reason an object pushed into a reactive array has to be read back out of it: mutating the original reference writes to the same data and re-renders nothing |
| `max-h-full` on an image whose parent shrink-wraps it | the percentage resolves against a parent with no definite height, so the browser drops the constraint and a 3000 px scan renders at full size. The fit has to be a measured pixel value (`bind:clientHeight` on the scroll container) — and the wrapper still has to shrink-wrap, or the ROI overlay stops lining up with the image |
| Bun loads `.env` natively | **never install `dotenv`** |
| `bun run --filter` runs with cwd inside the package | the root `.env` needs `--env-file`, already wired into the scripts |
| `bun install --frozen-lockfile` needs **every** workspace manifest | fails in Docker with a lockfile error that never names the missing file |
| Compose lives in `infra/` and resolves every relative path against **its own directory**, not the cwd | hence `context: ..`, `dockerfile: infra/Dockerfile` and `env_file: ../.env`. `.dockerignore` stays at the repo **root**, because Docker reads it from the build context — moving it beside the Dockerfile ships `node_modules` into the image |
| Compose `env_file` **overrides** the image's `ENV` | the dev `.env` wins inside the container, so `PYTHON_BIN` points at `../worker/.venv/Scripts/python.exe` — a Windows path, in a Linux container. Nothing fails at startup: `/api/health` is green and the container reports healthy, and every analysis dies with `ENOENT` on the interpreter. Any path the image sets has to be repeated in the `environment:` block, which is why `WEB_DIST` was already there |
| `apps/worker/` is **not** a Bun workspace | adding it to `workspaces` breaks `bun install` — there is no `package.json` to resolve |
| `cv2.distanceTransform` straight after the bbox crop | the crop guarantees the mask touches all four borders, so those pixels have no background to measure against and a solid band comes back as ~3.7e18. Pad 1 px, transform, unpad. Silent on real roots, fatal on a rectangle fixture, and the DT feeds the skeleton |
| `cv2.distanceTransform` with `DIST_MASK_PRECISE` is not reproducible (OpenCV 5.0.0) | the same input returns one of two arrays, differing by one ULP on a few hundred pixels. It tracks the allocation, not the thread count, so `setNumThreads` does not help. Harmless for the metrics, fatal for the ridge detection of 5.2, which compares distances for equality: it flipped 20 ridge pixels and 6 fragments on one fixture. Every exact euclidean distance is the root of an integer, so `sqrt(rint(d²))` snaps it back — `snap_to_exact` in `apps/worker/src/sabugo_worker/pipeline.py` |
| `export default { port, fetch }` | the object's `port` beats the `PORT` env var; without it, `env.PORT` is dead code |

## Tests

`bun test` over `apps/api/test/`, and `apps/worker/.venv/Scripts/pytest` over `apps/worker/tests/`. The two suites are separate and neither runs the other.

**A test that does not fail when you break what it guards is testing nothing.** After writing a test for an invariant, break the invariant on purpose and confirm it goes red. That is how the mount-order test was caught passing in both orders — it was missing a real client-build fixture on disk, so `serveStatic` had nothing to serve and fell through either way.

> ⚠️ **In Python, run that check with `python -B` and no `__pycache__`.** An edit that keeps the file the same size — `min` for `max`, `<` for `<=`, `+` for `-` — can leave the byte count unchanged, and the import machinery decides staleness from size and mtime. Rewrite the file twice within the same second and the interpreter reuses the old `.pyc`: the mutant never runs, the suite passes, and the survivor looks like an equivalent mutant. It cost a wrong conclusion once already — `best = min(values)` in `apps/worker/validation/metrics.py` "survived" and dies immediately with the cache cleared. Same-length edits are the most common kind in a mutation check, so this is not an edge case.

Dependencies a test needs to control are passed **as parameters** (`createApp(clientDist)`), never read from `env` inside the module.

## The Python worker

`apps/worker/`, beside `apps/api/` and `apps/web/`. It is **not** a Bun workspace — no `package.json`, and it never goes in the root `workspaces` array. Its own image, its own dependency manifest, its own test runner.

```
apps/worker/
  README.md             # the only doc under apps/worker/, in English
  pyproject.toml        # distribution name sabugo-worker
  src/sabugo_worker/    # import name, snake_case
  tests/
  validation/           # external ground truth, four tools side by side — is the measurement good?
    data/                 # the Zenodo downloads, ~2 GB, gitignored
    results/              # the CSVs that come out. Versioned, because the images are not
```

`src/` layout, not flat: without it pytest imports the working directory instead of the installed package, so the tests pass against code that is not what ships.

`apps/worker/README.md` is the single entry point for the worker — layout, how to run, what to download from Zenodo and where, how the tests are built, and the results. Do not add a second README under `apps/worker/`.

`python -m sabugo_worker.cli <image|dir> --dpi 600` runs the pipeline with no queue and no database. That is the development loop for the algorithm, and it is what the validation scripts drive.

**`apps/worker/validation/` is the ground truth, and it is external on purpose.** A growth model's own geometry, a copper wire's gauge, and rendered shapes whose length and diameter are exact by construction. Agreement with any particular tool is not a target: where the established tools disagree with the truth, and they do, matching them is the wrong result. RhizoVision Explorer appears there as one of three compared tools, on the same footing as WinRhizo and IJ_Rhizo.

**Read `apps/worker/README.md` before touching the pipeline.** It carries the measured results, the export column contract, and — more useful than any of it — the hypotheses that were measured and **refused**. Three of them concerned the length deficit alone. Re-running a dead one is the most expensive mistake available in this directory.

Parts of the pipeline are ported from RhizoVision Explorer and from `cvutil`, both GPL-3.0, © Noble Research Institute, LLC; the modules carrying ported code declare it in their header, and the licence section of `README.md` records what the derivation obliges. That is provenance, not a standard to match. Skeletonization is **not** in the RhizoVision Explorer repository — ridge detection and steepest ascent live in `cvutil/cvutil_bwskel.cpp`.

## Before finishing a task

`bun run check` and `bun test` green. Commit and push only when asked.
