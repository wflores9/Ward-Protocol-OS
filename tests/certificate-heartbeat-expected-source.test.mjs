// Regression tests for the Sep 27 2026 "expected 1, observed 3" watchdog alert.
// Root cause: EXPECTED_CERTIFICATE_COUNT="1" was a hand-set constant in
// wrangler.certificate-heartbeat.jsonc (commit 79f2442, 2026-08-24) that was
// never updated when certificate-index.json grew from 1 to 3 certificates.
// These tests pin the corrected behaviour. They never suppress an alert.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  deriveExpectedCertificates,
  evaluateCertificateStatus,
} from "../workers/certificate-heartbeat-core.mjs";
import { runHeartbeat } from "../workers/certificate-heartbeat.mjs";

const FIX = new URL("./fixtures/certificate-heartbeat/", import.meta.url);
const load = (name) => JSON.parse(readFileSync(new URL(name, FIX), "utf8"));

// Real committed data, copied byte-for-byte from git (see fixtures/*).
const INDEX3 = load("certificate-index-5ca3838.json");
const STATUS_0921 = load("status-2026-09-21T1328Z-41f34b6.json"); // the alert's "source generated" value
const STATUS_0928 = load("status-2026-09-28T1332Z-5ca3838.json");

const ALERT_TIME = Date.parse("2026-09-27T14:23:00Z"); // daily cron "23 14 * * *"
// 2026-09-21T13:28:16Z + 8 days (691200 s) = 2026-09-29T13:28:16Z (09:28:16 ET). Use a time after that.
const NOW_0929 = Date.parse("2026-09-29T14:00:00Z");
const EIGHT_DAYS_S = 691200;
const MAX_AGE_MS = EIGHT_DAYS_S * 1000;
const IDS = [
  "KV-IV-2026-0712-001",
  "WARD-DEVNET-20260901-001",
  "WARD-DEVNET-20260902-001",
];

const clone = (value) => JSON.parse(JSON.stringify(value));
const evaluate = (payload, index, nowMs = NOW_0929, extra = {}) =>
  evaluateCertificateStatus(payload, { nowMs, maxAgeMs: MAX_AGE_MS, index, ...extra });

function environment(index, statusPayload, { maxAge = String(EIGHT_DAYS_S) } = {}) {
  const entries = new Map();
  return {
    entries,
    env: {
      HEARTBEAT_STATE: {
        async get(key, format) {
          const value = entries.get(key);
          return format === "json" && value ? JSON.parse(value) : value ?? null;
        },
        async put(key, value) {
          entries.set(key, value);
        },
      },
      STATUS_URL: "https://example.test/certificate-reproducibility-status.json",
      INDEX_URL: "https://example.test/certificate-index.json",
      MAX_STATUS_AGE_SECONDS: maxAge,
      ALERT_FROM: "Ward Protocol <team@wardprotocol.org>",
      ALERT_TO: "team@wardprotocol.org",
      // v4: runHeartbeat is strict (pin enforced, bootstrap never healthy). These approved tests predate the pin and
      // assert the pre-pin behaviour, so they opt in to a TEST-ONLY legacy evaluator seam that production entry points
      // shadow to false. Their assertions are unchanged; strict behaviour is in certificate-heartbeat-strict.test.mjs.
      __TEST_ONLY_LEGACY_EVALUATOR: Symbol.for("ward.test-only.legacy-evaluator"),
      // No RESEND_API_KEY: an alert must fail visibly, never silently pass.
      __fetch: async (url) =>
        String(url).includes("index") ? Response.json(index) : Response.json(statusPayload),
    },
  };
}

async function withFetch(t, handler) {
  const original = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = original;
  });
  globalThis.fetch = handler;
}

// ---------------------------------------------------------------------------
// 1. Expected is derived from a single source of truth, not hard-coded.
// ---------------------------------------------------------------------------
test("expected set is derived from the certificate index, and equals the real three ids", () => {
  const { ids, problems } = deriveExpectedCertificates(INDEX3);
  assert.deepEqual(problems, []);
  assert.deepEqual(ids, IDS);
});

