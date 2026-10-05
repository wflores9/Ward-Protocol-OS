# Ward Protocol

**Deterministic, non-custodial default resolution for XLS-66 lending vaults on the XRP Ledger.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/ward-protocol.svg)](https://pypi.org/project/ward-protocol/)

---

## Public Core Update - Evidence-First Resolution

Ward's public core now includes the rail-neutral resolution engine, canonical evidence snapshot schema, replayable receipts, and synthetic workflow fixtures for independent verification. The current public surface is no longer limited to XLS-66 lending: XLS-66 remains the first proving boundary, while conditional release and two synthetic workflows (an off-chain governed escrow release and a tax-reserve circle) demonstrate the same deterministic pattern across non-custodial workflows. The synthetic workflow code IDs still use the prefix `netten-`; it does not indicate a pilot, customer, or relationship.

**Positioning:** chains prove execution. Ward proves the resolution path before execution: evidence, policy, signer boundary, receipt, replay, and institution review.

Public artifacts in this repo include:

- `ward/resolution.py` - canonical `ward-resolution/v1` receipt engine
- `schemas/ward-resolution-receipt-v1.schema.json` - receipt schema
- `schemas/ward-evidence-snapshot-v1.schema.json` - evidence snapshot schema
- `ward/workflows/` - conditional release and synthetic workflow adapters (IDs prefixed `netten-`; synthetic fixtures only)
- `examples/` - replayable synthetic workflow inputs
- `scripts/verify_resolution_receipt.py` - independent hash/replay verification helper
- `docs/security/evidence/` - golden receipts, review packets, and verification manifest

**Core invariant:** `ward_signed = False`. Ward evaluates and prepares. The institution signs. The ledger or external system settles.

---

## What Ward does

When a loan in an XLS-65 Single Asset Vault defaults, someone must decide what happens next — who absorbs the loss, in what order, and how much. In most systems, that decision is made by a person or a committee. Ward removes that person.

Ward reads on-chain facts from the XRP Ledger, applies a fixed rule, and returns an unsigned resolution that any party can independently re-derive and verify. No oracle. No human judgment. No Ward signature.

**Core invariant:** `ward_signed = False`

Ward never holds keys, never signs, never custodies. It computes; it never executes. This invariant is enforced at four layers: a static signing-boundary check, property tests, a TLA+ model check of the specification, and a runtime guard. The TLA+ check covers the model, not the implementation.

---

## Architecture

Ward's validator runs 9 on-ledger checks against the XRP Ledger state:

| Step | Check |
|------|-------|
| 1 | Policy NFT exists and belongs to correct taxon |
| 2 | Policy has not expired; premium payment verified on-chain |
| 3 | NFT covers the specific defaulted vault (cross-vault claims rejected) |
| 4 | Loan default flag set on-chain; net depositor loss computed after first-loss capital |
| 5 | Vault loss is positive |
| 6 | Coverage breach check |
| 7 | Replay protection — NFT not burned |
| 8 | Claimant currently holds the NFT |
| 9 | Pool solvency check; payout capped at policy coverage |

Every step is pinned to a `ledger_hash` + `ledger_index` so any third party can replay the resolution against the XRP Ledger and confirm the outcome follows from on-chain facts.

---

## XLS Primitives

Ward is built on native XRP Ledger primitives:

| Primitive | Role |
|-----------|------|
| XLS-65 (Single Asset Vault) | Reads `AssetsAvailable`, `AssetsTotal`, `Owner` for vault state |
| XLS-66 (Lending Protocol) | Reads `Loan` and `LoanBroker` objects for default state and first-loss capital |
| XLS-70 (Credentials) | Verifies borrower and lender hold valid on-chain credentials (Step 9) |
| XLS-20 (NFTs) | Policy certificate — Ward decodes the URI to derive coverage terms |

**Current status:** a read-only XLS-70 credential check has been demonstrated against XRPL Mainnet (`mainnet_proof_xls70.py`; results in https://wardprotocol.org/status.json). Ward runs no production workflow on Mainnet. Full default resolution runs on Devnet, aligned to the finalized XLS-66 object model. Mainnet activation is pending XLS-66 — the same gate every XLS-66 application is waiting for.

---

## Formal Verification

Ward's safety core is checked at multiple levels:

**TLA+ specification** — the `ward_signed = False` invariant and the 9-step resolution flow are specified in TLA+ and checked for safety violations.

**Z3 SMT proofs** — three mechanically-verified obligations, re-checkable by anyone:

```bash
# Install z3
pip install z3-solver

# Run all three proofs (each returns UNSAT = invariant holds)
python ward_loss_conservation.py
python ward_waterfall_ordering.py
python ward_resolution_authz.py
```

| Proof | Invariant | Result |
|-------|-----------|--------|
| `ward_loss_conservation.smt2` | `recovered + FLC-absorbed + depositor-borne == owed` | UNSAT |
| `ward_waterfall_ordering.smt2` | Absolute priority: junior only paid if senior whole | UNSAT |
| `ward_resolution_authz.smt2` | No outsider can resolve via any path, including rebind-then-resolve | UNSAT |

Anyone can re-check these proofs with the commands above.

**Phase 1 Devnet verification** — Ward's validator is aligned against real XLS-65/66 Devnet objects (xrpld 3.2.0). Verified transaction hashes:

| Transaction | Hash |
|-------------|------|
| VaultCreate | `E473FE274D66DA31E2AA272042DD382678C78F96A90D1C53D3FAB117397AE617` |
| VaultDeposit | `BD6A93CBE5149835FD9268644BD220D86F77A09A63F1239C54F6BC1BBAFEF8BE` |
| LoanBrokerSet | `6BDCCA2A1706B0F9F010CB15929BA26087371A79078786FC9A30FCC5D7078B05` |
| LoanBrokerCoverDeposit | `9AB10C5F60B56B700576637EE1F281ABEEF42C40D2FE22B5899262A694AEF5DA` |
| LoanSet (CounterpartySignature) | `009B3245BC7AA75DE803D3D7ADC00F21D811481F716650E49CFEE741D5A85BBF` |

All transactions carry Make Waves source tag `2606260002`.

---

## Installation

```bash
pip install ward-protocol
```

Or from source:

```bash
git clone https://github.com/wflores9/Ward-Protocol-OS.git
cd Ward-Protocol-OS
pip install -e .
```

---

## Quick Start

```python
import asyncio
from ward import ClaimValidator

async def main():
    validator = ClaimValidator()
    result = await validator.validate_claim(
        claimant_address="r...",
        nft_token_id="...",
        defaulted_vault="r...",
        loan_id="...",
        pool_address="r...",
    )
    print(f"Approved: {result.approved}")
    print(f"Payout: {result.claim_payout_drops} drops")
    print(f"Steps passed: {result.steps_passed}/9")

asyncio.run(main())
```

---

## Testing

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

Test counts change with each release; run the suite for the current count. The June 11, 2026 security report recorded 559 Python, 22 Rust and 53 TypeScript tests.

---

## Repository Structure

```
ward/              Core Python validator (9-step resolution logic)
sdk/
  python/          Python client SDK
  typescript/      TypeScript client SDK
tests/             Full test suite
scripts/
  phase1_devnet_xls6566.py   XLS-65/66 Devnet alignment script
  check_signing_boundary.py  Signing boundary invariant check
ward_loss_conservation.py    Z3 net-loss conservation proof
ward_waterfall_ordering.py   Z3 waterfall ordering proof
ward_resolution_authz.py     Z3 resolution authorization proof
mainnet_proof.py             XLS-70/80 read-only mainnet check
INVARIANTS.md                Full invariant specification
```

---

## Licensing

Ward Protocol's core validator and SDKs are open source under the MIT License.

Ward offers scoped, non-production design-partner pilots under a signed order form. Ward has no production customer deployments and no completed customer pilots as of September 2026. There is no mainnet API, no certification program, and no SLA. See [COMMERCIAL.md](COMMERCIAL.md).

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Security issues: see [SECURITY.md](SECURITY.md).

---

## Built by

Will Flores — solo founder, Ward Protocol  
[@wardprotocol](https://x.com/wardprotocol) · [wardprotocol.org](https://www.wardprotocol.org)  
XRPL Make Waves hackathon participant · Swell 2026 Platinum
