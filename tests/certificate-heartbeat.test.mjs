import assert from "node:assert/strict";
import test from "node:test";

import { evaluateCertificateStatus } from "../workers/certificate-heartbeat-core.mjs";
import { runHeartbeat } from "../workers/certificate-heartbeat.mjs";

const NOW = Date.parse("2026-08-24T15:00:00Z");

function status(overrides = {}) {
  return {
    schema: "ward-certificate-reproducibility-status/v1",
    generated_at: "2026-08-24T14:00:00Z",
    summary: { total: 1, reproducible: 0, unreproducible: 1, check_error: 0 },
    certificates: [
      {
        certificate_id: "KV-IV-2026-0712-001",
        checked_at: "2026-08-24T14:00:00Z",
        status: "unreproducible",
        error_code: "lgrNotFound",
      },
    ],
    ...overrides,
  };
}

function environment() {
  const entries = new Map();
  return {
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
      STATUS_URL: "https://example.test/status.json",
      MAX_STATUS_AGE_SECONDS: "691200",
      EXPECTED_CERTIFICATE_COUNT: "1",
      ALERT_FROM: "Ward Protocol <team@wardprotocol.org>",
      ALERT_TO: "team@wardprotocol.org",
    },
    entries,
  };
}

test("treats a fresh unreproducible certificate result as a healthy monitor run", () => {
  const result = evaluateCertificateStatus(status(), { nowMs: NOW, expectedCertificateCount: 1 });
  assert.equal(result.healthy, true);
  assert.deepEqual(result.reasons, []);
});

test("fails closed when the weekly status is stale", () => {
  const result = evaluateCertificateStatus(
    status({ generated_at: "2026-08-01T00:00:00Z" }),
    { nowMs: NOW, expectedCertificateCount: 1 },
  );
  assert.equal(result.healthy, false);
  assert.match(result.reasons.join("\n"), /status is stale/);
});

test("fails closed when a certificate disappears", () => {
  const result = evaluateCertificateStatus(
    status({
      summary: { total: 0, reproducible: 0, unreproducible: 0, check_error: 0 },
      certificates: [],
    }),
    { nowMs: NOW, expectedCertificateCount: 1 },
  );
  assert.equal(result.healthy, false);
  assert.match(result.reasons.join("\n"), /certificate count mismatch/);
});

test("fails closed on a check_error result", () => {
  const payload = status();
  payload.summary = { total: 1, reproducible: 0, unreproducible: 0, check_error: 1 };
  payload.certificates[0].status = "check_error";
  const result = evaluateCertificateStatus(payload, { nowMs: NOW, expectedCertificateCount: 1 });
  assert.equal(result.healthy, false);
  assert.match(result.reasons.join("\n"), /check_error/);
});

test("rejects a future timestamp instead of treating it as fresh", () => {
  const result = evaluateCertificateStatus(
    status({ generated_at: "2026-08-25T00:00:00Z" }),
    { nowMs: NOW, expectedCertificateCount: 1 },
  );
  assert.equal(result.healthy, false);
  assert.match(result.reasons.join("\n"), /future/);
});

test("scheduled heartbeat records a healthy public result", async (t) => {
  const originalFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = originalFetch;
  });
  globalThis.fetch = async () => Response.json(status());
  const { env, entries } = environment();

  const result = await runHeartbeat(env, new Date(NOW));

  assert.equal(result.state, "healthy");
  assert.equal(result.notification, "not_required");
  assert.equal(JSON.parse(entries.get("certificate-heartbeat-state")).state, "healthy");
});

test("scheduled heartbeat fails visibly when alert transport is unconfigured", async (t) => {
  const originalFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = originalFetch;
  });
  globalThis.fetch = async () =>
    Response.json(status({ generated_at: "2026-08-01T00:00:00Z" }));
  const { env, entries } = environment();

  await assert.rejects(() => runHeartbeat(env, new Date(NOW)), /RESEND_API_KEY/);

  const stored = JSON.parse(entries.get("certificate-heartbeat-state"));
  assert.equal(stored.state, "alert");
  assert.equal(stored.notification, "send_failed");
});
