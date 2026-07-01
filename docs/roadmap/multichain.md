# Ward Protocol — Multichain Roadmap

## Vision

Ward Protocol's nine-check deterministic resolution logic is chain-agnostic. The same invariant holds everywhere:

> `ward_signed = False — always.`

Ward never holds a signing key, never acts as a counterparty, never executes a transfer. It reads on-chain state, runs nine deterministic checks, and returns unsigned resolution data. The institution signs; the chain settles.

The multichain roadmap extends this model to every major settlement layer where RLUSD exists or will exist.

---

## Phase 1 — XRPL Mainnet (Live)

| Component | Status |
|---|---|
| Nine-check Python SDK (`ward/validator.py`) | Live |
| XRPL Python adapter (`ward/chain.py`) | Live |
| XLS-20 NFT policy certificates | Live |
| XLS-66 default flag detection | Live at mainnet launch |
| RLUSD escrow settlement | Live |

**Transport**: Native XRPL — no bridge.

---

## Phase 1.5 — Flare Network

| Component | Status |
|---|---|
| `FlareAdapter` (`ward/adapters/flare.py`) | Implemented |
| `WardResolver.sol` on Flare EVM | Pending RLUSD bridge |
| FTSO price anchoring | Available |
| Hardhat deployment guide | `docs/integration/flare.md` |

**Transport**: Native Flare EVM. RLUSD bridged from XRPL via canonical Flare bridge.

**Key advantage**: FTSO provides chain-native RLUSD price data — no external oracle dependency.

---

## Phase 2 — XRPL EVM Sidechain

| Component | Status |
|---|---|
| `WardResolver.sol` + `IWardResolver.sol` | Implemented |
| Hardhat test suite (`test/WardResolver.test.js`) | Implemented |
| `WormholeNTTAdapter` cross-chain transport | Implemented |
| `AxelarAdapter` GMP transport | Implemented |
| Deployment guide | `docs/integration/xrpl-evm.md` |

**Transport**: XRPL ↔ EVM via Axelar GMP or Wormhole NTT.

**Key advantage**: Native XRPL ecosystem — RLUSD canonical on XRPL EVM; no wrapping needed.

---

## Phase 3 — Solana

| Component | Status |
|---|---|
| `SolanaAdapter` (`ward/adapters/solana.py`) | Implemented |
| Ward Solana program (Rust) | Planned |
| RLUSD SPL mint | Pending Ripple deployment |
| Deployment guide | `docs/integration/solana.md` |

**Transport**: Wormhole NTT (RLUSD XRPL → Solana without wrapping).

**Key advantage**: 400ms finality for time-sensitive insurance claims; large DeFi liquidity base.

---

## Phase 4 — Hedera

| Component | Status |
|---|---|
| `HederaAdapter` (`ward/adapters/hedera.py`) | Implemented |
| Ward HTS contract | Planned |
| RLUSD HTS token | Pending Ripple deployment |
| Deployment guide | `docs/integration/hedera.md` |

**Transport**: Hedera Token Service native + Axelar GMP for cross-chain.

**Key advantage**: Enterprise Hashgraph consensus — deterministic finality, ABFT security. Strong institutional adoption in trade finance.

---

## Phase 5 — Stellar

| Component | Status |
|---|---|
| `StellarAdapter` (`ward/adapters/stellar.py`) | Implemented |
| Ward account data credential store | Planned |
| RLUSD Stellar asset | Pending Ripple deployment |
| Deployment guide | `docs/integration/stellar.md` |

**Transport**: Native Stellar payments. Claimable balances for dispute window.

**Key advantage**: RLUSD's natural home for cross-border payments; XLM-RLUSD liquidity pools; SEP-0031 institutional payment rails.

---

## Phase 6 — XDC Network

| Component | Status |
|---|---|
| `XDCAdapter` (`ward/adapters/xdc.py`) | Implemented |
| `WardResolver.sol` on XDC EVM | Pending RLUSD bridge |
| Deployment guide | `docs/integration/xdc.md` |

**Transport**: Native XDC EVM. RLUSD via XinFin cross-chain bridge from XRPL.

**Key advantage**: Trade finance focus — XDC's regulatory-compliant positioning aligns with Ward's institutional market.

---

## Transport Layer

### Wormhole NTT (Native Token Transfers)

- **No wrapping** — RLUSD issuer retains canonical control on every chain
- **Guardian attestation** — 19-of-19 threshold for message validity
- **Supported routes**: XRPL → Ethereum, Solana, Polygon, Avalanche, and 20+ more
- **Ward use**: Cross-chain RLUSD payout without synthetic tokens

### Axelar GMP (General Message Passing)

- **50+ chains** connected via proof-of-stake validator set
- **callContract + callContractWithToken** for arbitrary payload + token transfer
- **Ward use**: Cross-chain resolution payload relay — institution signs Gateway call; Ward never does
- **Supported routes**: XRPL EVM → Ethereum, Polygon, Arbitrum, Optimism, and 40+ more

---

## Core Invariant (All Chains)

```
ward_signed = False — always.
```

This invariant holds on every chain, in every adapter, in every struct, in every returned payload. Ward Protocol is not a counterparty. It is a resolution engine. The institution signs; the chain settles.
