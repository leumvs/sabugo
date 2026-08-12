import { describe, expect, test } from "bun:test";
import { fakeRunner, makeApp, PNG_BYTES, upload } from "../../helpers";

async function post(app, options) {
  return app.request("/api/analyses", upload(options));
}

describe("POST /api/analyses", () => {
  test("accepts an image and queues it", async () => {
    const { app } = await makeApp();
    const res = await post(app, {});

    expect(res.status).toBe(202);
    const body = await res.json();
    expect(body.status).toBe("pending");
    expect(body.queuePosition).toBe(0);
    expect(body.id).toMatch(/^[0-9a-f-]{36}$/);
    expect(body.queuedAt).toMatch(/Z$/);
  });

  test("the parameters reach the worker, defaults included", async () => {
    const runner = fakeRunner();
    const { app } = await makeApp({ runner });

    await post(app, { params: { mode: "whole_root", threshold_value: 180 } });
    await Bun.sleep(20);

    const [job] = runner.calls;
    expect(job.params.mode).toBe("whole_root");
    expect(job.params.threshold_value).toBe(180);
    expect(job.params.diameter_ranges_mm).toEqual([2.0, 5.0]);
    expect(job.params.keep_largest).toBe(true);
    expect(job.params.show_medial_axis).toBe(true);
    expect(job.params.medial_axis_width).toBe(3);
    expect(job.params.show_dist_map).toBe(false);
  });

  test("?preview=1 marks the job, and nothing else does", async () => {
    const runner = fakeRunner();
    const { app } = await makeApp({ runner });

    expect((await app.request("/api/analyses?preview=1", upload({}))).status).toBe(202);
    expect((await app.request("/api/analyses", upload({}))).status).toBe(202);
    await Bun.sleep(20);

    expect(runner.calls.map((job) => job.preview)).toEqual([true, false]);
  });
});

describe("the uploaded name", () => {
  test("reaches the worker, because it becomes File.Name in the export", async () => {
    const runner = fakeRunner();
    const { app } = await makeApp({ runner });

    await post(app, { name: "scan-04 (repeat).png" });
    await Bun.sleep(20);

    // Spaces and parentheses go; the stem survives.
    expect(runner.calls[0].filename).toBe("scan-04__repeat_");
  });

  test("a name that tries to leave the directory is rebuilt, not trusted", async () => {
    const runner = fakeRunner();
    const { app } = await makeApp({ runner });

    await post(app, { name: "../../../etc/passwd.png" });
    await Bun.sleep(20);

    expect(runner.calls[0].filename).toBe("passwd");
  });

  test("a nameless upload still has a name to write", async () => {
    const runner = fakeRunner();
    const { app } = await makeApp({ runner });

    await post(app, { name: ".png" });
    await Bun.sleep(20);

    expect(runner.calls[0].filename).toBe("image");
  });
});

describe("parameter validation", () => {
  test("diameter boundaries out of order are refused", async () => {
    const { app } = await makeApp();
    const res = await post(app, { params: { diameter_ranges_mm: [5.0, 2.0] } });

    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.code).toBe("INVALID_PARAMS");
    expect(body.details.field).toBe("params");
    expect(body.details.reason).toBe("diameter_ranges_must_be_strictly_increasing");
  });

  test("no error string is ever prose", async () => {
    // Zod's own message is an English sentence, which no client can
    // translate.
    const { app } = await makeApp();
    const cases = [
      { dpi: "9000" },
      { params: { threshold_value: 900 } },
      { params: { diameter_ranges_mm: [] } },
      { rois: [{ name: "a", x: -1, y: 0, width: 1, height: 1 }] },
    ];

    for (const options of cases) {
      const body = await (await post(app, options)).json();
      expect(body.message).toMatch(/^[a-z_]+$/);
      expect(body.details.reason, JSON.stringify(options)).toMatch(/^[a-z_]+$/);
    }
  });

  test("more than eleven boundaries is more than twelve classes", async () => {
    const { app } = await makeApp();
    const many = Array.from({ length: 12 }, (_, index) => index + 1);
    expect((await post(app, { params: { diameter_ranges_mm: many } })).status).toBe(400);
  });

  test("a boundary at zero or below is refused", async () => {
    const { app } = await makeApp();
    expect((await post(app, { params: { diameter_ranges_mm: [0] } })).status).toBe(400);
  });

  test("DPI outside [50, 4800] is refused", async () => {
    const { app } = await makeApp();
    expect((await post(app, { dpi: "49" })).status).toBe(400);
    expect((await post(app, { dpi: "4801" })).status).toBe(400);
    expect((await post(app, { dpi: "50" })).status).toBe(202);
  });

  test("DPI is mandatory: without it nothing is in millimetres", async () => {
    const { app } = await makeApp();
    const body = new FormData();
    body.append("image", new File([PNG_BYTES], "root.png"));

    const res = await app.request("/api/analyses", { method: "POST", body });
    expect(res.status).toBe(400);
    expect((await res.json()).details.field).toBe("dpi");
  });

  test("more than ten ROIs is refused", async () => {
    const { app } = await makeApp();
    const roi = (name) => ({ name, x: 0, y: 0, width: 10, height: 10 });
    const eleven = Array.from({ length: 11 }, (_, i) => roi(`roi_${i}`));

    expect((await post(app, { rois: eleven })).status).toBe(400);
    expect((await post(app, { rois: eleven.slice(0, 10) })).status).toBe(202);
  });

  test("params that are not JSON say so", async () => {
    const { app } = await makeApp();
    const body = new FormData();
    body.append("dpi", "600");
    body.append("params", "{not json");
    body.append("image", new File([PNG_BYTES], "root.png"));

    const res = await app.request("/api/analyses", { method: "POST", body });
    expect((await res.json()).details.reason).toBe("not_json");
  });
});

