const STATUS_SCHEMA = "ward-certificate-reproducibility-status/v1";
const INDEX_SCHEMA = "ward-certificate-index/v1";
const PIN_PREFIX = "wes1:";
const DEFAULT_MAX_AGE_MS = 8 * 24 * 60 * 60 * 1000;

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

// The expected certificate set is derived from the certificate index, which is
// the issuance register that the status file is generated from
// (status.source_index). It is never a hard-coded number and it is never
// derived from the status file being judged. `options.expectedCertificateCount`
// from earlier versions is intentionally ignored.
export function deriveExpectedCertificates(index) {
  const problems = [];
  if (!index || typeof index !== "object" || Array.isArray(index)) {
    return { ids: null, problems: ["certificate index must be a JSON object"] };
  }
  if (index.schema !== INDEX_SCHEMA) {
    problems.push(`unexpected certificate index schema: ${String(index.schema)}`);
  }
  if (!Array.isArray(index.certificates)) {
    problems.push("certificate index certificates must be an array");
    return { ids: null, problems };
  }
  const ids = [];
  const seen = new Set();
  for (const entry of index.certificates) {
    const id = entry?.certificate_id;
    if (typeof id !== "string" || !id.trim()) {
      problems.push("certificate index entry is missing certificate_id");
      continue;
    }
    if (seen.has(id)) {
      problems.push(`certificate index has duplicate certificate_id: ${id}`);
      continue;
    }
    seen.add(id);
    ids.push(id);
  }
  return { ids, problems };
}

