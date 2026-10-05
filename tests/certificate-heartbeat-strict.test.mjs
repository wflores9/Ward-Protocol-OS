// Strict (pinned) watchdog behaviour. The approved 34 tests are untouched; these add the
// fail-closed cases a review found open. A status document is never its own authority.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  LEGACY_DECLARED,
  computeExpectedSetPin,
  evaluateCertificateStatusStrict,
} from "../workers/certificate-heartbeat-core.mjs";
import { LEGACY_TEST_SEAM, runHeartbeat } from "../workers/certificate-heartbeat.mjs";

const FIX = new URL("./fixtures/certificate-heartbeat/", import.meta.url);
const load = (n) => JSON.parse(readFileSync(new URL(n, FIX), "utf8"));
const INDEX3 = load("certificate-index-5ca3838.json");
const STATUS = load("status-2026-09-28T1332Z-5ca3838.json");
const NOW = Date.parse("2026-09-29T09:00:00Z"); // 27h20m after the status: inside the 8 d window
const MAX = 691200 * 1000;
const clone = (v) => JSON.parse(JSON.stringify(v));
const PIN = await computeExpectedSetPin(INDEX3);
const SIX = STATUS.certificates.map((c) => c.certificate_id);

// The committed status lacks raw_reads_archive.sha256 for the reproducible entry; a real archive
// checker output carries it. Strict mode compares it to the pin, so fixtures add the pinned hashes.
function goodStatus() {
  const s = clone(STATUS);
  const arch = new Map(INDEX3.certificates.map((c) => [c.certificate_id, c.raw_reads_archive?.sha256]));
  // make the two September certificates reproducible, KV legacy unreproducible
  for (const c of s.certificates) {
    if (c.certificate_id.startsWith("WARD-")) {
      c.status = "reproducible";
      c.error_code = null;
      c.raw_reads_archive = { sha256: arch.get(c.certificate_id) };
    }
  }
  // v5: the legacy certificate carries its DECLARED result (what the patched checker writes), not the
  // older lgrNotFound wording of the 5ca3838 status file.
  const kv = s.certificates.find((c) => c.certificate_id === "KV-IV-2026-0712-001");
  kv.error_code = "missing_raw_reads_archive"; kv.reproducibility_label = "unreproducible/legacy"; kv.raw_reads_archive = null; kv.legacy = true;
  s.summary = { total: 3, reproducible: 2, unreproducible: 1, check_error: 0 };
  return s;
}
const ev = (payload, o = {}) =>
  evaluateCertificateStatusStrict(payload, { nowMs: NOW, maxAgeMs: MAX, index: INDEX3, expectedSetPin: PIN, ...o });
const bad = async (payload, re, o) => {
  const r = await ev(payload, o);
  assert.equal(r.healthy, false, "must fail closed");
  assert.match(r.reasons.join("\n"), re);
  return r;
};

test("baseline: pinned index + consistent status is healthy and authoritative", async () => {
  const r = await ev(goodStatus());
  assert.deepEqual(r.reasons, []);
  assert.equal(r.healthy, true);
  assert.equal(r.pinStatus, "PINNED");
  assert.equal(r.authoritative, true);
});

test("the pin is derived from ids, expected states and archive hashes, and is stable", async () => {
  assert.match(PIN, /^wes1:3:[0-9a-f]{64}$/);
  assert.equal(await computeExpectedSetPin(clone(INDEX3)), PIN);
});

test("no pin configured: fails closed with a hint instead of healthy (first run / no baseline)", async () => {
  await bad(goodStatus(), /EXPECTED_SET_PIN is missing/, { expectedSetPin: undefined });
  await bad(goodStatus(), /EXPECTED_SET_PIN is missing/, { expectedSetPin: "" });
  await bad(goodStatus(), /EXPECTED_SET_PIN is missing/, { expectedSetPin: "   " });
  await bad(goodStatus(), /EXPECTED_SET_PIN is malformed/, { expectedSetPin: "wes1:3:nothex" });
});

test("v4: bootstrap mode WITHOUT a pin is never healthy and never authoritative", async () => {
  const r = await ev(goodStatus(), { expectedSetPin: undefined, mode: "bootstrap-unpinned" });
  assert.equal(r.healthy, false);
  assert.equal(r.pinStatus, "BOOTSTRAP_UNPINNED");
  assert.equal(r.authoritative, false);
  assert.match(r.reasons.join("\n"), /bootstrap mode .* never reported healthy/);
});

