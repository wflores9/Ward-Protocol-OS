# XRPL Devnet operator SUPERSEDE evidence run - 2026-09-02

Public evidence certificate **WARD-DEVNET-20260902-001**. Issued with archive-on-issuance.

This is an **operator-run SUPERSEDE** of the `WARD-DEVNET-20260901-001` operator
receipt. It is **not** a Kairo independent verification. It does **not** retract
or rewrite:

- `KV-IV-2026-0712-001` (frozen unreproducible/legacy, Kairo)
- `WARD-DEVNET-20260901-001` (kept as-is, including `independently_verified: true`
  honesty gap)

`independently_verified` is **false**. `ward_signed` is **false**.

Loan / LoanBroker / Vault were discovered from LoanSet metadata
(`C4A6A5626F6B4CE2B1513520CB184B9507EA91A772FB73614721929E85EBF942` tesSUCCESS
in ledger 4970389), not from prior locators.

## Result

- Network: XRPL Devnet
- Issuance pin: ledger_index 4970389,
  ledger_hash `8CFDACA5A48F98ED2B3403E227211DA5DF40E29C5C1FC023645AD8ED789B9811`,
  close_time 841620142 (`2026-09-01T23:22:22Z`)
- Evaluation pin: ledger_index 4970443,
  ledger_hash `4334E6D89D0974E9E64B3D976F29E8BB862D7CE005420C2DEEF80D83979FCEE5`,
  close_time 841620310 (`2026-09-01T23:25:10Z`)
- Check 04 evaluated at the evaluation pin (issuance close 841620142 is before
  default-ready 841620271)
- FeeSettings via `ledger_entry` `{"fee": true, "ledger_index": <pin>}` at both
  pins. Chain-confirmed object index
  `4BC50C9B0D8515D3EAAE1E74B29A95804346C491EE1A95BF25E4AAB854A6A651`:
  ReserveBase 1000000, ReserveIncrement 200000, BaseFee `"1"`,
  ReferenceFeeUnits 10, LedgerEntryType FeeSettings. Both validated, hash match.
  Not command `fee_settings`. Not a `server_state` substitute.
- Ward decision: approved
- Ward semantic checks: 9 of 9 passed
- Independent verification: false (operator-run SUPERSEDE)
- Claim payout: 1000001 drops
- Coverage ratio after FeeSettings reserves: 99x
- Unsigned settlement packet: present
- Settlement submitted: no
- `ward_signed = False` — always

## Files and SHA-256

- `phase1-devnet-pre-resolution-2026-09-02.json`
  `ebe919272d30dd8295c58253ac1b945206687c8ff28d84fecde1eeb55255422c`
- `ward-evidence-pre-resolution-2026-09-02.json`
  `018bbf33b67f70e4830121cea0fdbe6dbe559d5a0667e1bfbafa2895bf2eda28`
- `ward-evidence-pre-resolution-2026-09-02.raw-reads.json`
  `372cd7bed0cf9c4864cc047a90f8c40cc1dd8888d849edb4147eba240e40c87e`
- `ward-evidence-pre-resolution-2026-09-02.operator-verification.json`
  `8772d0210e29436171653371781c99eef370a4a1cbc1c51dbc98ad388c208d3c`
  (operator path; `independently_verified: false`)

Kairo's independent archive sha256
`50090fc373b39ab16cbf057a63e82a2611a6462307a462de9700ad627dd6f6ba` (23 reads)
is a different artifact. This operator archive is 41 reads. The hashes do not
match and are not substituted.

## Reproduce

From the repository root:

```bash
python3 scripts/validate_partner_evidence.py \
  docs/security/evidence/devnet/2026-09-02/ward-evidence-pre-resolution-2026-09-02.json

python3 scripts/verify_devnet_evidence_independent.py \
  docs/security/evidence/devnet/2026-09-02/phase1-devnet-pre-resolution-2026-09-02.json \
  docs/security/evidence/devnet/2026-09-02/ward-evidence-pre-resolution-2026-09-02.json \
  --verifier-role operator

python3 scripts/check_certificate_reproducibility.py
python3 scripts/check_signing_boundary.py
```

Expected results:

- Structural gate: `Evidence bundle accepted`
- `approved_by_ward: true`
- `independently_verified: false`
- `ward_signed: false`
- `failures: []`
- `WARD-DEVNET-20260902-001`: reproducible from raw_reads_archive
- `WARD-DEVNET-20260901-001`: reproducible (unchanged)
- `KV-IV-2026-0712-001`: unreproducible/legacy (unchanged)
