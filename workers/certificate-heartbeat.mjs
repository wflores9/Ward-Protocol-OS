import { evaluateCertificateStatus } from "./certificate-heartbeat-core.mjs";

const STATE_KEY = "certificate-heartbeat-state";

function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload, null, 2), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
    },
  });
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

  try {
    const response = await fetch(env.STATUS_URL, {
      headers: { accept: "application/json", "user-agent": "Ward-Certificate-Heartbeat/1.0" },
      cf: { cacheTtl: 0, cacheEverything: false },
    });
    httpStatus = response.status;
    if (!response.ok) throw new Error(`status source returned HTTP ${response.status}`);
    const payload = await response.json();
    evaluation = evaluateCertificateStatus(payload, {
      nowMs: now.getTime(),
      maxAgeMs: Number(env.MAX_STATUS_AGE_SECONDS) * 1000,
      expectedCertificateCount: Number(env.EXPECTED_CERTIFICATE_COUNT),
    });
  } catch (error) {
    evaluation = {
      healthy: false,
      reasons: [`status fetch failed: ${error instanceof Error ? error.message : String(error)}`],
      generatedAt: null,
      certificateCount: null,
    };
  }

  const state = {
    schema: "ward-certificate-heartbeat/v1",
    state: evaluation.healthy ? "healthy" : "alert",
    checked_at: checkedAt,
    status_url: env.STATUS_URL,
    source_generated_at: evaluation.generatedAt,
    certificate_count: evaluation.certificateCount,
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
    return jsonResponse(state, state.state === "healthy" ? 200 : 503);
  },

  async scheduled(_controller, env, ctx) {
    ctx.waitUntil(runHeartbeat(env));
  },
};