test("empty index + empty status is never healthy (bootstrap or pinned)", async () => {
  const idx = { schema: "ward-certificate-index/v1", certificates: [] };
  const st = { ...goodStatus(), certificates: [], summary: { total: 0, reproducible: 0, unreproducible: 0, check_error: 0 } };
  await bad(st, /empty/, { index: idx, mode: "bootstrap-unpinned", expectedSetPin: undefined });
  await bad(st, /empty/, { index: idx, mode: "bootstrap-unpinned" }); // with a (now mismatching) pin too
  await bad(st, /empty/, { index: idx });
  await assert.rejects(() => computeExpectedSetPin(idx), /empty/);
});

test("coordinated shrink of index AND status does not match the out-of-band pin", async () => {
  const idx = clone(INDEX3);
  idx.certificates = idx.certificates.slice(0, 2);
  const st = goodStatus();
  st.certificates = st.certificates.slice(0, 2);
  st.summary = { total: 2, reproducible: 1, unreproducible: 1, check_error: 0 };
  await bad(st, /does not match the out-of-band expected-set pin/, { index: idx });
});

test("coordinated same-count id swap of index AND status does not match the pin", async () => {
  const idx = clone(INDEX3);
  idx.certificates[2].certificate_id = "WARD-DEVNET-20260999-001";
  const st = goodStatus();
  st.certificates[2].certificate_id = "WARD-DEVNET-20260999-001";
  await bad(st, /does not match the out-of-band expected-set pin/, { index: idx });
});

test("a re-pinned archive hash in the index does not match the pin", async () => {
  const idx = clone(INDEX3);
  idx.certificates[1].raw_reads_archive.sha256 = "0".repeat(64);
  await bad(goodStatus(), /does not match the out-of-band expected-set pin/, { index: idx });
});

test("forged, well-shaped status: a pinned-reproducible certificate reported unreproducible is caught", async () => {
  const st = goodStatus();
  st.certificates[1].status = "unreproducible";
  st.summary = { total: 3, reproducible: 1, unreproducible: 2, check_error: 0 };
  await bad(st, /pinned reproducible but the status reports unreproducible/);
});

test("forged status with a different archive hash is caught against the pin", async () => {
  const st = goodStatus();
  st.certificates[1].raw_reads_archive = { sha256: "f".repeat(64) };
  await bad(st, /archive sha256 in the status .* differs from the pinned value/);
});

test("forged status that omits the archive hash for a pinned-reproducible certificate is caught", async () => {
  const st = goodStatus();
  delete st.certificates[1].raw_reads_archive;
  await bad(st, /archive sha256 in the status \(absent\)/);
});

test("legacy certificate reported reproducible is caught (never relabelled)", async () => {
  const st = goodStatus();
  st.certificates[0].status = "reproducible";
  st.summary = { total: 3, reproducible: 3, unreproducible: 0, check_error: 0 };
  await bad(st, /pinned legacy\/unreproducible but the status reports reproducible/);
});

test("ward_signed=true anywhere in the status is rejected", async () => {
  await bad({ ...goodStatus(), ward_signed: true }, /ward_signed=true/);
  const st = goodStatus();
  st.certificates[0].ward_signed = true;
  await bad(st, /claims ward_signed=true/);
});

test("summary.reproducible must match the entries (both directions)", async () => {
  const inflated = goodStatus();
  inflated.summary = { total: 3, reproducible: 3, unreproducible: 0, check_error: 0 };
  await bad(inflated, /summary.reproducible 3 does not match the entries \(2\)/);
  const deflated = goodStatus();
  deflated.certificates.forEach((c) => { c.status = "unreproducible"; c.raw_reads_archive = null; });
  deflated.summary = { total: 3, reproducible: 0, unreproducible: 3, check_error: 0 };
  await bad(deflated, /pinned reproducible but the status reports unreproducible/);
  const lie = goodStatus();
  lie.summary = { total: 3, reproducible: 1, unreproducible: 2, check_error: 0 };
  await bad(lie, /summary.reproducible 1 does not match the entries \(2\)/);
});

test("certificate removal from index and from status is reported", async () => {
  const idx = clone(INDEX3);
  idx.certificates.pop();
  const st = goodStatus();
  st.certificates.pop();
  st.summary = { total: 2, reproducible: 1, unreproducible: 1, check_error: 0 };
  await bad(st, /removed from index since last check: WARD-DEVNET-20260902-001/, { index: idx, previousIndexIds: SIX });
});

