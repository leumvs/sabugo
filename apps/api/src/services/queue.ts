import { ApiError, type ErrorCode, envelope } from "../lib/errors";
import type { Job, JobStore } from "./jobs";
import type { Runner } from "./runner";
import type { EventBus } from "./sse-registry";

export type QueueConfig = {
  maxDepth: number;
  runner: Runner;
  jobs: JobStore;
  bus: EventBus;
  onSettled?: (job: Job) => void;
};

/** Concurrency 1, because one 100 MP image peaks around 4.8 GB. FIFO, and no
 *  retry: the worker's failures are deterministic. */
export function createQueue({ maxDepth, runner, jobs, bus, onSettled }: QueueConfig) {
  const waiting: Job[] = [];
  let running: Job | null = null;

  function depth(): number {
    return waiting.length;
  }

  function enqueue(job: Job): number {
    if (waiting.length >= maxDepth) {
      throw new ApiError("SERVICE_AT_CAPACITY", { queueDepth: waiting.length, maxDepth });
    }
    jobs.put(job);
    waiting.push(job);

    // Jobs ahead of this one, the running one included.
    const position = waiting.length - 1 + (running ? 1 : 0);
    publish(job, { event: "queued", data: { queuePosition: position } });
    void pump();
    return position;
  }

  async function pump(): Promise<void> {
    if (running) return;
    const job = waiting.shift();
    if (!job) return;

    running = job;
    job.status = "processing";
    job.startedAt = Date.now();
    publish(job, { event: "started", data: {} });

    try {
      const { result, csv } = await runner(job, (event) => bus.publish(job.id, event));
      job.status = "completed";
      job.result = result;
      job.csv = csv;
      publish(job, { event: "completed", data: result });
    } catch (error) {
      job.status = "failed";
      if (error instanceof ApiError) {
        job.error = error.envelope;
      } else {
        // The text goes to the log, never into the envelope: it is prose no
        // client can translate, and it can carry a filesystem path.
        console.error(JSON.stringify({ level: "error", jobId: job.id, error: String(error) }));
        job.error = envelope("INTERNAL_ERROR" as ErrorCode);
      }
      publish(job, { event: "failed", data: job.error });
    } finally {
      job.finishedAt = Date.now();
      jobs.expireLater(job.id);
      onSettled?.(job);
      running = null;
      void pump();
    }
  }

  /** The terminal event is remembered, so a client connecting after the job
   *  ended gets it instead of a stream that never speaks. */
  function publish(job: Job, event: Parameters<EventBus["publish"]>[1]): void {
    if (event.event === "completed" || event.event === "failed") job.terminal = event;
    bus.publish(job.id, event);
  }

  function isFull(): boolean {
    return waiting.length >= maxDepth;
  }

  return {
    enqueue,
    depth,
    isFull,
    get running() {
      return running;
    },
  };
}

export type Queue = ReturnType<typeof createQueue>;