test("with the real index, the real 2026-09-28 status is consistent (count 3 == index 3)", () => {
  const result = evaluate(STATUS_0928, INDEX3);
  assert.deepEqual(result.reasons, []);
  assert.equal(result.expectedCertificateCount, 3);
  assert.equal(result.certificateCount, 3);
});

test("changing the index changes what is expected (no constant anywhere)", () => {
  const four = clone(INDEX3);
  four.certificates.push({ certificate_id: "WARD-DEVNET-20261001-001" });
  const result = evaluate(STATUS_0928, four);
  assert.equal(result.healthy, false);
  assert.match(result.reasons.join("\n"), /certificate count mismatch: expected 4, found 3/);
  assert.match(result.reasons.join("\n"), /summary total mismatch: expected 4, found 3/);
  assert.match(result.reasons.join("\n"), /missing from status: WARD-DEVNET-20261001-001/);
});

test("a caller-supplied expectedCertificateCount option is ignored", () => {
  const result = evaluate(STATUS_0928, INDEX3, NOW_0929, { expectedCertificateCount: 1 });
  assert.deepEqual(result.reasons, []);
  assert.equal(result.expectedCertificateCount, 3);
});

test("neither worker source nor wrangler config contains EXPECTED_CERTIFICATE_COUNT any more", () => {
  for (const rel of [
    "../workers/certificate-heartbeat.mjs",
    "../workers/certificate-heartbeat-core.mjs",
    "../wrangler.certificate-heartbeat.jsonc",
  ]) {
    const text = readFileSync(new URL(rel, import.meta.url), "utf8");
    assert.doesNotMatch(text, /EXPECTED_CERTIFICATE_COUNT/, rel);
  }
});

// ---------------------------------------------------------------------------
// 2. A real count mismatch still alerts.
// ---------------------------------------------------------------------------
test("status missing a certificate that the index lists alerts", () => {
  const short = clone(STATUS_0928);
  short.certificates.pop();
  short.summary = { total: 2, reproducible: 1, unreproducible: 1, check_error: 0 };
  const result = evaluate(short, INDEX3);
  assert.equal(result.healthy, false);
  assert.match(result.reasons.join("\n"), /certificate count mismatch: expected 3, found 2/);
  assert.match(result.reasons.join("\n"), /summary total mismatch: expected 3, found 2/);
});

test("status with an extra certificate that the index does not list alerts", () => {
  const extra = clone(STATUS_0928);
  extra.certificates.push({ ...clone(extra.certificates[0]), certificate_id: "UNINDEXED-001" });
  extra.summary = { total: 4, reproducible: 1, unreproducible: 3, check_error: 0 };
  const result = evaluate(extra, INDEX3);
  assert.equal(result.healthy, false);
  assert.match(result.reasons.join("\n"), /expected 3, found 4/);
  assert.match(result.reasons.join("\n"), /not in index: UNINDEXED-001/);
});

test("same count but a different certificate id alerts (swap is not hidden)", () => {
  const swapped = clone(STATUS_0928);
  swapped.certificates[2].certificate_id = "WARD-DEVNET-20260902-999";
  const result = evaluate(swapped, INDEX3);
  assert.equal(result.healthy, false);
  assert.match(result.reasons.join("\n"), /missing from status: WARD-DEVNET-20260902-001/);
  assert.match(result.reasons.join("\n"), /not in index: WARD-DEVNET-20260902-999/);
});

test("the ORIGINAL alert is reproduced by an index that says 1 (mismatch is not suppressed)", () => {
  const oldIndex = { schema: "ward-certificate-index/v1", certificates: [{ certificate_id: IDS[0] }] };
  const result = evaluate(STATUS_0921, oldIndex, ALERT_TIME);
  assert.equal(result.healthy, false);
  assert.match(result.reasons.join("\n"), /certificate count mismatch: expected 1, found 3/);
  assert.match(result.reasons.join("\n"), /summary total mismatch: expected 1, found 3/);
});