test("future timestamps are not fresh: generated_at and per-certificate checked_at", async () => {
  await bad({ ...goodStatus(), generated_at: "2099-01-01T00:00:00Z" }, /future/);
  const st = goodStatus();
  st.certificates[0].checked_at = "2099-01-01T00:00:00Z";
  await bad(st, /checked_at is more than five minutes in the future/);
});

test("invalid timestamps fail closed", async () => {
  await bad({ ...goodStatus(), generated_at: "not-a-date" }, /generated_at/);
  const st = goodStatus();
  st.certificates[1].checked_at = "garbage";
  await bad(st, /checked_at/);
});

test("unavailable authoritative source: index or status fetch failure is an alert, not a pass", async (t) => {
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  const entries = new Map();
  const env = {
    HEARTBEAT_STATE: { async get(k, f) { const v = entries.get(k); return f === "json" && v ? JSON.parse(v) : v ?? null; }, async put(k, v) { entries.set(k, v); } },
    STATUS_URL: "https://example.test/status.json", INDEX_URL: "https://example.test/certificate-index.json",
    MAX_STATUS_AGE_SECONDS: "691200", EXPECTED_SET_PIN: PIN,
    ALERT_FROM: "Ward Protocol <team@wardprotocol.org>", ALERT_TO: "team@wardprotocol.org",
  };
  globalThis.fetch = async (url) => (String(url).includes("index") ? new Response("down", { status: 503 }) : Response.json(goodStatus()));
  await assert.rejects(() => runHeartbeat(env, new Date(NOW)), /RESEND_API_KEY/);
  assert.equal(JSON.parse(entries.get("certificate-heartbeat-state")).state, "alert");
  globalThis.fetch = async (url) => (String(url).includes("index") ? Response.json(INDEX3) : new Response("down", { status: 500 }));
  await assert.rejects(() => runHeartbeat(env, new Date(NOW + 60_000)), /RESEND_API_KEY/);
  assert.equal(JSON.parse(entries.get("certificate-heartbeat-state")).state, "alert");
});

test("runHeartbeat without EXPECTED_SET_PIN alerts (fails closed by default, no baseline needed)", async (t) => {
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  const entries = new Map();
  const env = {
    HEARTBEAT_STATE: { async get(k, f) { const v = entries.get(k); return f === "json" && v ? JSON.parse(v) : v ?? null; }, async put(k, v) { entries.set(k, v); } },
    STATUS_URL: "https://example.test/status.json", INDEX_URL: "https://example.test/certificate-index.json",
    MAX_STATUS_AGE_SECONDS: "691200",
    ALERT_FROM: "Ward Protocol <team@wardprotocol.org>", ALERT_TO: "team@wardprotocol.org",
  };
  globalThis.fetch = async (url) => (String(url).includes("index") ? Response.json(INDEX3) : Response.json(goodStatus()));
  await assert.rejects(() => runHeartbeat(env, new Date(NOW)), /RESEND_API_KEY/);
  const s = JSON.parse(entries.get("certificate-heartbeat-state"));
  assert.equal(s.state, "alert");
  assert.equal(s.pin_status, "NOT_PINNED");
  assert.equal(s.authoritative, false);
});

test("runHeartbeat with the correct pin is healthy and authoritative; a wrong pin alerts", async (t) => {
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  const mk = (pin) => {
    const entries = new Map();
    return { entries, env: {
      HEARTBEAT_STATE: { async get(k, f) { const v = entries.get(k); return f === "json" && v ? JSON.parse(v) : v ?? null; }, async put(k, v) { entries.set(k, v); } },
      STATUS_URL: "https://example.test/status.json", INDEX_URL: "https://example.test/certificate-index.json",
      MAX_STATUS_AGE_SECONDS: "691200", EXPECTED_SET_PIN: pin,
      ALERT_FROM: "Ward Protocol <team@wardprotocol.org>", ALERT_TO: "team@wardprotocol.org" } };
  };
  globalThis.fetch = async (url) => (String(url).includes("index") ? Response.json(INDEX3) : Response.json(goodStatus()));
  const ok = mk(PIN);
  const s = await runHeartbeat(ok.env, new Date(NOW));
  assert.equal(s.state, "healthy");
  assert.equal(s.pin_status, "PINNED");
  assert.equal(s.authoritative, true);
  assert.equal(s.ward_signed, false);
  const wrong = mk("wes1:3:" + "a".repeat(64));
  await assert.rejects(() => runHeartbeat(wrong.env, new Date(NOW)), /RESEND_API_KEY/);
  assert.match(JSON.parse(wrong.entries.get("certificate-heartbeat-state")).reasons.join("\n"), /out-of-band expected-set pin/);
});