describe("format validation by magic bytes", () => {
  test("a .png that is an executable is refused, and never queued", async () => {
    const runner = fakeRunner();
    const { app } = await makeApp({ runner });
    const executable = new TextEncoder().encode("MZ\x90\x00 this is a PE binary");

    const res = await post(app, { image: executable });
    await Bun.sleep(20);

    expect(res.status).toBe(415);
    expect((await res.json()).code).toBe("UNSUPPORTED_FORMAT");
    expect(runner.calls).toHaveLength(0);
  });

  test("a multi-page TIFF is refused rather than silently truncated", async () => {
    const { app } = await makeApp();
    const multi = new Uint8Array(8 + 2 + 12 + 4 + 16);
    const view = new DataView(multi.buffer);
    multi.set([0x49, 0x49, 0x2a, 0x00]);
    view.setUint32(4, 8, true);
    view.setUint16(8, 1, true);
    view.setUint32(22, 30, true);

    const res = await post(app, { image: multi });
    expect(res.status).toBe(415);
    expect((await res.json()).details.reason).toBe("multi_page_tiff");
  });

  test("a single-page TIFF is accepted", async () => {
    const { app } = await makeApp();
    const single = new Uint8Array(8 + 2 + 12 + 4 + 16);
    const view = new DataView(single.buffer);
    single.set([0x49, 0x49, 0x2a, 0x00]);
    view.setUint32(4, 8, true);
    view.setUint16(8, 1, true);
    view.setUint32(22, 0, true);

    expect((await post(app, { image: single })).status).toBe(202);
  });
});

describe("rate limiting per IP", () => {
  test("the upload allowance runs out, and it is counted per address", async () => {
    const { app } = await makeApp({ uploadsPerHour: 2 });
    const from = (ip) =>
      app.request("/api/analyses", { ...upload({}), headers: { "x-forwarded-for": ip } });

    expect((await from("10.0.0.1")).status).toBe(202);
    expect((await from("10.0.0.1")).status).toBe(202);
    expect((await from("10.0.0.1")).status).toBe(429);
    expect((await from("10.0.0.2")).status).toBe(202);
  });

  test("the refusal is the error envelope, like every other one", async () => {
    // The library answers plain text by default, which the client would
    // surface as INTERNAL_ERROR.
    const { app } = await makeApp({ uploadsPerHour: 1 });
    await app.request("/api/analyses", upload({}));
    const refused = await app.request("/api/analyses", upload({}));

    expect(refused.status).toBe(429);
    expect(refused.headers.get("content-type")).toStartWith("application/json");
    expect(await refused.json()).toEqual({ code: "RATE_LIMITED", message: "rate_limited" });
  });

  test("the leftmost forwarded address is the client, not the last proxy", async () => {
    const { app } = await makeApp({ uploadsPerHour: 1 });
    const chain = (first) => ({
      ...upload({}),
      headers: { "x-forwarded-for": `${first}, 10.9.9.9, 10.9.9.10` },
    });

    expect((await app.request("/api/analyses", chain("203.0.113.5"))).status).toBe(202);
    // Proxies append on the right, so reading the last entry would count
    // every user as one.
    expect((await app.request("/api/analyses", chain("203.0.113.6"))).status).toBe(202);
    expect((await app.request("/api/analyses", chain("203.0.113.6"))).status).toBe(429);
  });
});

describe("the queue is checked before the body is read", () => {
  test("a full queue answers SERVICE_AT_CAPACITY and reads nothing", async () => {
    const runner = fakeRunner({ delayMs: 200 });
    const { app } = await makeApp({ runner, maxQueueDepth: 1 });

    await post(app, {}); // starts running
    await Bun.sleep(5);
    await post(app, {}); // fills the single waiting slot
    const refused = await post(app, {});

    expect(refused.status).toBe(503);
    expect((await refused.json()).code).toBe("SERVICE_AT_CAPACITY");
  });
});