test("summary.total that disagrees with certificates[] length alerts", () => {
  const bad = clone(STATUS_0928);
  bad.summary.total = 2;
  bad.summary.unreproducible = 1;
  const result = evaluate(bad, INDEX3);
  assert.equal(result.healthy, false);
  assert.match(result.reasons.join("\n"), /summary total mismatch: expected 3, found 2/);
  assert.match(result.reasons.join("\n"), /does not match certificates length 3/);
});

// ---------------------------------------------------------------------------
// 3. Stale source is flagged, not trusted.
// ---------------------------------------------------------------------------
test("the 2026-09-21 source is NOT stale at alert time (6d < 8d), but IS stale after 2026-09-29T13:28:16Z", () => {
  const atAlert = evaluate(STATUS_0921, INDEX3, ALERT_TIME);
  assert.deepEqual(atAlert.reasons, []);
  // One second before the 8-day threshold it is still accepted; one second after it is stale.
  const generated = Date.parse("2026-09-21T13:28:16.665717Z");
  assert.deepEqual(evaluate(STATUS_0921, INDEX3, generated + MAX_AGE_MS).reasons.filter((r) => /stale by/.test(r)), []);
  assert.match(evaluate(STATUS_0921, INDEX3, generated + MAX_AGE_MS + 1000).reasons.join("\n"), /status is stale by/);
  const today = evaluate(STATUS_0921, INDEX3, NOW_0929);
  assert.equal(today.healthy, false);
  assert.match(today.reasons.join("\n"), /status is stale by \d+ seconds/);
  assert.match(today.reasons.join("\n"), /WARD-DEVNET-20260902-001 check result is stale/);
});

test("a missing or non-numeric MAX_STATUS_AGE_SECONDS fails closed instead of disabling staleness", () => {
  const nan = evaluateCertificateStatus(STATUS_0921, {
    nowMs: NOW_0929,
    maxAgeMs: Number(undefined),
    index: INDEX3,
  });
  assert.equal(nan.healthy, false);
  assert.match(nan.reasons.join("\n"), /MAX_STATUS_AGE_SECONDS is missing or invalid/);
});

test("heartbeat run with a stale source ends in alert state and does not send a green result", async (t) => {
  await withFetch(t, async (url) =>
    String(url).includes("index") ? Response.json(INDEX3) : Response.json(STATUS_0921),
  );
  const { env, entries } = environment(INDEX3, STATUS_0921);
  await assert.rejects(() => runHeartbeat(env, new Date(NOW_0929)), /RESEND_API_KEY/);
  const stored = JSON.parse(entries.get("certificate-heartbeat-state"));
  assert.equal(stored.state, "alert");
  assert.match(stored.reasons.join("\n"), /status is stale/);
});

// ---------------------------------------------------------------------------
// 4. Discovery counts exactly the certificate set.
// ---------------------------------------------------------------------------
test("index discovery counts exactly the indexed certificates: no more, no fewer", () => {
  assert.equal(deriveExpectedCertificates(INDEX3).ids.length, INDEX3.certificates.length);
  assert.equal(new Set(deriveExpectedCertificates(INDEX3).ids).size, 3);
});

test("duplicate ids in the index are reported, not silently collapsed", () => {
  const dup = clone(INDEX3);
  dup.certificates.push({ certificate_id: IDS[1] });
  const { ids, problems } = deriveExpectedCertificates(dup);
  assert.equal(ids.length, 3);
  assert.match(problems.join("\n"), /duplicate certificate_id: WARD-DEVNET-20260901-001/);
  assert.equal(evaluate(STATUS_0928, dup).healthy, false);
});