test("negative control: the 34 approved tests need bootstrap mode, i.e. strict mode really is stricter", async () => {
  const r = await ev(goodStatus(), { expectedSetPin: undefined });
  assert.equal(r.healthy, false);
});

test("documented limit: a forger who copies every public value passes; only an independent re-derivation would catch it", async () => {
  // This test records what is NOT protected.
  const forged = goodStatus();
  const r = await ev(forged);
  assert.equal(r.healthy, true);
  assert.equal(r.authoritative, true); // authoritative about the SET, not about the archive replay having run
});


// ---- v4 attack tests (a bootstrap flag must never disable a supplied pin) ----
const shrunk = () => {
  // coordinated shrink: index AND status both drop the two September certificates
  const idx = clone(INDEX3); idx.certificates = idx.certificates.filter((c) => c.certificate_id.startsWith("KV-"));
  const st = goodStatus(); st.certificates = st.certificates.filter((c) => c.certificate_id.startsWith("KV-"));
  st.summary = { total: 1, reproducible: 0, unreproducible: 1, check_error: 0 };
  return { idx, st };
};
const forgedRegression = () => {
  // forged regression: pinned-reproducible certificate reported unreproducible, shape and counts all consistent
  const st = goodStatus();
  const c = st.certificates.find((x) => x.certificate_id === "WARD-DEVNET-20260902-001");
  c.status = "unreproducible"; c.error_code = "lgrNotFound";
  st.summary = { total: 3, reproducible: 1, unreproducible: 2, check_error: 0 };
  return st;
};

test("v4 attack: coordinated shrink with a valid pin is caught in bootstrap mode too (mode cannot disable the pin)", async () => {
  const { idx, st } = shrunk();
  for (const mode of [undefined, "bootstrap-unpinned", "anything-else"]) {
    const r = await ev(st, { index: idx, mode });
    assert.equal(r.healthy, false, `mode=${mode}`);
    assert.equal(r.pinStatus, "MISMATCH");
    assert.equal(r.authoritative, false);
    assert.match(r.reasons.join("\n"), /out-of-band expected-set pin/);
  }
});

test("v4 attack: forged regression is caught in bootstrap mode when a pin is present", async () => {
  for (const mode of [undefined, "bootstrap-unpinned"]) {
    const r = await ev(forgedRegression(), { mode });
    assert.equal(r.healthy, false, `mode=${mode}`);
    assert.match(r.reasons.join("\n"), /pinned reproducible but the status reports unreproducible/);
  }
});

test("v4 attack: a good pinned status is healthy in bootstrap mode ONLY because the pin is enforced; the mode is reported as ignored", async () => {
  const r = await ev(goodStatus(), { mode: "bootstrap-unpinned" });
  assert.equal(r.healthy, true);
  assert.equal(r.pinStatus, "PINNED");
  assert.equal(r.modeIgnored, true);
});

test("v4 attack: a malformed pin is never treated as 'no pin' (fails in bootstrap mode too)", async () => {
  for (const bad_ of ["wes1:3:xyz", "WES1:3:" + "a".repeat(64), "wes1:3:" + "A".repeat(64), "0", "wes1:"]) {
    const r = await ev(goodStatus(), { expectedSetPin: bad_, mode: "bootstrap-unpinned" });
    assert.equal(r.healthy, false, bad_);
    assert.match(r.reasons.join("\n"), /EXPECTED_SET_PIN is malformed/);
  }
});

function mkEnv(index, status, extra = {}) {
  const entries = new Map();
  return {
    entries,
    env: {
      HEARTBEAT_STATE: { async get(k, f) { const v = entries.get(k); return f === "json" && v ? JSON.parse(v) : v ?? null; }, async put(k, v) { entries.set(k, v); } },
      STATUS_URL: "https://example.test/status.json", INDEX_URL: "https://example.test/index.json",
      MAX_STATUS_AGE_SECONDS: "691200", ALERT_FROM: "a@example.test", ALERT_TO: "b@example.test",
      __fetch: async (u) => (String(u).includes("index") ? Response.json(index) : Response.json(status)),
      ...extra,
    },
  };
}

