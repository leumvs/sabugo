import type { ErrorEnvelope } from "../lib/errors";

/** The five events, exactly as they go on the wire. */
export type JobEvent =
  | { event: "queued"; data: { queuePosition: number } }
  | { event: "started"; data: Record<string, never> }
  | { event: "progress"; data: { stage: string; percent: number; region?: string } }
  | { event: "completed"; data: CompletedPayload }
  | { event: "failed"; data: ErrorEnvelope };

/** What the worker's `--json` produces, with the pictures turned into data URIs. */
export type CompletedPayload = {
  pipelineVersion: string;
  results: Array<Record<string, unknown>>;
};

export type Listener = (event: JobEvent) => void;

/** Keyed by job and not by session, so two tabs following the same job both
 *  get every event. Plain callbacks and not streams, so the queue and the
 *  runner know nothing about Hono. */
export function createEventBus() {
  const listeners = new Map<string, Set<Listener>>();

  return {
    subscribe(jobId: string, listener: Listener): () => void {
      const set = listeners.get(jobId) ?? new Set<Listener>();
      set.add(listener);
      listeners.set(jobId, set);

      return () => {
        set.delete(listener);
        if (set.size === 0) listeners.delete(jobId);
      };
    },

    publish(jobId: string, event: JobEvent): void {
      for (const listener of listeners.get(jobId) ?? []) listener(event);
    },

    listenerCount(jobId: string): number {
      return listeners.get(jobId)?.size ?? 0;
    },
  };
}

export type EventBus = ReturnType<typeof createEventBus>;
