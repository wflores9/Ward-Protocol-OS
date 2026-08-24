const STATUS_SCHEMA = "ward-certificate-reproducibility-status/v1";

function parseTimestamp(value, fieldName) {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${fieldName} must be a timestamp string`);
  }
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) {
    throw new Error(`${fieldName} is not a valid timestamp`);
  }
  return parsed;
}

function integer(value, fieldName) {
  if (!Number.isInteger(value) || value < 0) {
    throw new Error(`${fieldName} must be a non-negative integer`);
  }
  return value;
}

export function evaluateCertificateStatus(payload, options = {}) {
  const nowMs = options.nowMs ?? Date.now();
  const maxAgeMs = options.maxAgeMs ?? 8 * 24 * 60 * 60 * 1000;
  const expectedCertificateCount = options.expectedCertificateCount ?? 1;
  const reasons = [];

  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return { healthy: false, reasons: ["status payload must be a JSON object"] };
  }
  if (payload.schema !== STATUS_SCHEMA) {
    reasons.push(`unexpected schema: ${String(payload.schema)}`);
  }

  let generatedAtMs;
  try {
    generatedAtMs = parseTimestamp(payload.generated_at, "generated_at");
  } catch (error) {
    reasons.push(error.message);
  }

  if (generatedAtMs !== undefined) {
    const ageMs = nowMs - generatedAtMs;
    if (ageMs < -5 * 60 * 1000) {
      reasons.push("generated_at is more than five minutes in the future");
    } else if (ageMs > maxAgeMs) {
      reasons.push(`status is stale by ${Math.floor(ageMs / 1000)} seconds`);
    }
  }

  const certificates = Array.isArray(payload.certificates) ? payload.certificates : null;
  if (!certificates) {
    reasons.push("certificates must be an array");
  } else {
    if (certificates.length !== expectedCertificateCount) {
      reasons.push(
        `certificate count mismatch: expected ${expectedCertificateCount}, found ${certificates.length}`,
      );
    }
    const seen = new Set();
    for (const certificate of certificates) {
      const certificateId = certificate?.certificate_id;
      if (typeof certificateId !== "string" || !certificateId.trim()) {
        reasons.push("certificate entry is missing certificate_id");
        continue;
      }
      if (seen.has(certificateId)) {
        reasons.push(`duplicate certificate_id: ${certificateId}`);
      }
      seen.add(certificateId);
      if (!certificate.checked_at) {
        reasons.push(`${certificateId} is missing checked_at`);
      } else {
        try {
          const checkedAtMs = parseTimestamp(certificate.checked_at, `${certificateId}.checked_at`);
          if (nowMs - checkedAtMs > maxAgeMs) {
            reasons.push(`${certificateId} check result is stale`);
          }
        } catch (error) {
          reasons.push(error.message);
        }
      }
      if (certificate.status === "check_error") {
        reasons.push(`${certificateId} ended in check_error`);
      } else if (!['reproducible', 'unreproducible'].includes(certificate.status)) {
        reasons.push(`${certificateId} has unknown status: ${String(certificate.status)}`);
      }
    }
  }

  const summary = payload.summary;
  if (!summary || typeof summary !== "object" || Array.isArray(summary)) {
    reasons.push("summary must be an object");
  } else {
    try {
      const total = integer(summary.total, "summary.total");
      const reproducible = integer(summary.reproducible, "summary.reproducible");
      const unreproducible = integer(summary.unreproducible, "summary.unreproducible");
      const checkError = integer(summary.check_error, "summary.check_error");
      if (total !== expectedCertificateCount) {
        reasons.push(`summary total mismatch: expected ${expectedCertificateCount}, found ${total}`);
      }
      if (certificates && total !== certificates.length) {
        reasons.push(`summary total ${total} does not match certificates length ${certificates.length}`);
      }
      if (reproducible + unreproducible + checkError !== total) {
        reasons.push("summary status counts do not add up to total");
      }
      if (checkError > 0) {
        reasons.push(`summary reports ${checkError} check_error result(s)`);
      }
    } catch (error) {
      reasons.push(error.message);
    }
  }

  return {
    healthy: reasons.length === 0,
    reasons,
    generatedAt: typeof payload.generated_at === "string" ? payload.generated_at : null,
    certificateCount: certificates?.length ?? null,
  };
}