test("v4 attack (end to end): pin + bootstrap flag + coordinated shrink + forged regression => alert state, /health 503, not healthy", async (t) => {
  const orig = globalThis.fetch;
  t.after(() => { globalThis.fetch = orig; });
  const { idx, st } = shrunk();
  const c = st.certificates[0]; c.status = "unreproducible";
  globalThis.fetch = async (u) => (String(u).includes("index") ? Response.json(idx) : Response.json(st));
  const { env, entries } = mkEnv(idx, st, { EXPECTED_SET_PIN: PIN, WATCHDOG_MODE: "bootstrap-unpinned" });
  await assert.rejects(() => runHeartbeat(env, new Date(NOW)), /RESEND_API_KEY/);
  const stored = JSON.parse(entries.get("certificate-heartbeat-state"));
  assert.equal(stored.state, "alert");
  assert.equal(stored.authoritative, false);
  const worker = (await import("../workers/certificate-heartbeat.mjs")).default;
  const res = await worker.fetch(new Request("https://w.test/health"), env);
  assert.equal(res.status, 503);
});

test("v4: bootstrap mode with NO pin, end to end, records alert / authoritative:false and /health is 503 (never 200)", async (t) => {
  const orig = globalThis.fetch;
  t.after(() => { globalThis.fetch = orig; });
  const st = goodStatus();
  globalThis.fetch = async (u) => (String(u).includes("index") ? Response.json(INDEX3) : Response.json(st));
  const { env, entries } = mkEnv(INDEX3, st, { WATCHDOG_MODE: "bootstrap-unpinned" });
  await assert.rejects(() => runHeartbeat(env, new Date(NOW)), /RESEND_API_KEY/);
  const stored = JSON.parse(entries.get("certificate-heartbeat-state"));
  assert.equal(stored.state, "alert");
  assert.equal(stored.pin_status, "BOOTSTRAP_UNPINNED");
  assert.equal(stored.authoritative, false);
  const worker = (await import("../workers/certificate-heartbeat.mjs")).default;
  assert.equal((await worker.fetch(new Request("https://w.test/health"), env)).status, 503);
});

test("v4: /health answers 200 only for a healthy AND authoritative (pinned) state; an old healthy record without pin_status is 503", async () => {
  const worker = (await import("../workers/certificate-heartbeat.mjs")).default;
  const mk = (state) => ({ HEARTBEAT_STATE: { async get() { return state; } } });
  assert.equal((await worker.fetch(new Request("https://w.test/health"), mk({ state: "healthy", authoritative: true }))).status, 200);
  assert.equal((await worker.fetch(new Request("https://w.test/health"), mk({ state: "healthy", authoritative: false }))).status, 503);
  assert.equal((await worker.fetch(new Request("https://w.test/health"), mk({ state: "healthy" }))).status, 503);
});

test("v4: the production scheduled entry point ignores the test-only legacy evaluator flag", async (t) => {
  const orig = globalThis.fetch;
  t.after(() => { globalThis.fetch = orig; });
  const st = goodStatus();
  globalThis.fetch = async (u) => (String(u).includes("index") ? Response.json(INDEX3) : Response.json(st));
  const { env, entries } = mkEnv(INDEX3, st, { __TEST_ONLY_LEGACY_EVALUATOR: true }); // no pin; `true` must NOT select the seam (v5: only the Symbol does)
  const worker = (await import("../workers/certificate-heartbeat.mjs")).default;
  const pending = [];
  await worker.scheduled({}, env, { waitUntil: (p) => pending.push(p.catch(() => {})) });
  await Promise.all(pending);
  const stored = JSON.parse(entries.get("certificate-heartbeat-state"));
  assert.equal(stored.state, "alert");
  assert.equal(stored.pin_status, "NOT_PINNED");
});

test("v4: string ward_signed, timezone-less timestamps and an unbounded max-age are rejected", async () => {
  const a = goodStatus(); a.ward_signed = "true";
  await bad(a, /ward_signed is "true", not boolean false/);
  const b = goodStatus(); b.certificates[0].ward_signed = "false";
  await bad(b, /ward_signed is not boolean false/);
  const c = goodStatus(); c.generated_at = "2026-09-28T13:32:39";
  await bad(c, /no time-zone designator/);
  await bad(goodStatus(), /31-day cap/, { maxAgeMs: 1e15 });
});


