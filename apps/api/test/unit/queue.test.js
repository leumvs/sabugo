import { describe, expect, test } from "bun:test";
import { ApiError } from "../../src/lib/errors";
import { createJobStore } from "../../src/services/jobs";
import { createQueue } from "../../src/services/queue";
import { createEventBus } from "../../src/services/sse-registry";

function job(id) {
  return {
    id,
    dpi: 600,
    params: { mode: "broken_roots" },
    rois: [],
    image: new Uint8Array([1]),
    format: "png",
    queuedAt: new Date().toISOString(),
    status: "pending",
  };
}

function harness(runner, maxDepth = 10) {
  const jobs = createJobStore();
  const bus = createEventBus();
  const queue = createQueue({ maxDepth, runner, jobs, bus });
  return { queue, jobs, bus };
}

const ok = { result: { pipelineVersion: "1.3.0", results: [] }, csv: "" };

describe("the queue", () => {
  test("runs in FIFO order", async () => {
    const order = [];
    const { queue } = harness(async (j) => {
      order.push(j.id);
      await Bun.sleep(1);
      return ok;
    });

    for (const id of ["a", "b", "c"]) queue.enqueue(job(id));
    await Bun.sleep(30);

    expect(order).toEqual(["a", "b", "c"]);
  });

  test("never runs two at a time", async () => {
    let inFlight = 0;
    let peak = 0;
    const { queue } = harness(async () => {
      peak = Math.max(peak, ++inFlight);
      await Bun.sleep(5);
      inFlight--;
      return ok;
    });

    for (const id of ["a", "b", "c", "d"]) queue.enqueue(job(id));
    await Bun.sleep(60);

    expect(peak).toBe(1);
  });

  test("a full queue is refused rather than accepted", async () => {
    const { queue } = harness(async () => {
      await Bun.sleep(50);
      return ok;
    }, 2);

    queue.enqueue(job("running"));
    await Bun.sleep(1); // let the first one leave the waiting list
    queue.enqueue(job("a"));
    queue.enqueue(job("b"));

    expect(() => queue.enqueue(job("c"))).toThrow(ApiError);
    try {
      queue.enqueue(job("d"));
    } catch (error) {
      expect(error.code).toBe("SERVICE_AT_CAPACITY");
      expect(error.status).toBe(503);
    }
  });

  test("publishes every transition on that job's stream", async () => {
    const { queue, bus } = harness(async (_j, emit) => {
      emit({ event: "progress", data: { stage: "segment", percent: 20 } });
      return ok;
    });

    const seen = [];
    const target = job("a");
    bus.subscribe("a", (event) => seen.push(event.event));
    queue.enqueue(target);
    await Bun.sleep(20);

    expect(seen).toEqual(["queued", "started", "progress", "completed"]);
  });

  test("a failing run becomes `failed` with the token, and never a retry", async () => {
    let attempts = 0;
    const { queue, bus, jobs } = harness(async () => {
      attempts++;
      throw new ApiError("NO_ROOTS_DETECTED");
    });

    const seen = [];
    bus.subscribe("a", (event) => seen.push(event));
    queue.enqueue(job("a"));
    await Bun.sleep(20);

    expect(attempts).toBe(1);
    expect(seen.at(-1)).toEqual({
      event: "failed",
      data: { code: "NO_ROOTS_DETECTED", message: "no_roots_detected" },
    });
    expect(jobs.get("a").status).toBe("failed");
  });

  test("an error that is not an ApiError still reaches the client", async () => {
    const { queue, bus } = harness(async () => {
      throw new TypeError("undefined is not a function");
    });

    const seen = [];
    bus.subscribe("a", (event) => seen.push(event));
    queue.enqueue(job("a"));
    await Bun.sleep(20);

    expect(seen.at(-1).event).toBe("failed");
    expect(seen.at(-1).data.code).toBe("INTERNAL_ERROR");
    // The runtime's own message is prose and can carry a filesystem path.
    expect(JSON.stringify(seen.at(-1).data)).not.toContain("undefined is not a function");
    expect(seen.at(-1).data.details).toBeUndefined();
  });

  test("the queue position counts what is ahead, running included", async () => {
    const { queue } = harness(async () => {
      await Bun.sleep(50);
      return ok;
    });

    expect(queue.enqueue(job("a"))).toBe(0);
    await Bun.sleep(1);
    expect(queue.enqueue(job("b"))).toBe(1);
    expect(queue.enqueue(job("c"))).toBe(2);
  });
});
