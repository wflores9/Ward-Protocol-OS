import { evaluateCertificateStatus, evaluateCertificateStatusStrict } from "./certificate-heartbeat-core.mjs";

const STATE_KEY = "certificate-heartbeat-state";

// TEST-ONLY seam token (v5). The seam is honoured only for this exact Symbol. A deployed Worker's env holds
// strings, numbers and bindings, never a Symbol, so no var, no JSON config and no `true`/`"true"`/`1` can select the
// legacy evaluator, even for a future caller that passes the raw env to runHeartbeat(). Tests build the Symbol with
// Symbol.for(); production code never does.
export const LEGACY_TEST_SEAM = Symbol.for("ward.test-only.legacy-evaluator");

function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload, null, 2), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}

async function fetchJson(url, label) {
  if (typeof url !== "string" || !url) throw new Error(`${label} URL is not configured`);
  const response = await fetch(url, {
    headers: { accept: "application/json", "user-agent": "Ward-Certificate-Heartbeat/1.0" },
    cf: { cacheTtl: 0, cacheEverything: false },
  });
  if (!response.ok) throw new Error(`${label} returned HTTP ${response.status}`);
  return { status: response.status, body: await response.json() };
}

function utcDay(isoTimestamp) {
  return isoTimestamp.slice(0, 10);
}

function renderAlertText(subject, state) {
  const reasons = state.reasons.length
    ? state.reasons.map((reason) => `- ${reason}`).join("\n")
    : "- no failures reported";
  return [
    subject,
    "",
    `Monitor state: ${state.state}`,
    `Checked at: ${state.checked_at}`,
    `Source: ${state.status_url}`,
    `Source generated at: ${state.source_generated_at ?? "unknown"}`,
    `Certificates expected (derived from ${state.index_url ?? "no index configured"}): ${state.expected_certificate_count ?? "unknown"}`,
    `Certificates observed in status: ${state.certificate_count ?? "unknown"}`,
    "",
    "Reasons:",
    reasons,
    "",
    "This watchdog runs on Cloudflare, outside the GitHub Actions failure domain.",
    "ward_signed = False — always.",
  ].join("\n");
}

