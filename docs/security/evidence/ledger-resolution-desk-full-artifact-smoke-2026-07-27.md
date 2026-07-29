# Ledger Resolution Desk Full Artifact Smoke Test - 2026-07-27

## Scope

This smoke test verifies the live Ward Ledger Worker can run the Resolution Desk as a full case workflow, not just a visual shell.

The test covered:

- create a resolution case
- verify all required evidence
- generate a canonical `ward-resolution/v1` receipt
- store the full receipt artifact on the case
- replay the same canonical engine input
- compare replay hash against the stored receipt hash
- route the case to institution review
- mark the case accepted after matched replay
- preserve the audit trail

## Environment

- Ledger Worker: `Ward production runtime`
- Worker URL: `https://wardprotocol.org`
- Worker version: `c9d38228-5ca2-45b1-90fe-0293eed2d363`
- Canonical engine URL: `https://api.wardprotocol.org`
- Receipt schema: `ward-resolution/v1`

## Passing Control Path

Workflow: `conditional_release`

Case:

- `case_4f80bcc7-6064-481b-9e7e-93ed0544e5fc`
- Title: `Full artifact smoke - conditional release`

Result:

```json
{
  "stage": "accepted",
  "review": "accepted",
  "receiptHash": "9855479f9e45f154705e473317016210c17a8d124748e2c3db2b159f210f4ac9",
  "receiptStored": true,
  "receiptDecision": "approved",
  "receiptWardSigned": false,
  "replayStatus": "matched",
  "replayMatched": true
}
```

Audit events recorded:

```text
case_created
evidence_updated
evidence_updated
evidence_updated
receipt_generated
replay_run
case_updated
replay_run
case_updated
```

## Adapter Boundary Found

A Netten escrow release smoke payload correctly failed at the canonical engine boundary with HTTP `422`.

This means the Resolution Desk UI can create and map a Netten-style case, but Netten receipt generation must remain adapter-pending until the canonical engine supports that payload. The desk must not fake a receipt for unsupported adapter input.

## Readiness Conclusion

The Resolution Desk now has a live, full-stack happy path for `conditional_release` case artifacts. Netten is not yet full-stack receipt-ready because canonical engine support is still required.
