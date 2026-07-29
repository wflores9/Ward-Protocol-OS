# Ward Review Packet - Netten escrow release full-stack smoke

## Packet

- Version: ward-review-packet/v1
- Generated: 2026-07-27T22:21:00.000Z
- Case ID: case_80c8ffb3-6246-4d40-8f5f-84c664491575

## Workflow Map

| Field | Value |
| --- | --- |
| Facility / obligation | Services escrow half-deposit release workflow |
| Parties | Client, Service provider, Escrow authority / institution |
| Policy artifact | ward.netten-escrow-release@1.0.0 |
| Authoritative source | XRPL validated escrow state and agreed service-acceptance evidence |
| Triggering event | Client acceptance or agreed release interval elapsed, with no egregious dispute open |
| Fixed rules | NE-01 deposit received; NE-02 service rendered; NE-03 release authorized; NE-04 no egregious dispute; NE-05 external signer retained |
| Expected output | ward-resolution/v1 receipt and unsigned xrpl.escrow_finish action for external review and signing |

## Signer Boundary

- ward_signed: false
- External signer: Escrow authority / institution signer
- Statement: Ward evaluates and prepares evidence plus unsigned instructions. The institution retains signing and settlement authority.

## Evidence Bundle

| Evidence | Required | Status | Reference |
| --- | --- | --- | --- |
| Authoritative escrow ledger state | Required | verified | xrpl:ledger/100200300/netten-services-release-001 |
| Policy artifact / rule bundle | Required | verified | ward.netten-escrow-release@1.0.0 |
| Service acceptance or interval trigger evidence | Required | verified | client_acceptance=true; release_interval_elapsed=false; egregious_dispute=false |

## Receipt

- Schema: ward-resolution/v1
- Hash: 095faa35669ed8edec384152d94cd20c7a695659f6a7d0aff276c89793e774e4
- Generated: 2026-07-27T22:18:00.000Z
- Decision: approved
- Ward signed: false

## Replay

- Status: matched
- Matched: true
- Original receipt hash: 095faa35669ed8edec384152d94cd20c7a695659f6a7d0aff276c89793e774e4
- Replay receipt hash: 095faa35669ed8edec384152d94cd20c7a695659f6a7d0aff276c89793e774e4
- Checked: 2026-07-27T22:19:00.000Z

## Institution Review

- Status: accepted
- Reviewer: Ward operator smoke review
- Reason: Pilot smoke case accepted after matching replay. External signer remains responsible for any real escrow execution.

## Limitations

- This packet is a pilot review artifact, not a production SLA.
- Ward does not custody funds, sign transactions, submit settlement, insure loss, or replace institutional judgment.
- Receipt validity depends on the frozen workflow input and authoritative evidence references captured in the case.
- Institutional acceptance means review completed; it does not mean Ward signed or settled.

## Audit Trail

| Time | Actor | Action | Detail |
| --- | --- | --- | --- |
| 2026-07-27T22:15:00.000Z | operator | case_created | Not recorded |
| 2026-07-27T22:17:00.000Z | operator | evidence_updated | All required evidence marked verified for smoke case. |
| 2026-07-27T22:18:00.000Z | operator | receipt_generated | Canonical engine returned approved receipt with ward_signed=false. |
| 2026-07-27T22:19:00.000Z | operator | replay_run | Replay hash matched original receipt hash. |
| 2026-07-27T22:20:00.000Z | operator | institution_review_routed | Not recorded |
| 2026-07-27T22:21:00.000Z | operator | institution_review_accepted | Accepted as internal pilot smoke evidence only. |
