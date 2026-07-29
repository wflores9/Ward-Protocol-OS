# Netten Circles Tax Reserve Pilot

## Synthetic Case

Netten Circles lets a freelancer or agency reserve part of earned income after a job completes. The first Ward pilot uses synthetic data only.

- Job amount: `$1,500`
- Reserve rule: `50%`
- Reserve amount: `$750`
- Review window: `72 hours`
- Parties: `freelancer/agency + client`
- Blocker: client disapproval of delivered assets during review

## Governed Question

Was this amount supposed to be reserved, and is it eligible to be released now?

Ward evaluates the reserve event, review window, client approval or disapproval state, and signer boundary. Ward does not custody, sign, release funds, or provide tax advice.

## Evidence Snapshot

Adapter: `netten-tax-reserve-circle/v1`

Snapshot type: `escrow.tax_reserve`

Required fields:

- `circle_id`
- `event_id`
- `job_amount`
- `reserve_percentage`
- `reserve_amount`
- `review_window_hours`
- `review_window_closed`
- `client_disapproved_assets`
- `freelancer_or_agency`
- `client`
- `release_authority`

## Resolution Rules

- `NC-01`: Job/payment event is identified.
- `NC-02`: Reserve percentage and reserve amount match the policy artifact.
- `NC-03`: Review window is evaluated.
- `NC-04`: Client disapproval blocks release eligibility.
- `NC-05`: Release authority remains external to Ward.
- `NC-06`: Ward outputs a replayable receipt and unsigned release/block recommendation only.

## Pilot Output

A successful pilot produces:

- workflow map
- evidence snapshot
- versioned receipt
- replay comparison
- signer-boundary statement
- institution or partner review note
- trust asset candidate

## Boundary

This is a non-sensitive pilot workflow. Do not collect taxpayer identifiers, real client payment data, production signing keys, or confidential contract terms for the first test.
