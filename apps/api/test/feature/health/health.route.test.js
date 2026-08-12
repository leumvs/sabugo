import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import { rm } from "node:fs/promises";
import { makeApp } from "../../helpers";

let clientDist;
let app;

beforeAll(async () => {
  ({ app, clientDist } = await makeApp());
});

afterAll(async () => {
  await rm(clientDist, { recursive: true, force: true });
});

describe("GET /api/health", () => {
  test("returns ok", async () => {
    const res = await app.request("/api/health");

    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ status: "ok" });
  });
});

describe("unknown /api route", () => {
  test("returns JSON 404, never the SPA fallback", async () => {
    const res = await app.request("/api/nope");

    expect(res.status).toBe(404);
    expect(res.headers.get("content-type")).toContain("application/json");

    const body = await res.json();
    expect(body.code).toBe("NOT_FOUND");
    expect(typeof body.message).toBe("string");
  });
});

describe("error page", () => {
  test("serves the branded 404 page outside /api", async () => {
    const res = await app.request("/any/path");
    const body = await res.text();

    expect(res.status).toBe(404);
    expect(res.headers.get("content-type")).toContain("text/html");
    expect(body).toContain("404");
    expect(body).toContain("Sabugo");
  });
});

describe("OpenAPI document", () => {
  // Generated from the sub-app instead of the root app, the paths come out
  // without the `/api` prefix and 404 for whoever follows them.
  test("every documented path actually responds", async () => {
    const res = await app.request("/api/openapi.json");
    expect(res.headers.get("content-type")).toContain("application/json");

    const doc = await res.json();
    const paths = Object.keys(doc.paths ?? {});

    expect(paths.length).toBeGreaterThan(0);

    for (const path of paths) {
      // 404 from the handler is fine; 404 from the router is what this looks
      // for, and only that reaches the SPA fallback and returns HTML.
      const res = await app.request(path.replaceAll(/\{[^}]+\}/g, "does-not-exist"));
      expect(res.headers.get("content-type"), `documented path ${path}`).not.toContain("text/html");
    }
  });

  test("all four routes are documented", async () => {
    const doc = await (await app.request("/api/openapi.json")).json();

    expect(Object.keys(doc.paths).sort()).toEqual([
      "/api/analyses",
      "/api/analyses/{id}/events",
      "/api/analyses/{id}/export",
      "/api/health",
    ]);
  });

  test("every documented path carries the /api prefix", async () => {
    const doc = await (await app.request("/api/openapi.json")).json();

    for (const path of Object.keys(doc.paths)) {
      expect(path.startsWith("/api/")).toBe(true);
    }
  });
});
