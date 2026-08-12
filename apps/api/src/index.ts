import { createApp } from "./app";
import { env } from "./lib/env";
import { createWorkerRunner } from "./services/runner";

const app = createApp({
  clientDist: env.WEB_DIST,
  maxQueueDepth: env.MAX_QUEUE_DEPTH,
  uploadsPerHour: env.UPLOADS_PER_HOUR,
  runner: createWorkerRunner({
    pythonBin: env.PYTHON_BIN,
    workerCwd: env.WORKER_CWD,
    maxMegapixels: env.MAX_MEGAPIXELS,
    timeoutSeconds: env.JOB_TIMEOUT_SECONDS,
  }),
});

export default { port: env.PORT, fetch: app.fetch };
