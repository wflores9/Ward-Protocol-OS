import assert from "node:assert/strict";
import test from "node:test";

import { evaluateCertificateStatus } from "../workers/certificate-heartbeat-core.mjs";

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
