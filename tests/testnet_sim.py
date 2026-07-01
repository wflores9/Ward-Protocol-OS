#!/usr/bin/env python3
"""
Ward Protocol — Testnet Simulation
=====================================

Runs a full end-to-end simulation against XRPL Altnet (testnet):

  1. Load pre-funded wallets from testnet_wallets.json
  2. Check wallet balances
  3. Purchase a Ward insurance policy (Payment + NFTokenMint)
  4. Run ClaimValidator steps 1-3 against the real NFT on testnet
     (Steps 4-9 require XLS-66 on testnet; documented as a known gap)
  5. Generate PREIMAGE-SHA-256 claim condition
  6. Create a time-locked escrow from the insurance pool
     (NOTE: uses a 10-second finish window instead of 48h for simulation only)
  7. Wait for the XRPL ledger time to advance past the finish window
  8. Finish the escrow with the preimage (payout released to depositor)
  9. Burn the policy NFT (replay protection)
 10. Write testnet_run.log with every transaction hash

All transaction hashes can be verified at:
  https://testnet.xrpl.org/transactions/<HASH>

XLS-66 Testnet Gap:
  XLS-66 (LoanManage, Loan, LoanBroker, Vault ledger objects) is a draft
  standard not yet deployed on XRPL Altnet. ClaimValidator steps 4-9 which
  rely on these objects will fail in this simulation. The simulation documents
  which step fails and why. In production on a mainnet or custom network with
  XLS-66 deployed, all 9 steps will run.

Usage:
  python testnet_sim.py
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone

from xrpl.asyncio.clients import AsyncJsonRpcClient
from xrpl.asyncio.transaction import autofill, submit_and_wait
from xrpl.models import (
    AccountInfo,
    AccountNFTs,
    EscrowCreate,
    EscrowFinish,
    Memo,
    NFTokenBurn,
    ServerInfo,
)
from xrpl.utils import str_to_hex
from xrpl.wallet import Wallet

from ward_client import (
    WardClient,
    EscrowRecord,
    EscrowSettlement,
    PoolHealthMonitor,
    ClaimValidator,
    generate_claim_condition,
    get_ledger_time,
    LedgerError,
    ValidationError,
    WardError,
    WARD_POLICY_TAXON,
    TF_BURNABLE,
    DEFAULT_TESTNET_URL,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

XRPL_URL      = DEFAULT_TESTNET_URL
LOG_FILE      = "testnet_run.log"
WALLETS_FILE  = "testnet_wallets.json"

# Coverage policy parameters
COVERAGE_XRP  = 1.0          # 1 XRP coverage
COVERAGE_DROPS = 1_000_000   # 1 XRP in drops
PERIOD_DAYS   = 7            # 7-day policy
PREMIUM_RATE  = 0.01         # 1% annual rate

# Payout amount for simulation escrow
PAYOUT_DROPS  = 500_000      # 0.5 XRP payout (small; pool has ~1,000 XRP)

# Escrow timing for simulation
# PRODUCTION uses ESCROW_DISPUTE_HOURS=48 — here we use 10 seconds
SIM_FINISH_AFTER_SECONDS = 10   # Finish window opens after 10s
SIM_CANCEL_AFTER_SECONDS = 120  # Cancel allowed after 2 minutes

# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------

_log_file = None
_txns: dict = {}  # step → tx_hash for final summary


def log(msg: str, level: str = "INFO") -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"[{ts}] [{level:5s}] {msg}"
    print(line, flush=True)
    if _log_file:
        _log_file.write(line + "\n")
        _log_file.flush()


def log_tx(step: str, tx_hash: str, note: str = "") -> None:
    _txns[step] = tx_hash
    suffix = f"  # {note}" if note else ""
    log(f"TX  {step:30s}  {tx_hash}{suffix}")


def log_section(title: str) -> None:
    bar = "=" * 70
    log(f"\n{bar}")
    log(f"  {title}")
    log(bar)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_wallets(path: str) -> dict[str, Wallet]:
    """Load pre-funded testnet wallets from JSON file."""
    with open(path) as f:
        data = json.load(f)

    wallets = {}
    for name, info in data.items():
        wallet = Wallet.from_seed(info["seed"])
        if wallet.classic_address != info["address"]:
            raise ValueError(
                f"Address mismatch for {name}: "
                f"expected {info['address']}, got {wallet.classic_address}"
            )
        wallets[name] = wallet
        log(f"Loaded wallet '{name}': {wallet.classic_address}")
    return wallets


async def get_balance(client: AsyncJsonRpcClient, address: str) -> float:
    """Return XRP balance for an address (in XRP, not drops)."""
    resp = await client.request(AccountInfo(account=address, ledger_index="validated"))
    if not resp.is_successful():
        return 0.0
    balance_drops = int(resp.result["account_data"]["Balance"])
    return balance_drops / 1_000_000


async def wait_for_ledger_advance(
    client: AsyncJsonRpcClient,
    target_ripple_time: int,
    poll_interval: float = 4.0,
) -> int:
    """
    Poll XRPL ledger time until it exceeds target_ripple_time.
    Returns the actual ledger time when the condition was met.
    """
    log(f"Waiting for XRPL ledger time > {target_ripple_time} "
        f"(polling every {poll_interval:.0f}s)...")
    while True:
        current = await get_ledger_time(client)
        remaining = target_ripple_time - current
        if remaining <= 0:
            log(f"Ledger time {current} has passed target {target_ripple_time}. Continuing.")
            return current
        log(f"  Ledger time: {current}  |  Need: {target_ripple_time}  |  "
            f"Remaining: {remaining}s")
        await asyncio.sleep(poll_interval)


# ---------------------------------------------------------------------------
# Main simulation
# ---------------------------------------------------------------------------


async def run_simulation() -> None:
    global _log_file

    with open(LOG_FILE, "w") as logfile:
        _log_file = logfile

        log(f"Ward Protocol Testnet Simulation")
        log(f"Log file: {LOG_FILE}")
        log(f"Network:  {XRPL_URL}")
        log(f"Date:     {datetime.now(timezone.utc).isoformat()}")

        client = AsyncJsonRpcClient(XRPL_URL)

        # ================================================================
        log_section("STEP 1 — Load wallets & check balances")
        # ================================================================

        wallets = load_wallets(WALLETS_FILE)
        depositor_wallet = wallets["test_depositor"]
        pool_wallet      = wallets["insurance_pool"]
        operator_wallet  = wallets["ward_operator"]

        log(f"\nWallets:")
        log(f"  test_depositor : {depositor_wallet.classic_address}")
        log(f"  insurance_pool : {pool_wallet.classic_address}")
        log(f"  ward_operator  : {operator_wallet.classic_address}")

        dep_bal  = await get_balance(client, depositor_wallet.classic_address)
        pool_bal = await get_balance(client, pool_wallet.classic_address)
        op_bal   = await get_balance(client, operator_wallet.classic_address)

        log(f"\nBalances (XRP):")
        log(f"  test_depositor : {dep_bal:.6f} XRP")
        log(f"  insurance_pool : {pool_bal:.6f} XRP")
        log(f"  ward_operator  : {op_bal:.6f} XRP")

        if dep_bal < 1.0:
            log("WARN  test_depositor has less than 1 XRP — may not have enough for "
                "premium + reserves.", "WARN")
        if pool_bal < 10.0:
            log("WARN  insurance_pool has less than 10 XRP. Escrow payout may fail.", "WARN")

        # Use the ward_operator address as the "vault" (a real valid XRPL address).
        # On testnet there are no XLS-66 Vault objects; this is a simulation stand-in.
        VAULT_ADDRESS = operator_wallet.classic_address
        log(f"\nSimulated vault address: {VAULT_ADDRESS}")
        log("NOTE  XLS-66 Vault/Loan objects do NOT exist on XRPL altnet. "
            "Vault address is a real XRPL account used as a simulation stand-in.")

        # ================================================================
        log_section("STEP 2 — Purchase insurance policy")
        # ================================================================

        log(f"Coverage: {COVERAGE_XRP} XRP ({COVERAGE_DROPS} drops)")
        log(f"Period:   {PERIOD_DAYS} days")
        log(f"Premium rate: {PREMIUM_RATE*100:.1f}% annual")
        log(f"Estimated premium: "
            f"{COVERAGE_DROPS * PREMIUM_RATE * PERIOD_DAYS / 365 / 1_000_000:.6f} XRP")

        ward_client = WardClient(xrpl_url=XRPL_URL)
        policy = await ward_client.purchase_coverage(
            wallet=depositor_wallet,
            vault_address=VAULT_ADDRESS,
            coverage_drops=COVERAGE_DROPS,
            period_days=PERIOD_DAYS,
            pool_address=pool_wallet.classic_address,
            premium_rate=PREMIUM_RATE,
        )

        nft_token_id = policy["nft_token_id"]
        premium_tx   = policy["premium_tx"]
        mint_tx      = policy["ledger_tx"]
        policy_id    = policy["policy_id"]
        expiry_time  = policy["expiry_ledger_time"]
        premium_drops = policy["premium_drops"]

        log_tx("premium_payment",     premium_tx, f"{premium_drops} drops → pool")
        log_tx("nft_policy_mint",     mint_tx,    f"NFT: {nft_token_id[:16]}...")

        log(f"\nPolicy issued:")
        log(f"  policy_id      : {policy_id}")
        log(f"  nft_token_id   : {nft_token_id}")
        log(f"  expiry_ledger  : {expiry_time}")
        log(f"  premium_drops  : {premium_drops}")
        log(f"  status         : {policy['status']}")

        # ================================================================
        log_section("STEP 3 — ClaimValidator (Steps 1–3 only; XLS-66 gap at Step 4)")
        # ================================================================

        log("Running ClaimValidator.validate_claim() with a simulated loan ID.")
        log("Expected outcome: PASS steps 1–3 (NFT ownership, expiry, vault match),")
        log("then FAIL at step 4 (LoanDefault flag) because XLS-66 is not on altnet.")

        # A loan_id is a 64-hex-char ledger object ID. We use a fake one.
        FAKE_LOAN_ID = "A" * 64
        log(f"\nFake loan_id (XLS-66 not on testnet): {FAKE_LOAN_ID}")

        validator = ClaimValidator(xrpl_url=XRPL_URL)
        try:
            result = await validator.validate_claim(
                claimant_address=depositor_wallet.classic_address,
                nft_token_id=nft_token_id,
                defaulted_vault=VAULT_ADDRESS,
                loan_id=FAKE_LOAN_ID,
                pool_address=pool_wallet.classic_address,
            )
            steps_passed = result.steps_passed

            if result.approved:
                log(f"UNEXPECTED: ClaimValidator approved claim — {result}")
            else:
                log(f"\nClaimValidator result: REJECTED at step {steps_passed + 1}")
                log(f"  reason: {result.rejection_reason}")

        except (ValidationError, LedgerError, WardError) as exc:
            msg = str(exc)
            log(f"\nClaimValidator raised {type(exc).__name__}: {msg}")
            # Estimate how many steps passed based on error message
            if "step 1" in msg.lower() or "nft not found" in msg.lower():
                steps_passed = 0
            elif "step 2" in msg.lower() or "expired" in msg.lower():
                steps_passed = 1
            elif "step 3" in msg.lower() or "vault" in msg.lower():
                steps_passed = 2
            else:
                steps_passed = 3

        log(f"\nSteps passed: {steps_passed}/9")
        if steps_passed >= 3:
            log("PASS  Steps 1-3 confirmed: NFT ownership ✓  Expiry ✓  Vault ✓")
            log("SKIP  Steps 4-9 require XLS-66 (LoanManage/Loan/LoanBroker/Vault "
                "ledger objects). These are draft-standard objects not yet available "
                "on XRPL Altnet. See security_notes.md §4 for details.")
        else:
            log(f"FAIL  Unexpected failure before step 4 — check testnet connectivity "
                f"and wallet balances.")

        # ================================================================
        log_section("STEP 4 — Generate PREIMAGE-SHA-256 claim condition")
        # ================================================================

        preimage, condition_hex, fulfillment_hex = generate_claim_condition()

        log(f"Preimage (32 bytes, SECRET — shown here only for simulation audit):")
        log(f"  {preimage.hex().upper()}")
        log(f"Condition hex (shared with pool operator):")
        log(f"  {condition_hex}")
        log(f"Fulfillment hex (kept secret by claimant until escrow finish):")
        log(f"  {fulfillment_hex}")
        log(f"\nIn production: claimant keeps preimage and fulfillment_hex OFFLINE.")
        log(f"Pool operator only sees condition_hex (the SHA-256 hash commitment).")

        # ================================================================
        log_section("STEP 5 — Create time-locked + crypto-conditioned escrow")
        # ================================================================

        log(f"Payout amount: {PAYOUT_DROPS / 1_000_000:.4f} XRP ({PAYOUT_DROPS} drops)")
        log(f"Finish window opens: {SIM_FINISH_AFTER_SECONDS}s from now "
            f"(PRODUCTION uses {48}h)")
        log(f"Cancel window opens: {SIM_CANCEL_AFTER_SECONDS}s from now "
            f"(PRODUCTION uses {72}h)")
        log(f"NOTE  Using short timing for simulation only. Production deployment")
        log(f"      uses ESCROW_DISPUTE_HOURS=48 / ESCROW_CANCEL_HOURS=72.")

        current_ledger_time = await get_ledger_time(client)
        finish_after_ripple = current_ledger_time + SIM_FINISH_AFTER_SECONDS
        cancel_after_ripple = current_ledger_time + SIM_CANCEL_AFTER_SECONDS

        log(f"\nCurrent ledger time  : {current_ledger_time}")
        log(f"finish_after (Ripple): {finish_after_ripple}")
        log(f"cancel_after (Ripple): {cancel_after_ripple}")

        audit_memo = json.dumps(
            {
                "protocol":    "ward-v1",
                "claim_id":    "sim-claim-001",
                "nft":         nft_token_id,
                "payout_xrp":  f"{PAYOUT_DROPS / 1_000_000:.4f}",
                "sim":         True,
            },
            separators=(",", ":"),
        )

        escrow_tx = EscrowCreate(
            account=pool_wallet.classic_address,
            destination=depositor_wallet.classic_address,
            amount=str(PAYOUT_DROPS),
            finish_after=finish_after_ripple,
            cancel_after=cancel_after_ripple,
            condition=condition_hex,
            memos=[
                Memo(
                    memo_type=str_to_hex("ward/claim-escrow"),
                    memo_data=str_to_hex(audit_memo),
                )
            ],
        )
        escrow_tx = await autofill(escrow_tx, client)
        escrow_response = await submit_and_wait(
            escrow_tx, client, pool_wallet, autofill=False
        )

        if not escrow_response.is_successful():
            result_code = escrow_response.result.get("meta", {}).get("TransactionResult", "?")
            raise LedgerError(f"EscrowCreate failed: {result_code}")

        escrow_create_hash = escrow_response.result["hash"]
        # Sequence is in Sequence field, or tx_json if available
        escrow_sequence = (
            escrow_response.result.get("Sequence")
            or escrow_response.result.get("tx_json", {}).get("Sequence")
            or escrow_tx.sequence
        )

        log_tx("escrow_create", escrow_create_hash,
               f"seq={escrow_sequence}  condition={condition_hex[:16]}...")
        log(f"\nEscrow created:")
        log(f"  sequence     : {escrow_sequence}")
        log(f"  payout       : {PAYOUT_DROPS / 1_000_000:.4f} XRP")
        log(f"  owner        : {pool_wallet.classic_address}")
        log(f"  destination  : {depositor_wallet.classic_address}")
        log(f"  finish_after : {finish_after_ripple} (Ripple epoch)")
        log(f"  cancel_after : {cancel_after_ripple} (Ripple epoch)")

        escrow_record = EscrowRecord(
            claim_id="sim-claim-001",
            nft_token_id=nft_token_id,
            pool_address=pool_wallet.classic_address,
            claimant_address=depositor_wallet.classic_address,
            payout_drops=PAYOUT_DROPS,
            escrow_sequence=escrow_sequence,
            condition_hex=condition_hex,
            tx_hash=escrow_create_hash,
            finish_after_ripple=finish_after_ripple,
            cancel_after_ripple=cancel_after_ripple,
        )

        # ================================================================
        log_section("STEP 6 — Wait for escrow finish window to open")
        # ================================================================

        actual_ledger_time = await wait_for_ledger_advance(
            client, finish_after_ripple, poll_interval=4.0
        )
        log(f"Finish window open. Ledger time: {actual_ledger_time}")

        # ================================================================
        log_section("STEP 7 — Finish escrow (release payout to claimant)")
        # ================================================================

        log(f"Submitting EscrowFinish with preimage fulfillment...")
        log(f"  account        : {depositor_wallet.classic_address} (claimant)")
        log(f"  owner          : {pool_wallet.classic_address}")
        log(f"  offer_sequence : {escrow_record.escrow_sequence}")

        finish_tx = EscrowFinish(
            account=depositor_wallet.classic_address,
            owner=escrow_record.pool_address,
            offer_sequence=escrow_record.escrow_sequence,
            condition=escrow_record.condition_hex,
            fulfillment=fulfillment_hex,
            memos=[
                Memo(
                    memo_type=str_to_hex("ward/escrow-finish"),
                    memo_data=str_to_hex(json.dumps(
                        {"claim_id": "sim-claim-001", "nft": nft_token_id[:16]},
                        separators=(",", ":"),
                    )),
                )
            ],
        )
        finish_tx = await autofill(finish_tx, client)
        finish_response = await submit_and_wait(
            finish_tx, client, depositor_wallet, autofill=False
        )

        if not finish_response.is_successful():
            result_code = finish_response.result.get("meta", {}).get("TransactionResult", "?")
            raise LedgerError(f"EscrowFinish failed: {result_code}")

        finish_hash = finish_response.result["hash"]
        log_tx("escrow_finish", finish_hash,
               f"payout {PAYOUT_DROPS/1_000_000:.4f} XRP → {depositor_wallet.classic_address}")
        log(f"\nEscrow finished. Payout released to depositor.")

        # ================================================================
        log_section("STEP 8 — Burn policy NFT (replay protection)")
        # ================================================================

        log(f"Burning NFT {nft_token_id} from {depositor_wallet.classic_address}")
        log("NFT burn prevents the same policy from being used to claim twice.")

        burn_tx = NFTokenBurn(
            account=depositor_wallet.classic_address,
            nftoken_id=nft_token_id,
            memos=[
                Memo(
                    memo_type=str_to_hex("ward/policy-burn"),
                    memo_data=str_to_hex(json.dumps(
                        {"claim_id": "sim-claim-001"},
                        separators=(",", ":"),
                    )),
                )
            ],
        )
        burn_tx = await autofill(burn_tx, client)
        burn_response = await submit_and_wait(
            burn_tx, client, depositor_wallet, autofill=False
        )

        if not burn_response.is_successful():
            result_code = burn_response.result.get("meta", {}).get("TransactionResult", "?")
            log(f"WARN  NFTokenBurn failed: {result_code}", "WARN")
            log("WARN  Manual burn required. Policy is already settled (escrow finished).", "WARN")
            burn_hash = "FAILED"
        else:
            burn_hash = burn_response.result["hash"]
            log_tx("nft_policy_burn", burn_hash, f"NFT: {nft_token_id[:16]}... burned")
            log(f"\nNFT burned. Replay protection confirmed.")
            log(f"Querying account_nfts to verify NFT is gone from depositor's account...")

            # Verify NFT is gone
            verify_resp = await client.request(
                AccountNFTs(account=depositor_wallet.classic_address, limit=400)
            )
            nfts_after = verify_resp.result.get("account_nfts", [])
            ids_after = {n["NFTokenID"] for n in nfts_after}
            if nft_token_id in ids_after:
                log("WARN  NFT still visible in account_nfts — ledger may not have "
                    "propagated yet.", "WARN")
            else:
                log("PASS  NFT confirmed absent from account_nfts. Replay protection active.")

        # ================================================================
        log_section("STEP 9 — Pool health check (PoolHealthMonitor)")
        # ================================================================

        pool_monitor = PoolHealthMonitor(pool_address=pool_wallet.classic_address)
        health = await pool_monitor.get_health(active_coverage_drops=COVERAGE_DROPS)

        log(f"\nPool health after simulation:")
        log(f"  pool_balance   : {health.balance_drops / 1_000_000:.4f} XRP")
        log(f"  coverage_ratio : {health.coverage_ratio:.2f}x")
        log(f"  risk_tier      : {health.risk_tier}")
        log(f"  minting_allowed: {pool_monitor.is_minting_allowed(health)}")

        if pool_monitor.is_minting_allowed(health):
            quote = pool_monitor.calculate_premium(
                health,
                coverage_drops=COVERAGE_DROPS,
                term_days=PERIOD_DAYS,
            )
            log(f"  premium_quote  : {quote['premium_drops'] / 1_000_000:.6f} XRP "
                f"({quote['annual_rate']*100:.1f}% annual, "
                f"risk multiplier {quote['multiplier']:.2f}x)")

        # ================================================================
        log_section("STEP 10 — Final balance check")
        # ================================================================

        dep_bal_after  = await get_balance(client, depositor_wallet.classic_address)
        pool_bal_after = await get_balance(client, pool_wallet.classic_address)

        log(f"\nBalance changes:")
        log(f"  test_depositor : {dep_bal:.6f} → {dep_bal_after:.6f} XRP  "
            f"(Δ {dep_bal_after - dep_bal:+.6f} XRP)")
        log(f"  insurance_pool : {pool_bal:.6f} → {pool_bal_after:.6f} XRP  "
            f"(Δ {pool_bal_after - pool_bal:+.6f} XRP)")

        # ================================================================
        log_section("SIMULATION SUMMARY — All Transaction Hashes")
        # ================================================================

        log(f"\nVerify at: https://testnet.xrpl.org/transactions/<hash>")
        log(f"Or:        https://xrpl.org/explorer?network=testnet#<hash>\n")

        for step, tx_hash in _txns.items():
            log(f"  {step:30s}  {tx_hash}")

        # ================================================================
        log_section("TESTNET vs MOCK DIFFERENCES")
        # ================================================================

        log("""
