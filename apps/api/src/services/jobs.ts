import type { ErrorEnvelope } from "../lib/errors";
import type { AnalysisParams, Roi } from "../modules/analyses/model";
import type { CompletedPayload, JobEvent } from "./sse-registry";

export type JobStatus = "pending" | "processing" | "completed" | "failed";

/** The job of 3, in memory from the POST to the terminal event, and gone after. */
export type Job = {
  id: string;
  dpi: number;
  params: AnalysisParams;
  rois: Roi[];
  image: Uint8Array;
  format: string;
  /** Sanitised stem of the uploaded name; the worker reports it as `File.Name`. */
  filename: string;
  /** `?preview=1`: segmentation only, so there is no CSV and no metrics. */
  preview: boolean;
  queuedAt: string;
  status: JobStatus;
  /** The last event published, so a stream that opened late is not left mute. */
  terminal?: JobEvent;
  result?: CompletedPayload;
  /** The worker's own features.csv, which is what the export route returns. */
  csv?: string;
  error?: ErrorEnvelope;
  startedAt?: number;
  finishedAt?: number;
};

/** How long a finished job stays readable; the export route answers
 *  `NOT_FOUND` outside this window. */
export const RESULT_TTL_MS = 5 * 60 * 1000;

export function createJobStore(ttlMs: number = RESULT_TTL_MS) {
  const jobs = new Map<string, Job>();
  const timers = new Map<string, ReturnType<typeof setTimeout>>();

  return {
    put(job: Job): void {
      jobs.set(job.id, job);
    },

    get(id: string): Job | undefined {
      return jobs.get(id);
    },

    /** Terminal states are terminal: reprocessing is a new job. */
    expireLater(id: string): void {
      if (timers.has(id)) return;
      const timer = setTimeout(() => {
        jobs.delete(id);
        timers.delete(id);
      }, ttlMs);
      timer.unref?.();
      timers.set(id, timer);
    },

    clear(): void {
      for (const timer of timers.values()) clearTimeout(timer);
      timers.clear();
      jobs.clear();
    },
  };
}

export type JobStore = ReturnType<typeof createJobStore>;