export function evaluateCertificateStatus(payload, options = {}) {
  const nowMs = options.nowMs ?? Date.now();
  const maxAgeMs = options.maxAgeMs === undefined ? DEFAULT_MAX_AGE_MS : options.maxAgeMs;
  const reasons = [];

  // Fail closed on a bad threshold. A NaN threshold (for example
  // Number(undefined) from a missing env var) would make every
  // `age > maxAge` comparison false and silently disable the staleness check.
  const maxAgeValid = Number.isFinite(maxAgeMs) && maxAgeMs > 0;
  if (!maxAgeValid) {
    reasons.push("MAX_STATUS_AGE_SECONDS is missing or invalid; staleness cannot be evaluated");
  }

  let expectedIds = null;
  if (options.indexError) {
    reasons.push(`certificate index unavailable: ${options.indexError}`);
  } else {
    const derived = deriveExpectedCertificates(options.index);
    expectedIds = derived.ids;
    reasons.push(...derived.problems);
  }
  const expectedCertificateCount = expectedIds ? expectedIds.length : null;

  // Deriving "expected" from the index means the index must not shrink silently.
  // Any certificate the watchdog saw in the index on its previous successful
  // read that is now gone is reported. This compares against the last observed
  // index, never against the status file, and it does not update any expectation.
  if (expectedIds && Array.isArray(options.previousIndexIds)) {
    const now = new Set(expectedIds);
    for (const id of options.previousIndexIds) {
      if (!now.has(id)) reasons.push(`certificate removed from index since last check: ${id}`);
    }
  }

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
    } else if (maxAgeValid && ageMs > maxAgeMs) {
      reasons.push(`status is stale by ${Math.floor(ageMs / 1000)} seconds`);
    }
  }

  const certificates = Array.isArray(payload.certificates) ? payload.certificates : null;
  if (!certificates) {
    reasons.push("certificates must be an array");
  } else {
    if (expectedCertificateCount !== null) {
      if (certificates.length !== expectedCertificateCount) {
        reasons.push(
          `certificate count mismatch: expected ${expectedCertificateCount}, found ${certificates.length}`,
        );
      }
      const statusIds = new Set(
        certificates.map((entry) => entry?.certificate_id).filter((id) => typeof id === "string"),
      );
      for (const id of expectedIds) {
        if (!statusIds.has(id)) reasons.push(`certificate in index is missing from status: ${id}`);
      }
      const expectedSet = new Set(expectedIds);
      for (const id of statusIds) {
        if (!expectedSet.has(id)) reasons.push(`certificate in status is not in index: ${id}`);
      }
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
          if (maxAgeValid && nowMs - checkedAtMs > maxAgeMs) {
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
      if (expectedCertificateCount !== null && total !== expectedCertificateCount) {
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
    expectedCertificateCount,
    expectedCertificateIds: expectedIds,
  };
}

// ---------------------------------------------------------------------------
// STRICT mode. A status document is never its own authority.
//
// The expected certificate set must be committed OUT OF BAND: an operator-held Worker variable
// EXPECTED_SET_PIN, computed by `node scripts/compute-expected-set-pin.mjs <certificate-index.json>`
// after a human has checked the set. The pin covers, per certificate, (id, expected state, pinned
// archive sha256), so a coordinated rewrite of index + status (shrink, swap, empty) no longer
// matches it, and a status that contradicts the pinned expectation (for example a pinned-reproducible
// certificate reported unreproducible) is reported.
//
// What no watchdog can do without an independent re-derivation: detect a forger who copies the public
// values (ids, archive hashes, fresh timestamps) into a well-shaped status. The pin removes the
// *coordinated-shrink* and *expected-set-from-the-attacked-file* holes; it does not prove the archive
// replay actually ran. That is why the weekly workflow and this watchdog are separate failure domains.
// ---------------------------------------------------------------------------
async function sha256Hex(text) {
  const bytes = new TextEncoder().encode(text);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export function expectedTuples(index) {
  const derived = deriveExpectedCertificates(index);
  if (!derived.ids) return { tuples: null, problems: derived.problems };
  const byId = new Map(index.certificates.map((c) => [c.certificate_id, c]));
  const tuples = derived.ids
    .map((id) => {
      const c = byId.get(id);
      const archive = c?.raw_reads_archive?.sha256 ?? null;
      const legacy = c?.legacy === true || (c?.raw_reads_archive == null);
      return [id, legacy ? "legacy_unreproducible" : "reproducible", archive];
    })
    .sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));
  return { tuples, problems: derived.problems };
}

export async function computeExpectedSetPin(index) {
  const { tuples, problems } = expectedTuples(index);
  if (!tuples || problems.length) throw new Error(`cannot pin an invalid index: ${problems.join("; ")}`);
  if (tuples.length === 0) throw new Error("cannot pin an empty certificate set");
  return `${PIN_PREFIX}${tuples.length}:${await sha256Hex(JSON.stringify(tuples))}`;
}

// Declared result of a legacy (no issuance archive) certificate. Same values as scripts/certificate_states.py in WARD.
export const LEGACY_DECLARED = Object.freeze({ error_code: "missing_raw_reads_archive", reproducibility_label: "unreproducible/legacy" });
const PIN_RE = new RegExp(`^${PIN_PREFIX}\\d+:[0-9a-f]{64}$`);
const MAX_AGE_CAP_MS = 31 * 24 * 60 * 60 * 1000;
const HAS_ZONE = /(Z|[+-]\d{2}:?\d{2})$/i;

// Pin handling (v4): a well-formed pin is ALWAYS enforced, whatever `mode` says. A leftover
// bootstrap flag can therefore never switch strictness off. `mode: "bootstrap-unpinned"` applies only when NO pin
// is configured at all, and even then the result is NEVER healthy: it reports authoritative:false and an explicit
// non-healthy reason (the deployer is told the computed pin to verify out of band). A malformed non-empty pin fails
// closed in every mode.
export async function evaluateCertificateStatusStrict(payload, options = {}) {
  const base = evaluateCertificateStatus(payload, options);
  const reasons = [...base.reasons];
  const pin = options.expectedSetPin;
  const pinPresent = typeof pin === "string" && pin.trim() !== "";
  const pinValid = pinPresent && PIN_RE.test(pin);
  const bootstrapRequested = options.mode === "bootstrap-unpinned";
  const nowMs = options.nowMs ?? Date.now();
  let pinStatus = "PINNED";
  let modeIgnored = false;
  const indexOk = Boolean(options.index) && !options.indexError;
  const { tuples } = indexOk ? expectedTuples(options.index) : { tuples: null };

  // Checks that need no pin apply in every mode.
  if (tuples && tuples.length === 0) reasons.push("certificate index is empty: an empty set is never healthy");
  if (Number.isFinite(options.maxAgeMs) && options.maxAgeMs > MAX_AGE_CAP_MS) reasons.push("MAX_STATUS_AGE_SECONDS exceeds the 31-day cap: an unbounded freshness window is not accepted");

  const hintFor = async () => {
    try { if (indexOk) return ` (computed from the index just read: ${await computeExpectedSetPin(options.index)}; verify it out of band before setting EXPECTED_SET_PIN)`; } catch { /* no hint */ }
    return "";
  };

  if (pinValid) {
    modeIgnored = bootstrapRequested;
    if (!tuples) {
      pinStatus = "UNVERIFIABLE";
    } else if (tuples.length > 0) {
      const computed = `${PIN_PREFIX}${tuples.length}:${await sha256Hex(JSON.stringify(tuples))}`;
      if (computed !== pin) {
        pinStatus = "MISMATCH";
        reasons.push(`certificate index does not match the out-of-band expected-set pin (pinned ${pin}, index ${computed}): the set changed, shrank or was swapped`);
      }
    } else {
      pinStatus = "MISMATCH";
    }
  } else if (pinPresent) {
    pinStatus = "NOT_PINNED";
    reasons.push("EXPECTED_SET_PIN is malformed: failing closed in every mode (a bad pin is never treated as no pin)");
  } else if (bootstrapRequested) {
    pinStatus = "BOOTSTRAP_UNPINNED";
    reasons.push(`bootstrap mode (no EXPECTED_SET_PIN configured): the expected set has no out-of-band commitment, so this run is NOT authoritative and is never reported healthy${await hintFor()}`);
  } else {
    pinStatus = "NOT_PINNED";
    reasons.push(`EXPECTED_SET_PIN is missing: the expected certificate set has no out-of-band commitment; failing closed${await hintFor()}`);
  }

  const p = payload && typeof payload === "object" && !Array.isArray(payload) ? payload : null;
  if (p) {
    if (p.ward_signed === true) reasons.push("status claims ward_signed=true");
    else if ("ward_signed" in p && p.ward_signed !== false) reasons.push(`status ward_signed is ${JSON.stringify(p.ward_signed)}, not boolean false`);
    if (typeof p.generated_at === "string" && !HAS_ZONE.test(p.generated_at.trim())) reasons.push("status generated_at has no time-zone designator (would be parsed in the runtime's local zone)");
    const certs = Array.isArray(p.certificates) ? p.certificates : null;
    if (certs && certs.length === 0) reasons.push("status lists no certificates: an empty status is never healthy");
    const expectedById = new Map((tuples ?? []).map((t) => [t[0], t]));
    let repro = 0, unrepro = 0, errors = 0;
    for (const c of certs ?? []) {
      if (c?.ward_signed === true) reasons.push(`${c.certificate_id} claims ward_signed=true`);
      else if (c && "ward_signed" in c && c.ward_signed !== false) reasons.push(`${c.certificate_id} ward_signed is not boolean false`);
      if (typeof c?.checked_at === "string" && !HAS_ZONE.test(c.checked_at.trim())) reasons.push(`${c.certificate_id} checked_at has no time-zone designator`);
      if (c?.status === "reproducible") repro += 1;
      else if (c?.status === "unreproducible") unrepro += 1;
      else if (c?.status === "check_error") errors += 1;
      if (c?.checked_at) {
        const t = Date.parse(c.checked_at);
        if (Number.isFinite(t) && t - nowMs > 5 * 60 * 1000) reasons.push(`${c.certificate_id} checked_at is more than five minutes in the future`);
      }
      const exp = expectedById.get(c?.certificate_id);
      if (exp && pinStatus === "PINNED") {
        if (exp[1] === "reproducible") {
          if (c.status !== "reproducible") reasons.push(`${c.certificate_id} is pinned reproducible but the status reports ${c.status}: regression`);
          const got = c?.raw_reads_archive?.sha256;
          if (got !== exp[2]) reasons.push(`${c.certificate_id} archive sha256 in the status (${got ?? "absent"}) differs from the pinned value`);
        } else {
          // v5: a legacy certificate must match its DECLARED result exactly (the same rule as the WARD
          // classifier certificate_states.py). Anything else is a regression: a relabel, a fabricated archive, a changed
          // error code or a changed label. The declared values are constants of the legacy state, not read from the
          // status file, so the status cannot redefine them (and the wes1 pin format is unchanged).
          if (c.status === "reproducible") reasons.push(`${c.certificate_id} is pinned legacy/unreproducible but the status reports reproducible`);
          if (c.status !== "unreproducible") reasons.push(`${c.certificate_id} is pinned legacy/unreproducible but the status reports ${c.status}: legacy exact-declared-match failed`);
          if (c.error_code !== LEGACY_DECLARED.error_code) reasons.push(`${c.certificate_id} legacy error_code ${JSON.stringify(c.error_code ?? null)} differs from the declared ${JSON.stringify(LEGACY_DECLARED.error_code)}: legacy exact-declared-match failed`);
          if (c.reproducibility_label !== LEGACY_DECLARED.reproducibility_label) reasons.push(`${c.certificate_id} legacy reproducibility_label ${JSON.stringify(c.reproducibility_label ?? null)} differs from the declared ${JSON.stringify(LEGACY_DECLARED.reproducibility_label)}: legacy exact-declared-match failed`);
          const ref = c.raw_reads_archive;
          if (!(ref === null || ref === undefined)) reasons.push(`${c.certificate_id} is legacy but the status carries a raw_reads_archive (a fabricated archive is not allowed)`);
        }
      }
    }
    const s = p.summary;
    if (s && typeof s === "object" && certs) {
      if (s.reproducible !== repro) reasons.push(`summary.reproducible ${s.reproducible} does not match the entries (${repro})`);
      if (s.unreproducible !== unrepro) reasons.push(`summary.unreproducible ${s.unreproducible} does not match the entries (${unrepro})`);
      if (s.check_error !== errors) reasons.push(`summary.check_error ${s.check_error} does not match the entries (${errors})`);
    }
  }
  const healthy = reasons.length === 0 && pinStatus === "PINNED";
  return { ...base, healthy, reasons: [...new Set(reasons)], pinStatus, modeIgnored, authoritative: pinStatus === "PINNED" && reasons.length === 0 };
}