test("an index entry with no certificate_id is reported", () => {
  const bad = clone(INDEX3);
  bad.certificates.push({ title: "no id" });
  assert.equal(evaluate(STATUS_0928, bad).healthy, false);
});

test("wrong or missing index schema and non-array certificates fail closed", () => {
  assert.equal(evaluate(STATUS_0928, { schema: "x", certificates: [] }).healthy, false);
  assert.equal(evaluate(STATUS_0928, { schema: "ward-certificate-index/v1" }).healthy, false);
  assert.equal(evaluate(STATUS_0928, null).healthy, false);
});

test("the Aug 24 evidence run is not a certificate and is not counted", () => {
  const ids = deriveExpectedCertificates(INDEX3).ids;
  assert.equal(ids.some((id) => id.includes("20260824")), false);
});

test("index unreachable fails closed: no expected value is invented", async (t) => {
  await withFetch(t, async (url) =>
    String(url).includes("index")
      ? new Response("nope", { status: 503 })
      : Response.json(STATUS_0928),
  );
  const { env, entries } = environment(null, STATUS_0928);
  await assert.rejects(() => runHeartbeat(env, new Date(NOW_0929)), /RESEND_API_KEY/);
  const stored = JSON.parse(entries.get("certificate-heartbeat-state"));
  assert.equal(stored.state, "alert");
  assert.equal(stored.expected_certificate_count, null);
  assert.match(stored.reasons.join("\n"), /certificate index unavailable: certificate index returned HTTP 503/);
});

// ---------------------------------------------------------------------------
// 5. No path sets expected = observed automatically.
// ---------------------------------------------------------------------------
test("a status file cannot redefine the expectation by changing its own summary or list", () => {
  const forged = clone(STATUS_0928);
  forged.certificates = forged.certificates.slice(0, 1);
  forged.summary = { total: 1, reproducible: 0, unreproducible: 1, check_error: 0 };
  const result = evaluate(forged, INDEX3);
  assert.equal(result.healthy, false);
  assert.equal(result.expectedCertificateCount, 3);
});

test("the expectation is recomputed on every run from a fresh index fetch (no cached copy in KV)", async (t) => {
  const indexes = [INDEX3, { schema: "ward-certificate-index/v1", certificates: [{ certificate_id: IDS[0] }] }];
  let call = 0;
  await withFetch(t, async (url) => {
    if (String(url).includes("index")) return Response.json(indexes[call++ > 0 ? 1 : 0]);
    return Response.json(STATUS_0928);
  });
  const first = environment(INDEX3, STATUS_0928);
  const s1 = await runHeartbeat(first.env, new Date(NOW_0929));
  assert.equal(s1.state, "healthy");
  assert.equal(s1.expected_certificate_count, 3);
  // Same KV, index now lists 1: the very next run must alert rather than reuse "3".
  await assert.rejects(() => runHeartbeat(first.env, new Date(NOW_0929 + 60_000)), /RESEND_API_KEY/);
  const s2 = JSON.parse(first.entries.get("certificate-heartbeat-state"));
  assert.equal(s2.state, "alert");
  assert.equal(s2.expected_certificate_count, 1);
});

test("no code path assigns the observed count or summary total to the expected value", () => {
  for (const rel of ["../workers/certificate-heartbeat.mjs", "../workers/certificate-heartbeat-core.mjs"]) {
    const text = readFileSync(new URL(rel, import.meta.url), "utf8");
    assert.doesNotMatch(text, /expectedCertificateCount\s*=\s*(certificates|summary|payload)/, rel);
    assert.doesNotMatch(text, /expected_certificate_count\s*[:=]\s*(evaluation\.certificateCount|state\.certificate_count)/, rel);
  }
});

