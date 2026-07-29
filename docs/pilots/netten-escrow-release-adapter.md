# Netten Escrow Release Adapter

## Status

Prototype adapter for one narrow workflow: half-deposit services escrow with conditional release.

## Workflow

- Client deposits funds into escrow.
- Service provider renders work.
- Release is authorized by either client acceptance or an agreed release interval.
- Non-egregious disputes remain an external party issue.
- Egregious disputes block the automatic release path for external handling.
- Ward emits a replayable receipt and unsigned escrow action only.

## Boundary

Ward does not custody, sign, settle, or judge work quality. The institution or escrow authority remains the signer.

## Files

- `ward/workflows/netten_escrow_release.py`
- `examples/netten-escrow-release-input.json`
- `scripts/run_netten_escrow_release.py`
- `tests/test_netten_escrow_release.py`
- `tests/test_netten_escrow_release_cli.py`

## Next Data Needed From Netten

- Exact escrow rail and signer authority.
- Required source of truth for deposit received.
- Required source of truth for work accepted or interval elapsed.
- What qualifies as egregious dispute.
- What unsigned action should be produced for their real escrow implementation.