async function sendAlert(env, subject, state) {
  if (!env.RESEND_API_KEY) {
    throw new Error("RESEND_API_KEY is not configured on the watchdog Worker");
  }
  const response = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      authorization: `Bearer ${env.RESEND_API_KEY}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({
      from: env.ALERT_FROM,
      to: [env.ALERT_TO],
      subject,
      text: renderAlertText(subject, state),
    }),
  });
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new Error(`Resend returned ${response.status}${detail ? `: ${detail}` : ""}`);
  }
}

export async function runHeartbeat(env, now = new Date()) {
  const checkedAt = now.toISOString();
  const previous = await env.HEARTBEAT_STATE.get(STATE_KEY, "json");
  let evaluation;
  let httpStatus = null;

  // The expected certificate set comes from the certificate index, fetched on
  // every run. There is no expected-count variable and no fallback constant.
  let index = null;
  let indexError = null;
  try {
    index = (await fetchJson(env.INDEX_URL, "certificate index")).body;
  } catch (error) {
    indexError = error instanceof Error ? error.message : String(error);
  }

  try {
    const fetched = await fetchJson(env.STATUS_URL, "status source");
    httpStatus = fetched.status;
    const common = {
      nowMs: now.getTime(),
      maxAgeMs: Number(env.MAX_STATUS_AGE_SECONDS) * 1000,
      index,
      indexError,
      previousIndexIds: previous?.last_known_index_ids,
    };
    // TEST-ONLY seam (Symbol-gated, see LEGACY_TEST_SEAM) for the 34 approved tests, which predate the pin and assert the pre-pin behaviour.
    // The production entry points (default export below) shadow this flag to false, so a deployed Worker can never
    // reach it, whatever its vars say. The result is labelled non-authoritative.
    if (env.__TEST_ONLY_LEGACY_EVALUATOR === LEGACY_TEST_SEAM) {
      const legacy = evaluateCertificateStatus(fetched.body, common);
      evaluation = { ...legacy, pinStatus: "LEGACY_TEST_EVALUATOR", authoritative: false };
    } else {
      evaluation = await evaluateCertificateStatusStrict(fetched.body, {
        ...common,
        expectedSetPin: env.EXPECTED_SET_PIN,
        mode: env.WATCHDOG_MODE,
      });
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    const statusResponse = /HTTP (\d+)/.exec(message);
    if (statusResponse) httpStatus = Number(statusResponse[1]);
    evaluation = {
      healthy: false,
      reasons: [
        `status fetch failed: ${message}`,
        ...(indexError ? [`certificate index unavailable: ${indexError}`] : []),
      ],
      generatedAt: null,
      certificateCount: null,
      expectedCertificateCount: null,
      expectedCertificateIds: null,
    };
  }

  const state = {
    schema: "ward-certificate-heartbeat/v1",
    state: evaluation.healthy ? "healthy" : "alert",
    checked_at: checkedAt,
    status_url: env.STATUS_URL,
    index_url: env.INDEX_URL ?? null,
    source_generated_at: evaluation.generatedAt,
    certificate_count: evaluation.certificateCount,
    expected_certificate_count: evaluation.expectedCertificateCount ?? null,
    expected_certificate_ids: evaluation.expectedCertificateIds ?? null,
    // The removal baseline only advances on a healthy run. An unhealthy run
    // (including "a certificate vanished from the index") never re-baselines
    // itself, so the alert keeps firing until the condition is genuinely resolved.
    last_known_index_ids: evaluation.healthy
      ? evaluation.expectedCertificateIds
      : previous?.last_known_index_ids ?? null,
    // pin_status: PINNED = the expected set was checked against an out-of-band commitment (enforced in every mode);
    // BOOTSTRAP_UNPINNED = explicit bootstrap with NO pin: never healthy; NOT_PINNED/MISMATCH = alert.
    pin_status: evaluation.pinStatus ?? "UNKNOWN",
    authoritative: evaluation.authoritative === true,
    ward_signed: false,
    source_http_status: httpStatus,
    reasons: evaluation.reasons,
    alert_from: env.ALERT_FROM,
    alert_to: env.ALERT_TO,
    notification: "not_required",
  };

  const isRecovery = evaluation.healthy && previous?.state === "alert";
  const alertAlreadySentToday =
    previous?.state === "alert" &&
    previous?.last_alert_at &&
    utcDay(previous.last_alert_at) === utcDay(checkedAt);
  const shouldSendAlert = !evaluation.healthy && !alertAlreadySentToday;

  if (shouldSendAlert || isRecovery) {
    const subject = shouldSendAlert
      ? "Ward alert: certificate monitor is stale or incomplete"
      : "Ward recovery: certificate monitor is healthy";
    try {
      await sendAlert(env, subject, state);
      state.notification = shouldSendAlert ? "alert_sent" : "recovery_sent";
      state.last_alert_at = shouldSendAlert ? checkedAt : previous?.last_alert_at ?? null;
    } catch (error) {
      state.notification = "send_failed";
      state.notification_error = error instanceof Error ? error.message : String(error);
      await env.HEARTBEAT_STATE.put(STATE_KEY, JSON.stringify(state));
      throw error;
    }
  } else if (previous?.last_alert_at) {
    state.last_alert_at = previous.last_alert_at;
  }

  await env.HEARTBEAT_STATE.put(STATE_KEY, JSON.stringify(state));
  return state;
}

// Production entry points never honour the test-only seam, even if a var of that name were set on the Worker.
function productionEnv(env) {
  return Object.create(env, { __TEST_ONLY_LEGACY_EVALUATOR: { value: false } });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method !== "GET" || url.pathname !== "/health") {
      return jsonResponse({ detail: "Not Found" }, 404);
    }
    const state = await env.HEARTBEAT_STATE.get(STATE_KEY, "json");
    if (!state) {
      return jsonResponse({ state: "not_yet_run" }, 503);
    }
    // 200 only for a healthy state that was checked against a pin. Anything else, including an old state record
    // that predates pin_status, answers 503.
    const ok = state.state === "healthy" && state.authoritative === true;
    return jsonResponse(state, ok ? 200 : 503);
  },

  async scheduled(_controller, env, ctx) {
    ctx.waitUntil(runHeartbeat(productionEnv(env)));
  },
};
