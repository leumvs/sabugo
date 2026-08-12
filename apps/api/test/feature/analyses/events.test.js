import { describe, expect, test } from "bun:test";
import { ApiError } from "../../../src/lib/errors";
import { fakeRunner, gatedRunner, makeApp, readEvents, upload } from "../../helpers";

async function queueOne(app, options) {
  const res = await app.request("/api/analyses", upload(options));
  return (await res.json()).id;
}

/** Open the stream, let the handler subscribe, then let the run proceed: a
 *  sleep instead of this ordering is a race. */
async function follow(app, id, runner) {
  const response = await app.request(`/api/analyses/${id}/events`);
  const reading = readEvents(response);
  await Bun.sleep(10);
  runner.release();
  return reading;
}

describe("GET /api/analyses/:id/events", () => {
  test("carries the run from queued to completed, result included", async () => {
    const runner = gatedRunner({
      progress: [
        { stage: "segment", percent: 20 },
        { stage: "skeletonize", percent: 60 },
      ],
    });
    const { app } = await makeApp({ runner });

    const id = await queueOne(app, {});
    const events = await follow(app, id, runner);
    const names = events.map((event) => event.event);

    // SSE has no replay: only the terminal event is held.
    expect(names).toEqual(["progress", "progress", "completed"]);

    const completed = events.at(-1).data;
    expect(completed.pipelineVersion).toBe("1.3.0");
    expect(completed.results[0].metrics.totalRootLength).toBe(12.5);
  });

  test("the analysis id is not repeated in the payload", async () => {
    const runner = gatedRunner();
    const { app } = await makeApp({ runner });
    const id = await queueOne(app, {});
    const events = await follow(app, id, runner);

    for (const event of events) {
      expect(JSON.stringify(event.data)).not.toContain(id);
    }
  });

  test("a failure arrives as `failed` with the error envelope", async () => {
    const runner = gatedRunner({ fail: new ApiError("NO_ROOTS_DETECTED") });
    const { app } = await makeApp({ runner });

    const id = await queueOne(app, {});
    const events = await follow(app, id, runner);

    expect(events.at(-1)).toEqual({
      event: "failed",
      data: { code: "NO_ROOTS_DETECTED", message: "no_roots_detected" },
    });
  });

  test("a client that connects after the end still gets the result", async () => {
    // Connecting after the end: the terminal event is delivered while the
    // result lives, and the stream closes.
    const { app } = await makeApp({ runner: fakeRunner() });

    const id = await queueOne(app, {});
    await Bun.sleep(30); // the job finishes with nobody listening

    const events = await readEvents(await app.request(`/api/analyses/${id}/events`));
    expect(events).toHaveLength(1);
    expect(events[0].event).toBe("completed");
  });

  test("an unknown id gets `failed` with NOT_FOUND, not silence", async () => {
    const { app } = await makeApp();
    const events = await readEvents(await app.request("/api/analyses/nope/events"));

    expect(events).toEqual([
      { event: "failed", data: { code: "NOT_FOUND", message: "not_found" } },
    ]);
  });

  test("two tabs on the same job both get every event", async () => {
    const runner = gatedRunner();
    const { app } = await makeApp({ runner });
    const id = await queueOne(app, {});

    const responses = await Promise.all([
      app.request(`/api/analyses/${id}/events`),
      app.request(`/api/analyses/${id}/events`),
    ]);
    // Not `.map(readEvents)`: map passes the index as the second argument,
    // which lands on `limit` and cuts the first reader off at zero events.
    const reading = Promise.all(responses.map((response) => readEvents(response)));
    await Bun.sleep(10);
    runner.release();
    const [first, second] = await reading;

    expect(first.at(-1).event).toBe("completed");
    expect(second.at(-1).event).toBe("completed");
  });

  test("the proxy headers that keep the stream unbuffered are set", async () => {
    const { app } = await makeApp();
    const res = await app.request("/api/analyses/nope/events");

    expect(res.headers.get("content-type")).toContain("text/event-stream");
    expect(res.headers.get("x-accel-buffering")).toBe("no");
  });
});

describe("GET /api/analyses/:id/export", () => {
  test("returns the worker's own features.csv as an attachment", async () => {
    const csv = "File.Name,Region.of.Interest\nroot.png,Full\n";
    const { app } = await makeApp({ runner: fakeRunner({ csv }) });

    const id = await queueOne(app, {});
    await Bun.sleep(30);
    const res = await app.request(`/api/analyses/${id}/export?format=csv`);

    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toContain("text/csv");
    expect(res.headers.get("content-disposition")).toContain("attachment");
    expect(await res.text()).toBe(csv);
  });

  test("before `completed` there is nothing to export", async () => {
    const { app } = await makeApp({ runner: fakeRunner({ delayMs: 200 }) });
    const id = await queueOne(app, {});

    const res = await app.request(`/api/analyses/${id}/export?format=csv`);
    expect(res.status).toBe(404);
    expect((await res.json()).code).toBe("NOT_FOUND");
  });

  test("a failed job has no export either", async () => {
    const { app } = await makeApp({ runner: fakeRunner({ fail: new ApiError("INVALID_IMAGE") }) });
    const id = await queueOne(app, {});
    await Bun.sleep(30);

    expect((await app.request(`/api/analyses/${id}/export?format=csv`)).status).toBe(404);
  });

  test("a format the route does not implement is refused, not guessed", async () => {
    const { app } = await makeApp();
    const id = await queueOne(app, {});
    await Bun.sleep(30);

    expect((await app.request(`/api/analyses/${id}/export?format=xlsx`)).status).toBe(400);
  });
});