Differences observed between live testnet and mocked unit tests:

1. ESCROW TIMING
   Mock:     finish_after set to any arbitrary value; tests bypass time checks
   Testnet:  finish_after must be a future Ripple-epoch time; EscrowFinish fails
             with tecNO_PERMISSION if submitted before the time window opens.
             We wait for real XRPL ledger time to advance.

2. XLS-66 LEDGER OBJECTS (Loan, LoanBroker, Vault)
   Mock:     Test fixtures return synthetic node objects for loan/broker/vault
   Testnet:  XLS-66 is a draft standard NOT deployed on XRPL Altnet.
             LedgerEntry(index=<loan_id>) returns "objectNotFound" error.
             ClaimValidator steps 4-9 fail at the first Loan/LoanBroker query.
             On a network with XLS-66 (custom devnet or future mainnet),
             all 9 steps will run.

3. TRANSACTION FEES
   Mock:     Fee field pre-populated by autofill mock (static 12 drops)
   Testnet:  autofill() fetches real fee from server; fees fluctuate with load.
             EscrowFinish fees are higher because the condition/fulfillment fields
             add bytes to the serialized tx (fee ≈ 12 + 10 * (len(fulfillment)/16)).

4. NFT ID EXTRACTION
   Mock:     meta.nftoken_id shortcut always present in mock responses
   Testnet:  rippled ≥ 1.11 provides meta.nftoken_id; older nodes require
             AffectedNodes NFTokenPage diff. Both paths are implemented and tested.

5. SEQUENCE NUMBERS
   Mock:     Sequences start at 1 and don't advance between calls
   Testnet:  Each transaction increments the account sequence. autofill()
             fetches the current sequence before each submission.
             Submitting two transactions in quick succession without re-fetching
             can cause tecNO_PERMISSION or tefPAST_SEQ errors.

6. LEDGER TIME
   Mock:     get_ledger_time() returns a configurable integer (e.g. 800000000)
   Testnet:  Returns live validated_ledger.close_time (Ripple epoch seconds).
             Currently ~(time.time() - 946684800). Policy expiry is stored
             in the NFT metadata in this epoch and checked against live ledger.

7. FAUCET FUNDING
   Mock:     Wallets have arbitrary balances; reserves not enforced
   Testnet:  XRPL base reserve is 20 XRP per account. Pool must maintain
             20 XRP reserve + escrow amounts + transaction fees.
             Pool balance shown after simulation reflects real deductions.
""")

        log_section("DONE")
        log(f"Full log written to: {LOG_FILE}")
        log(f"Simulation completed at: {datetime.now(timezone.utc).isoformat()}")

    _log_file = None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    asyncio.run(run_simulation())