test("a certificate that disappears from the index between runs is reported, not silently re-baselined", async (t) => {
  const shrunk = { schema: "ward-certificate-index/v1", certificates: INDEX3.certificates.slice(0, 2) };
  const statusTwo = clone(STATUS_0928);
  statusTwo.certificates.pop();
  statusTwo.summary = { total: 2, reproducible: 1, unreproducible: 1, check_error: 0 };
  let call = 0;
  await withFetch(t, async (url) => {
    if (String(url).includes("index")) return Response.json(call++ === 0 ? INDEX3 : shrunk);
    return Response.json(call === 1 ? STATUS_0928 : statusTwo);
  });
  const { env, entries } = environment(INDEX3, STATUS_0928);
  assert.equal((await runHeartbeat(env, new Date(NOW_0929))).state, "healthy");
  // Index and status now agree on 2 certificates, but the removal itself must still alert.
  await assert.rejects(() => runHeartbeat(env, new Date(NOW_0929 + 60_000)), /RESEND_API_KEY/);
  const stored = JSON.parse(entries.get("certificate-heartbeat-state"));
  assert.equal(stored.state, "alert");
  assert.match(stored.reasons.join("\n"), /certificate removed from index since last check: WARD-DEVNET-20260902-001/);
  // A third run must STILL alert: the baseline does not advance on an unhealthy run.
  await assert.rejects(() => runHeartbeat(env, new Date(NOW_0929 + 2 * 24 * 3600_000)), /RESEND_API_KEY/);
  const again = JSON.parse(entries.get("certificate-heartbeat-state"));
  assert.equal(again.state, "alert");
  assert.deepEqual(again.last_known_index_ids, IDS);
});

test("last-known index ids survive a failed index fetch", async (t) => {
  let call = 0;
  await withFetch(t, async (url) => {
    if (String(url).includes("index")) return call++ === 0 ? Response.json(INDEX3) : new Response("x", { status: 500 });
    return Response.json(STATUS_0928);
  });
  const { env, entries } = environment(INDEX3, STATUS_0928);
  await runHeartbeat(env, new Date(NOW_0929));
  await assert.rejects(() => runHeartbeat(env, new Date(NOW_0929 + 60_000)), /RESEND_API_KEY/);
  assert.deepEqual(JSON.parse(entries.get("certificate-heartbeat-state")).last_known_index_ids, IDS);
});

// ---------------------------------------------------------------------------
// 6. ward_signed = false is preserved.
// ---------------------------------------------------------------------------
test("heartbeat state and alert text carry ward_signed=false and never true", async (t) => {
  let sentBody = null;
  await withFetch(t, async (url, init) => {
    if (String(url).includes("api.resend.com")) {
      sentBody = JSON.parse(init.body);
      return Response.json({ id: "test" });
    }
    return String(url).includes("index") ? Response.json(INDEX3) : Response.json(STATUS_0921);
  });
  const { env, entries } = environment(INDEX3, STATUS_0921);
  env.RESEND_API_KEY = "test-only-not-a-secret";
  const state = await runHeartbeat(env, new Date(NOW_0929));
  assert.equal(state.ward_signed, false);
  assert.equal(JSON.parse(entries.get("certificate-heartbeat-state")).ward_signed, false);
  assert.match(sentBody.text, /ward_signed = False — always\./);
  assert.match(sentBody.text, /Certificates expected \(derived from/);
  assert.equal(state.notification, "alert_sent");
});

test("healthy state also carries ward_signed=false", async (t) => {
  await withFetch(t, async (url) =>
    String(url).includes("index") ? Response.json(INDEX3) : Response.json(STATUS_0928),
  );
  const { env } = environment(INDEX3, STATUS_0928);
  const state = await runHeartbeat(env, new Date(NOW_0929));
  assert.equal(state.state, "healthy");
  assert.equal(state.ward_signed, false);
});

test("the fixtures themselves never claim ward_signed true", () => {
  for (const file of [INDEX3, STATUS_0921, STATUS_0928]) {
    assert.doesNotMatch(JSON.stringify(file), /"ward_signed":\s*true/);
  }
});