// ---- v5: legacy exact-declared-match, same rule as the WARD classifier ----
const KV_ID = "KV-IV-2026-0712-001";
const withKv = (f) => { const s = goodStatus(); f(s.certificates.find((c) => c.certificate_id === KV_ID)); return s; };
const recount = (s) => { s.summary = { total: s.certificates.length, reproducible: s.certificates.filter((c) => c.status === "reproducible").length, unreproducible: s.certificates.filter((c) => c.status === "unreproducible").length, check_error: s.certificates.filter((c) => c.status === "check_error").length }; return s; };

test("v5 baseline: the declared legacy result is healthy and authoritative", async () => {
  const r = await ev(goodStatus());
  assert.equal(r.healthy, true); assert.equal(r.authoritative, true);
});

test("v5 attack: a fabricated raw_reads_archive on the legacy certificate is not healthy or authoritative", async () => {
  for (const ref of [{ sha256: "a".repeat(64) }, { file: "x.json" }, "x", 1, true, [1], {}]) {
    const r = await bad(recount(withKv((c) => { c.raw_reads_archive = ref; })), /fabricated archive|raw_reads_archive/);
    assert.equal(r.authoritative, false);
  }
});

test("v5 attack: a changed error_code or a null/absent error_code on the legacy certificate is not healthy", async () => {
  for (const v of ["other", "lgrNotFound", null, "", 0, "MISSING_RAW_READS_ARCHIVE"]) {
    const r = await bad(recount(withKv((c) => { c.error_code = v; })), /legacy error_code .* differs from the declared/);
    assert.equal(r.authoritative, false);
  }
  await bad(recount(withKv((c) => { delete c.error_code; })), /legacy error_code null differs/);
});

test("v5 attack: a changed or removed reproducibility_label on the legacy certificate is not healthy", async () => {
  for (const v of ["reproducible", "unreproducible", "Unreproducible/Legacy", null, ""]) {
    const r = await bad(recount(withKv((c) => { c.reproducibility_label = v; })), /legacy reproducibility_label .* differs from the declared/);
    assert.equal(r.authoritative, false);
  }
  await bad(recount(withKv((c) => { delete c.reproducibility_label; })), /legacy reproducibility_label null differs/);
});

test("v5: relabelling the legacy certificate as reproducible / check_error / unknown stays unhealthy (v4 behaviour kept)", async () => {
  for (const st of ["reproducible", "check_error", "verified", undefined]) {
    await bad(recount(withKv((c) => { c.status = st; })), /legacy/);
  }
});

test("v5: the older lgrNotFound wording (the 5ca3838 status file) is NOT accepted as the declared legacy result", async () => {
  // The committed OS status at 5ca3838 carries error_code lgrNotFound and no label. Under exact-declared-match that
  // reads unhealthy until the weekly checker regenerates it with the declared values (disclosed).
  const r = await ev(recount(clone(STATUS)));
  assert.equal(r.healthy, false);
});

test("v5: the legacy declared values are constants, so the status file cannot redefine them (pin format unchanged)", async () => {
  assert.deepEqual({ ...LEGACY_DECLARED }, { error_code: "missing_raw_reads_archive", reproducibility_label: "unreproducible/legacy" });
  assert.equal(Object.isFrozen(LEGACY_DECLARED), true);
  assert.equal(PIN, await computeExpectedSetPin(INDEX3));
});

test("v5: only the Symbol selects the test seam; true / 'true' / 1 / '1' through runHeartbeat(rawEnv) do not", async (t) => {
  const orig = globalThis.fetch;
  t.after(() => { globalThis.fetch = orig; });
  const st = goodStatus();
  globalThis.fetch = async (u) => (String(u).includes("index") ? Response.json(INDEX3) : Response.json(st));
  for (const v of [true, "true", 1, "1", "LEGACY", {}, Symbol("ward.test-only.legacy-evaluator")]) {
    const { env, entries } = mkEnv(INDEX3, st, { __TEST_ONLY_LEGACY_EVALUATOR: v }); // raw env, no pin
    await assert.rejects(() => runHeartbeat(env, new Date(NOW)), /RESEND_API_KEY/);
    const stored = JSON.parse(entries.get("certificate-heartbeat-state"));
    assert.equal(stored.state, "alert", String(v));
    assert.equal(stored.pin_status, "NOT_PINNED");
    assert.equal(stored.authoritative, false);
  }
  const { env } = mkEnv(INDEX3, st, { __TEST_ONLY_LEGACY_EVALUATOR: LEGACY_TEST_SEAM });
  const s = await runHeartbeat(env, new Date(NOW));
  assert.equal(s.pin_status, "LEGACY_TEST_EVALUATOR");
  assert.equal(s.authoritative, false);
});
