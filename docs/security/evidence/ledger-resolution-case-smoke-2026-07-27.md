# Ledger Resolution Case Smoke Test - 2026-07-27

## Scope

This smoke test verifies the live Ward Ledger Worker can create a resolution case, enforce required evidence before receipt generation, generate a canonical receipt after evidence verification, and replay the receipt through the canonical Ward engine.

## Environment

- Ledger Worker: `Ward production runtime`
- Worker URL: `https://wardprotocol.org`
- Worker version: `0fd7caaa-fec5-4539-a623-e2d3eac205ed`
- Canonical engine URL: `https://api.wardprotocol.org`
- Receipt schema: `ward-resolution/v1`

## Blocked Receipt Path

Case: `case_8a4cb5fb-39ac-4efe-b5a5-38bf15176ba2`

Result:
- Required evidence was missing.
- Receipt generation was blocked.
- No `receiptHash` was produced.
- Case stage moved to `evidence`.
- Audit event recorded: `receipt_blocked`.

Expected error: `Verify required evidence before generating a receipt.`

Blockers recorded:
- `Authoritative ledger state is not verified.`
- `Policy artifact / version is not verified.`
- `Trigger evidence is not verified.`

## Positive Receipt And Replay Path

Case: `case_3bb6b8b3-b72d-4ae3-b5d3-eee887cf4cb1`

Result:
- Required evidence was verified.
- Blockers cleared.
- Receipt was generated.
- Receipt replay matched.

Receipt hash: `939b8123bcc3ceb408bc5d371cc74d31f7c4d18a332953ef8cd0840509a2a700`

Final state:
- `stage: institution-review`
- `replayStatus: matched`
- `matched: true`

Audit events confirmed:
- `case_created`
- `evidence_updated`
- `receipt_generated`
- `replay_run`

## CTO Gate Result

Pass.

The live resolution-case workspace now enforces the required evidence boundary before canonical receipt generation and confirms deterministic replay after receipt generation.
