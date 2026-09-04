# Independent verification — WARD-DEVNET-20260901-001

XRPL Devnet only. Not production or mainnet. `ward_signed = False` always.

This certificate is **not** KV-IV-2026-0712-001. Kairo Vault's July 12, 2026
certificate remains on the public register as unreproducible/legacy
(`raw_reads_archive` null; Devnet ledger 3576434 is gone from public RPC).
No archive was fabricated for KV-IV.

## What this run is

A new Devnet lending lifecycle was created with `scripts/phase1_devnet_xls6566.py`
using ephemeral faucet wallets (vault owner, depositor, broker, borrower, pool).
Those wallets signed XLS-65/66 setup transactions. Ward did not sign.

`scripts/run_xrpl_devnet_evidence.py` then performed a read-only canonical
validation, archived raw RPC/WS reads at issuance, and emitted an unsigned
settlement packet. Settlement was not submitted.

Independent verification (`scripts/verify_devnet_evidence_independent.py`)
re-derived policy, premium, vault/loan binding, default-ready timing, payout,
solvency, and packet binding without trusting `ward_result.checks`.

## Identifiers

- Certificate: `WARD-DEVNET-20260901-001`
- Network: XRPL Devnet (`https://s.devnet.rippletest.net:51234`)
- Pinned ledger index: `4949701`
- Ledger close: `2026-09-01T05:09:42Z`
- Policy NFT: `00010000A566E82468525FD269278322F05E63B2C87398DE40913A4F004B86BB`
- Vault: `AD00F70E6A400B4293B9D669A05BE74A2D1B1317502A7A186BA0EFC12E13B438`
- LoanBroker: `0182BE39BBCEDE681F80E86879C02271AA603A0683756BF5B483351657A83827`
- Loan: `2B75A2B59766216B84C63AB2112DE792B7E99AFABB54766B07211F0B65D5F4A4`
- Pool: `rrpHG3XbdXbYL1d7CXYdT1sQ85aMas6G3u`
- Claimant: `rGnZmksFVqX2yms4tQbiZvC3VS9DTTp59X`
- Defaulted vault owner: `r31drqRzUBq391XFGWM2EZXPTbgo1k7yzW`

## Result

- Approved: yes
- Steps passed: 9 / 9
- Independently verified: yes
- Claim payout: 1000001 drops
- Vault loss: 1000001 drops
- Policy coverage: 2000000 drops
- Coverage ratio (usable / payout): 80x
- Unsigned packet present: yes
- Ward signed: no

## Archive

Complete `ward-raw-ledger-reads/v1` document:

`docs/security/evidence/archives/ward-evidence-pre-resolution-2026-09-01.raw-reads.json`

SHA-256: `967e69133e38fc296af3076b0906701b06d22d0e71ffb9aa1dc71e0661c66c04`

Weekly reproducibility re-proofs from this archive and does not query public
Devnet RPC.

## Limitations

- Devnet evidence only.
- Not a security audit or economic-design endorsement.
- Operator-run; not third-party attestation.
- Settlement packet remains unsigned and unsubmitted.
