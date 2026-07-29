# Netten Resolution Desk Full-Stack Smoke Test - 2026-07-27

## Scope

This smoke test verifies the live Ward Ledger Worker can run a Netten escrow-release case through the full Resolution Desk path using the canonical Ward engine.

The test covered:

- create a `netten_escrow_release` resolution case
- verify all required evidence
- generate a canonical `ward-resolution/v1` receipt
- store the full receipt artifact on the case
- replay the same canonical engine input
- compare replay hash against the stored receipt hash
- route the case to institution review
- mark the case accepted after matched replay
- preserve `ward_signed = false` and produce only an unsigned action

## Environment

- Ledger Worker: `ward-ledger`
- Worker URL: `https://ward-ledger.wflores-9.workers.dev`
- Worker version: `3d17f5cd-7324-4848-9cb3-d1f9954d606a`
- Canonical engine URL: `https://api.wardprotocol.org`
- Receipt schema: `ward-resolution/v1`

## Passing Netten Control Path

Workflow: `netten_escrow_release`

Case:

- `case_80c8ffb3-6246-4d40-8f5f-84c664491575`
- Title: `Netten escrow release full-stack smoke`

Result:

```json
{
  "case_id": "case_80c8ffb3-6246-4d40-8f5f-84c664491575",
  "receipt_hash": "095faa35669ed8edec384152d94cd20c7a695659f6a7d0aff276c89793e774e4",
  "workflow": "netten_escrow_release",
  "decision": "approved",
  "ward_signed": false,
  "action_type": "xrpl.escrow_finish",
  "replay_status": "matched",
  "review": "accepted",
  "stage": "accepted"
}
```

## Signer Boundary

The generated receipt preserved `ward_signed = false`. The output action was `xrpl.escrow_finish`, and it remained an unsigned instruction for the external institution or escrow authority to review and sign.

## Readiness Conclusion

Netten escrow release is now full-stack smoke-tested through the canonical engine and live Ledger Worker. This is still pilot evidence, not a production SLA or custody/signing claim.
