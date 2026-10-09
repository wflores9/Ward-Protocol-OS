# Historical Devnet replay and verification boundaries

The offline replay command reads existing repository archives only:

```bash
python scripts/replay_historical_devnet.py
python scripts/replay_historical_devnet.py --require-all
```

The default command fails for corrupt, missing referenced, malformed, or semantically inconsistent archives. A certificate explicitly lacking an issuance archive is reported as `unavailable`, never passed. `--require-all` additionally exits nonzero for that legacy absence. CI publishes the complete report so a successful job cannot be mistaken for verification of every certificate.

| Certificate | Offline result | Residual limits |
| --- | --- | --- |
| KV-IV-2026-0712-001 | Unavailable | No issuance archive exists; none has been reconstructed or fabricated. |
| WARD-DEVNET-20260901-001 | Selected archived semantics replay | No consistent evaluation pin or pinned FeeSettings; historical independently-verified claim is not adopted. |
| WARD-DEVNET-20260902-001 | Selected archived semantics replay, including evaluation-pin consistency and reserve calculation | Operator archive only; not a Kairo attestation or current network verification. |

Each report explicitly sets `live_provenance_verified=false` and `independently_verified=false`. SHA-256 checks establish identity with the repository's indexed archive bytes, not authenticity of those bytes or their source.

Replayed checks cover NFT ownership/taxon, policy and loan/broker bindings, expiry and default timing, bounded payout, pool balance, and the archived premium transaction reference. Where present, evaluation ledger index/hash/validation flags and FeeSettings reserves are checked. Historical ward-v2 policies reference the premium transaction in their URI. Their pre-mint premium memo does not bind the later NFT ID: this replay does **not** claim a pass of the current ward-v1 NFT memo rule. Claim-attempt history, rate limits, full nine-step current-validator approval, signatures/Merkle proofs, third-party independence, and settlement are not established.

The report is deterministic and makes no RPC calls. Original archives, certificate hashes, and original historical receipts remain unchanged. Regression tests reject altered bytes, amounts, account ownership, premium destinations, conflicting/missing observations, ledger pins, and reserves.

## Live availability remains separate

```bash
python scripts/check_certificate_reproducibility.py \
  --status /tmp/live-certificate-status.json \
  --fail-on-unreproducible --fail-on-check-error
```

This checks historical ledger availability at the configured endpoint; it is not a full provenance proof either. A fresh local run still returned `lgrNotFound` for all three ledgers. The weekly workflow retains its visible failure behavior; offline success cannot replace or overwrite its status.

## Test inventory and dependencies

The public repository never shipped `ward.adapters`. Its 96 unsupported multi-chain test functions are preserved verbatim in `tests/legacy/adapter_tests.py.txt`, excluded from discovery by explicit archival and not counted as passing. All remaining XRPL core/adversarial tests in `tests/test_ward.py` run normally. Unit fixtures use explicit endpoints and isolated in-memory state. The live integration smoke test asserts unsigned preparation, not minted or active coverage.

The Python API imports the shipped `ward` package instead of depending on an unshipped legacy shim. CI tests both Python test directories. The integration marker remains opt-in for network independence; run the full suite with:

```bash
python -m pip install --upgrade pip
python -m pip install -e '.[dev]' -r requirements.txt
python -m pytest tests sdk/python/tests -q -m ''
```

Wrangler is pinned to 4.149.0 with regenerated dependencies (Miniflare 5.20261006.1-alpha, sharp 0.35.5, undici 7.29.1). The Miniflare version is Wrangler's own dependency, not an independently selected deployment runtime. The TypeScript SDK upgrades Jest to 30 and narrowly overrides the NYC config loader's js-yaml dependency to compatible v4 to remove the vulnerable argparse/sprintf-js chain. SDK tests, compilation, heartbeat tests, and a Wrangler dry-run exercise these updates.

Gitleaks 8.30.1 scans all fetched reachable history and the source tree. Raw scanning identified generic-api-key false positives exclusively on public `NFTokenID`/`nftoken_id` fields. The exception matches only those exact field names with 64 uppercase hex digits in JSON evidence paths; no entire file or commit is exempted. Scan results are bounded to the scanner's detection capabilities, not a guarantee that every possible secret is absent.
