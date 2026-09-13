import assert from "node:assert/strict";
import { test } from "node:test";
import { canRevamp, screenshotCount, revampInProgress } from "../src/revamp.ts";
import { ApiError, apiAssetUrl, request } from "../src/api.ts";

const run = {
  id: "real-run", status: "completed", results: {
    first: { steps: [{ screenshot_url: "/original/1" }, { screenshot_url: null }] },
    second: { steps: [{ screenshot_url: "https://example.com/2.png" }] },
  },
};

test("improvements cover screenshots across the whole finished run", () => {
  assert.equal(screenshotCount(run), 2);
  assert.equal(canRevamp(run), true);
  assert.equal(canRevamp({ ...run, status: "failed" }), true);
  for (const status of ["created", "running"]) assert.equal(canRevamp({ ...run, status }), false);
  assert.equal(canRevamp({ ...run, id: "demo-1" }), false);
  assert.equal(canRevamp({ ...run, results: {} }), false);
});

test("polling stops for completed, partial, and failed revamps", () => {
  for (const status of ["created", "running"]) assert.equal(revampInProgress({ status }), true);
  for (const status of ["completed", "partial", "failed"]) assert.equal(revampInProgress({ status }), false);
});

test("original and generated image URLs support API paths and full URLs", () => {
  assert.equal(apiAssetUrl("/runs/id/screenshot"), "/api/runs/id/screenshot");
  assert.equal(apiAssetUrl("runs/id/screenshot-fixed"), "/api/runs/id/screenshot-fixed");
  assert.equal(apiAssetUrl("https://example.com/screenshot.png"), "https://example.com/screenshot.png");
});

test("API errors preserve the difference between absent improvements and an expired run", async (t) => {
  for (const detail of ["Revamp not found", "Run not found"]) {
    t.mock.method(globalThis, "fetch", async () => new Response(JSON.stringify({ detail }), { status: 404 }));
    await assert.rejects(request("/runs/id/revamp"), (error) => error instanceof ApiError && error.status === 404 && error.message === detail);
    t.mock.restoreAll();
  }
});
