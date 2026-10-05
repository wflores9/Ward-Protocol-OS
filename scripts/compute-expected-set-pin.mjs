#!/usr/bin/env node
// Prints the EXPECTED_SET_PIN for a certificate index. Run it, CHECK THE LIST OUT OF BAND (a human
// confirms every id, state and archive hash against issuance records), then set the value as the
// EXPECTED_SET_PIN variable/secret of the watchdog Worker. This script does not deploy anything.
// ward_signed = false — always.
import { readFileSync } from "node:fs";
import { computeExpectedSetPin, expectedTuples } from "../workers/certificate-heartbeat-core.mjs";

const file = process.argv[2] ?? "docs/security/evidence/certificate-index.json";
const index = JSON.parse(readFileSync(file, "utf8"));
const { tuples } = expectedTuples(index);
for (const [id, state, archive] of tuples ?? []) console.error(`${id}  ${state}  ${archive ?? "-"}`);
console.log(await computeExpectedSetPin(index));
