# Ward Protocol — Testnet Proof

_Simulation run: 2026-03-01T19:57:34Z — 2026-03-01T19:59:31Z_
_Network: XRPL Altnet (testnet) — rippled 3.1.1_
_Wallets: rf3dH3S7JdBfSfawsxf7TFpGQ2sVtH9wva (depositor), rK4dpLy9bGVmNmnJNGzkHfNdhB7XzZh9iV (pool)_

---

## Confirmed On-Chain Transactions

All 5 transactions below can be verified on the XRPL Testnet Explorer.

### 1 — Premium Payment
**Type:** `Payment` (191 drops from depositor → insurance pool)

```
D541B6A2156E4BB3B22D9BD1D451598DF2D0387A25B73A5918A8779D76783169
```
[View on XRPL Testnet Explorer →](https://testnet.xrpl.org/transactions/D541B6A2156E4BB3B22D9BD1D451598DF2D0387A25B73A5918A8779D76783169)

### 2 — Policy NFT Mint
**Type:** `NFTokenMint` — Ward policy, taxon=281, `tfBurnable` only (non-transferable by design)

```
B323815A6C7BA98935D2C2AA3CFC94BB956E59BA716A59430F2183D2AE148CDF
```
[View on XRPL Testnet Explorer →](https://testnet.xrpl.org/transactions/B323815A6C7BA98935D2C2AA3CFC94BB956E59BA716A59430F2183D2AE148CDF)

**NFT Token ID:**
```
000100004341F329192D196167C1C6F3D728D98731BE61AE9BEE37B200E41D10
```

### 3 — Escrow Create
**Type:** `EscrowCreate` — 0.5 XRP locked with PREIMAGE-SHA-256 crypto condition + time lock

```
9BB570DBC6CB9EB11339FBBDA4920E03EC2CC49EC547CBF0D031C8AABC48B0A3
```
[View on XRPL Testnet Explorer →](https://testnet.xrpl.org/transactions/9BB570DBC6CB9EB11339FBBDA4920E03EC2CC49EC547CBF0D031C8AABC48B0A3)

**Security note:** The escrow requires *both* a time condition (finish window) and a PREIMAGE-SHA-256 crypto condition. Only the claimant holding the preimage can finish the escrow — Ward cannot front-run or redirect the payout.

### 4 — Escrow Finish
**Type:** `EscrowFinish` — 0.5 XRP payout released to depositor with valid preimage fulfillment

```
E65C35A568AE93E6D8A628F36A217DACB1B2A7E1A8F0A7B0912E510AED0A3DBB
```
[View on XRPL Testnet Explorer →](https://testnet.xrpl.org/transactions/E65C35A568AE93E6D8A628F36A217DACB1B2A7E1A8F0A7B0912E510AED0A3DBB)

### 5 — Policy NFT Burn (Replay Protection)
**Type:** `NFTokenBurn` — policy destroyed after settlement; cannot be reused

```
A5A0652C4DA629F0D46D2A3504FDC22E410848AF5D27E956E3997346A7B464D8
```
[View on XRPL Testnet Explorer →](https://testnet.xrpl.org/transactions/A5A0652C4DA629F0D46D2A3504FDC22E410848AF5D27E956E3997346A7B464D8)

Confirmed absent from `account_nfts` after burn — replay protection active.

---

## What Was Confirmed On-Chain

| Component | Status |
|-----------|--------|
| Premium payment (depositor → pool) | ✓ Confirmed |
| NFT policy mint (taxon=281, non-transferable) | ✓ Confirmed |
| NFT metadata URI within 256-byte XRPL limit | ✓ Confirmed |
| PREIMAGE-SHA-256 crypto condition on escrow | ✓ Confirmed |
| Escrow time-lock enforced by XRPL ledger time | ✓ Confirmed |
| EscrowFinish requires valid preimage (no front-running) | ✓ Confirmed |
| NFT burn as replay protection | ✓ Confirmed |
| NFT confirmed absent after burn | ✓ Confirmed |
| ClaimValidator Steps 1–3 (NFT ownership, expiry, vault) | ✓ Confirmed |
| Pool health monitoring (PoolHealthMonitor) | ✓ Confirmed |

---

## What Was Simulated (XLS-66 Not Yet on Altnet)

ClaimValidator Steps 4–9 require XLS-66 ledger objects (`Loan`, `LoanBroker`, `Vault`) which are a draft standard not yet deployed on XRPL Altnet. These steps were tested with mock fixtures in the unit test suite (75/75 passing at time of this run — current suite is 296/296 Python · 40/40 Rust · 45/45 TypeScript).

When XLS-66 is live (custom devnet or mainnet), `LedgerEntry(index=loan_id)` will return the `Loan` object and all 9 validation steps will run end-to-end.

---

## Balance Changes (Confirmed On-Chain)

| Wallet | Before | After | Change |
|--------|--------|-------|--------|
| `rf3dH3S7...` (depositor) | 101.498 XRP | 101.998 XRP | **+0.499 XRP** (payout received) |
| `rK4dpLy9...` (pool) | 98.501 XRP | 98.001 XRP | **−0.500 XRP** (payout sent + fees) |

---

## Bug Discovered During Testnet Run

**`get_ledger_time()` — rippled 3.x compatibility**

rippled 3.x removed `close_time` from `ServerInfo.validated_ledger`. The original implementation raised `LedgerError` on every real network call.

**Fix:** `get_ledger_time()` now uses `Ledger(ledger_index='validated').ledger.close_time` as the primary source, with `ServerInfo` as fallback for older nodes.

This is the only code change required to go from unit tests passing → testnet simulation passing.

---

## Reproduce

```bash
cd ward-protocol
pip install xrpl-py pytest pytest-asyncio

# Unit tests (no network)
pytest test_ward.py -v -m "not integration"  # 296/296 Python pass (75/75 at time of this testnet run)

# Testnet simulation (requires XRPL Altnet)
python testnet_sim.py
```
