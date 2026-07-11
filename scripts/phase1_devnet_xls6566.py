#!/usr/bin/env python3
"""
Ward Protocol — Phase 1: XLS-65/66 Devnet Ground Truth

Creates real Vault, LoanBroker, and Loan objects on XRPL Devnet and queries
their actual JSON. This is ground truth for aligning Ward's validator to the
FINALIZED XLS-65/66 spec — not assumptions, not the draft model.

Make Waves source tag (2606260002) is attached to every transaction.

USAGE:
    python3 scripts/phase1_devnet_xls6566.py --out phase1_results.json

If any step fails, this script PRINTS THE EXACT FAILURE and STOPS. It does
not fall back to fabricated data. If XLS-65/66 transaction types aren't
supported by your installed xrpl-py version, it will tell you that plainly.
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime

DEVNET_WS = "wss://s.devnet.rippletest.net:51233"
WAVES_SOURCE_TAG = 2606260002
WARD_POLICY_TAXON = 281
TF_BURNABLE = 0x00000001
WARD_POLICY_COVERAGE_DROPS = 2_000_000
WARD_POLICY_EXPIRY_LEDGER_TIME = 999_999_999


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


async def main(out_path: str, *, stop_before_default_resolution: bool = False):
    try:
        from xrpl.asyncio.clients import AsyncWebsocketClient
        from xrpl.asyncio.wallet import generate_faucet_wallet
        from xrpl.models.requests import AccountNFTs, AccountObjects, Ledger, ServerInfo
        from xrpl.utils import str_to_hex
    except ImportError as e:
        log(f"❌ FATAL: missing xrpl-py base imports: {e}")
        log("   Run: pip install --upgrade xrpl-py")
        sys.exit(1)

    # ── Detect XLS-65/66 transaction model support ──────────────────────
    tx_models = {}
    missing_models = []
    for name in ["VaultCreate", "VaultDeposit", "LoanBrokerSet",
                 "LoanBrokerCoverDeposit", "LoanSet", "LoanManage"]:
        try:
            mod = __import__("xrpl.models.transactions", fromlist=[name])
            tx_models[name] = getattr(mod, name)
        except (ImportError, AttributeError):
            missing_models.append(name)

    if missing_models:
        log(f"WARNING: xrpl-py does not have native typed models for: {', '.join(missing_models)}")
        log("   Will build these as raw transaction dicts instead. This is normal --")
        log("   XLS-65/66 are very new and typed model support varies by version.")
    else:
        log("OK: xrpl-py has native typed models for all XLS-65/66 transaction types")

    results = {
        "meta": {
            "timestamp": datetime.now().isoformat(),
            "network": "devnet",
            "source_tag": WAVES_SOURCE_TAG,
            "typed_models_available": len(missing_models) == 0,
            "missing_models": missing_models,
            "stop_before_default_resolution": stop_before_default_resolution,
        },
        "wallets": {},
        "tx_results": {},
        "ledger_objects": {},
        "errors": [],
    }

    client = AsyncWebsocketClient(DEVNET_WS)
    try:
        await client.open()
    except Exception as e:
        log(f"FATAL: cannot connect to Devnet at {DEVNET_WS}: {e}")
        log("   This is the egress block we expect in a sandboxed environment.")
        log("   Run this on a machine with open internet access.")
        sys.exit(1)

    log(f"OK: Connected to {DEVNET_WS}")

    # ── Server info / version check ──────────────────────────────────────
    try:
        info = await client.request(ServerInfo())
        build_version = info.result.get("info", {}).get("build_version", "unknown")
        amendments = info.result.get("info", {}).get("validated_ledger", {}).get("amendments", [])
        log(f"   rippled/xrpld build: {build_version}")
        results["meta"]["build_version"] = build_version
        results["meta"]["active_amendments_count"] = len(amendments)
    except Exception as e:
        log(f"WARNING: Could not fetch server_info: {e}")

    # ── Step 1: Fund 4 wallets ──────────────────────────────────────────
    log("\nFunding 4 wallets via Devnet faucet (this can take 30-90s)...")
    roles = ["vault_owner", "depositor", "broker_owner", "borrower", "ward_pool"]
    wallets = {}
    for role in roles:
        try:
            w = await generate_faucet_wallet(client, debug=False)
            wallets[role] = w
            results["wallets"][role] = {"address": w.address, "seed": w.seed}
            log(f"   OK: {role}: {w.address}")
        except Exception as e:
            log(f"   FAILED funding {role}: {e}")
            results["errors"].append(f"funding_{role}: {str(e)}")

    if len(wallets) < 5:
        log("\nFATAL: not all wallets funded. Cannot proceed safely.")
        log(f"   Got {len(wallets)}/5. Faucet may be rate-limited -- wait and retry.")
        with open(out_path, "w") as f:
            json.dump(results, f, indent=2)
        log(f"   Partial results saved to {out_path}")
        sys.exit(1)

    # ── Helper: submit a raw or typed transaction ────────────────────────
    async def submit_tx(label, tx_dict, signer_wallet):
        tx_dict["SourceTag"] = WAVES_SOURCE_TAG
        try:
            from xrpl.models.transactions.transaction import Transaction
            from xrpl.asyncio.transaction import autofill_and_sign, submit_and_wait
            tx = Transaction.from_xrpl(json.dumps(tx_dict))
            signed = await autofill_and_sign(tx, client, signer_wallet)
            response = await submit_and_wait(signed, client)
            result = response.result
            tx_hash = result.get("hash", "unknown")
            engine_result = result.get("meta", {}).get("TransactionResult", "unknown")
            ok = engine_result == "tesSUCCESS"
            log(f"   {'OK' if ok else 'WARN'}: {label}: {engine_result} | hash={tx_hash}")
            results["tx_results"][label] = {
                "hash": tx_hash,
                "engine_result": engine_result,
                "raw": result,
            }
            return result
        except Exception as e:
            log(f"   FAILED: {label}: {e}")
            results["errors"].append(f"{label}: {str(e)}")
            results["tx_results"][label] = {"error": str(e)}
            return None

    # ── Step 2: VaultCreate ──────────────────────────────────────────────
    log("\nStep 2: VaultCreate (XLS-65)...")
    await submit_tx("VaultCreate", {
        "TransactionType": "VaultCreate",
        "Account": wallets["vault_owner"].address,
        "Asset": {"currency": "XRP"},
    }, wallets["vault_owner"])

    # ── Step 3: Find the Vault ID from account_objects ───────────────────
    log("\nStep 3: Querying vault_owner's account_objects for the new Vault...")
    vault_id = None
    try:
        obj_resp = await client.request(AccountObjects(account=wallets["vault_owner"].address))
        for obj in obj_resp.result.get("account_objects", []):
            if obj.get("LedgerEntryType") == "Vault":
                vault_id = obj.get("index")
                results["ledger_objects"]["Vault"] = obj
                log(f"   OK: Found Vault: {vault_id}")
                break
        if not vault_id:
            log("   FAILED: No Vault object found in account_objects")
            results["errors"].append("vault_not_found")
    except Exception as e:
        log(f"   FAILED: account_objects query failed: {e}")
        results["errors"].append(f"vault_query: {str(e)}")

    # ── Step 4: VaultDeposit ──────────────────────────────────────────────
    if vault_id:
        log("\nStep 4: VaultDeposit (depositor, 10 XRP)...")
        await submit_tx("VaultDeposit", {
            "TransactionType": "VaultDeposit",
            "Account": wallets["depositor"].address,
            "VaultID": vault_id,
            "Amount": "10000000",  # 10 XRP in drops
        }, wallets["depositor"])

        # ── Ward policy artifact for complete evidence --------------------
        # This is a Devnet pilot artifact signed by the test borrower wallet,
        # not by Ward. Ward's evidence runner only reads it later.
        log("\nStep 4b: Mint Ward policy NFT and pay premium memo...")
        policy_metadata = {
            "w": "ward-v1",
            "v": wallets["vault_owner"].address,
            "c": str(WARD_POLICY_COVERAGE_DROPS),
            "e": WARD_POLICY_EXPIRY_LEDGER_TIME,
            "t": "starter",
            "pa": wallets["ward_pool"].address,
        }
        uri_hex = str_to_hex(json.dumps(policy_metadata, separators=(",", ":"))).upper()
        mint_result = await submit_tx("WardPolicyNFTokenMint", {
            "TransactionType": "NFTokenMint",
            "Account": wallets["borrower"].address,
            "NFTokenTaxon": WARD_POLICY_TAXON,
            "Flags": TF_BURNABLE,
            "URI": uri_hex,
            "Memos": [
                {
                    "Memo": {
                        "MemoData": str_to_hex(
                            f"ward-policy|starter|cov={WARD_POLICY_COVERAGE_DROPS}"
                        ).upper()
                    }
                }
            ],
        }, wallets["borrower"])

        policy_nft_id = None
        if mint_result:
            try:
                nft_resp = await client.request(AccountNFTs(account=wallets["borrower"].address))
                for nft in nft_resp.result.get("account_nfts", []):
                    if (
                        nft.get("NFTokenTaxon") == WARD_POLICY_TAXON
                        and nft.get("URI", "").upper() == uri_hex
                    ):
                        policy_nft_id = nft.get("NFTokenID")
                        break
                if not policy_nft_id:
                    results["errors"].append("ward_policy_nft_not_found")
                    log("   FAILED: Ward policy NFT not found after mint")
            except Exception as e:
                results["errors"].append(f"ward_policy_nft_query: {str(e)}")
                log(f"   FAILED: Ward policy NFT query failed: {e}")

        if policy_nft_id:
            premium_memo_data = f"{policy_nft_id}:{WARD_POLICY_COVERAGE_DROPS}"
            await submit_tx("WardPolicyPremiumPayment", {
                "TransactionType": "Payment",
                "Account": wallets["borrower"].address,
                "Destination": wallets["ward_pool"].address,
                "Amount": "1",
                "Memos": [
                    {
                        "Memo": {
                            "MemoType": str_to_hex("ward/policy-premium").upper(),
                            "MemoData": str_to_hex(premium_memo_data).upper(),
                        }
                    }
                ],
            }, wallets["borrower"])

            results["ward_policy"] = {
                "policy_nft_id": policy_nft_id,
                "pool_address": wallets["ward_pool"].address,
                "claimant_address": wallets["borrower"].address,
                "defaulted_vault": wallets["vault_owner"].address,
                "coverage_drops": WARD_POLICY_COVERAGE_DROPS,
                "expiry_ledger_time": WARD_POLICY_EXPIRY_LEDGER_TIME,
                "nft_taxon": WARD_POLICY_TAXON,
                "ward_signed": False,
            }
            log(f"   OK: Ward policy NFT: {policy_nft_id}")

    # ── Step 5: LoanBrokerSet ─────────────────────────────────────────────
    broker_id = None
    if vault_id:
        log("\nStep 5: LoanBrokerSet (broker_owner, tied to vault)...")
        await submit_tx("LoanBrokerSet", {
            "TransactionType": "LoanBrokerSet",
            "Account": wallets["vault_owner"].address,
            "VaultID": vault_id,
            "DebtMaximum": "5000000",  # 5 XRP max debt
        }, wallets["vault_owner"])

        log("\nQuerying broker_owner's account_objects for the new LoanBroker...")
        try:
            obj_resp = await client.request(AccountObjects(account=wallets["vault_owner"].address))
            for obj in obj_resp.result.get("account_objects", []):
                if obj.get("LedgerEntryType") == "LoanBroker":
                    broker_id = obj.get("index")
                    results["ledger_objects"]["LoanBroker"] = obj
                    log(f"   OK: Found LoanBroker: {broker_id}")
                    break
            if not broker_id:
                log("   FAILED: No LoanBroker object found")
                results["errors"].append("loanbroker_not_found")
        except Exception as e:
            log(f"   FAILED: LoanBroker query failed: {e}")
            results["errors"].append(f"loanbroker_query: {str(e)}")

    # ── Step 6: LoanBrokerCoverDeposit (first-loss capital) ───────────────
    if broker_id:
        log("\nStep 6: LoanBrokerCoverDeposit (2 XRP first-loss cover)...")
        await submit_tx("LoanBrokerCoverDeposit", {
            "TransactionType": "LoanBrokerCoverDeposit",
            "Account": wallets["vault_owner"].address,
            "LoanBrokerID": broker_id,
            "Amount": "2000000",  # 2 XRP in drops
        }, wallets["vault_owner"])

    # ── Step 7: LoanSet (two-party CounterpartySignature flow) ────────────
    loan_id = None
    if broker_id:
        log("\nStep 7: LoanSet (broker signs first, borrower co-signs second)...")
        try:
            from xrpl.models.transactions import LoanSet
            from xrpl.asyncio.transaction import autofill_and_sign, submit_and_wait as async_submit_and_wait
            from xrpl.transaction import sign_loan_set_by_counterparty

            # Build LoanSet with ALL required fields per official XRPL docs tutorial
            loan_tx = LoanSet(
                account=wallets["vault_owner"].address,
                loan_broker_id=broker_id,
                counterparty=wallets["borrower"].address,
                principal_requested="1000000",   # 1 XRP in drops
                interest_rate=500,               # 0.5% annualised (1/10th basis points)
                payment_total=12,                # 12 payments
                payment_interval=60,             # 60 seconds (min) for testing
                grace_period=60,                 # 60 seconds grace before default allowed
                loan_origination_fee="100",      # 100 drops one-time fee
                loan_service_fee="10",           # 10 drops per payment
                source_tag=WAVES_SOURCE_TAG,
            )

            # Step 1: broker (vault_owner) autofills and signs first
            broker_signed = await autofill_and_sign(loan_tx, client, wallets["vault_owner"])
            log("   Broker signed. Adding borrower CounterpartySignature...")

            # Step 2: borrower signs second using xrpl-py's dedicated function
            # Returns SignLoanSetResult — access .signed_transaction or .tx
            fully_signed_result = sign_loan_set_by_counterparty(wallets["borrower"], broker_signed)
            if hasattr(fully_signed_result, "signed_transaction"):
                fully_signed_tx = fully_signed_result.signed_transaction
            elif hasattr(fully_signed_result, "tx"):
                fully_signed_tx = fully_signed_result.tx
            else:
                fully_signed_tx = fully_signed_result

            log("   Both parties signed. Submitting...")
            response = await async_submit_and_wait(fully_signed_tx, client)
            result = response.result
            tx_hash = result.get("hash", "unknown")
            engine_result = result.get("meta", {}).get("TransactionResult", "unknown")
            ok = engine_result == "tesSUCCESS"
            log(f"   {'OK' if ok else 'WARN'}: LoanSet: {engine_result} | hash={tx_hash}")
            results["tx_results"]["LoanSet"] = {"hash": tx_hash, "engine_result": engine_result, "raw": result}

            # Extract loan ID from AffectedNodes metadata
            if ok:
                for node in result.get("meta", {}).get("AffectedNodes", []):
                    created = node.get("CreatedNode", {})
                    if created.get("LedgerEntryType") == "Loan":
                        loan_id = created.get("LedgerIndex")
                        results["ledger_objects"]["Loan"] = created.get("NewFields", {})
                        log(f"   OK: Loan created: {loan_id}")
                        break

        except Exception as e:
            log(f"   FAILED: LoanSet: {e}")
            results["errors"].append(f"LoanSet: {str(e)}")
            results["tx_results"]["LoanSet"] = {"error": str(e)}

        if not loan_id:
            log("\nQuerying for Loan object via account_objects fallback...")
            try:
                obj_resp = await client.request(AccountObjects(account=wallets["vault_owner"].address))
                for obj in obj_resp.result.get("account_objects", []):
                    if obj.get("LedgerEntryType") == "Loan":
                        loan_id = obj.get("index")
                        results["ledger_objects"]["Loan"] = obj
                        log(f"   OK: Found Loan: {loan_id}")
                        break
                if not loan_id:
                    log("   No Loan object found")
                    results["errors"].append("loan_not_found")
            except Exception as e:
                log(f"   FAILED: Loan query: {e}")
                results["errors"].append(f"loan_query: {str(e)}")

    # ── Step 8: LoanManage (attempt default — expected to fail pre-grace) ─
    if loan_id:
        log("\nStep 8: LoanManage (attempt default -- may fail before grace period)...")
        first_manage = await submit_tx("LoanManage", {
            "TransactionType": "LoanManage",
            "Account": wallets["vault_owner"].address,
            "LoanID": loan_id,
            "Flags": 0x00010000,  # tfLoanImpair/default flow on Devnet XLS-66
        }, wallets["vault_owner"])

        if not first_manage:
            log(
                "   LoanManage returned no successful result. Waiting 150s for "
                "payment interval plus grace window, then retrying..."
            )
            await asyncio.sleep(150)
            try:
                ledger_resp = await client.request(
                    Ledger(ledger_index="validated", transactions=False, expand=False)
                )
                ledger = ledger_resp.result.get("ledger", {})
                close_time = ledger.get("close_time")
                results["meta"]["pre_resolution_ledger_index"] = ledger.get(
                    "ledger_index"
                )
                results["meta"]["pre_resolution_ledger_close_time"] = close_time
                results["meta"]["pre_resolution_ledger_close_time_iso"] = ledger.get(
                    "close_time_iso"
                )
                if close_time is not None:
                    log(f"   OK: Pre-resolution ledger close_time={close_time}")
            except Exception as e:
                log(f"   WARNING: Pre-resolution ledger query failed: {e}")

            try:
                obj_resp = await client.request(AccountObjects(account=wallets["vault_owner"].address))
                for obj in obj_resp.result.get("account_objects", []):
                    if obj.get("LedgerEntryType") == "Loan":
                        results["ledger_objects"]["Loan_pre_default_resolution"] = obj
                        log("   OK: Captured Loan before default-resolution transaction")
                        break
            except Exception as e:
                log(f"   WARNING: Pre-resolution Loan re-query failed: {e}")

            if stop_before_default_resolution:
                log("   STOP: --stop-before-default-resolution set; not submitting retry.")
                results["meta"]["default_resolution_submitted"] = False
                await client.close()
                with open(out_path, "w") as f:
                    json.dump(results, f, indent=2, default=str)
                log(f"\nPre-resolution results written to {out_path}")
                return

            await submit_tx("LoanManageRetryAfterGrace", {
                "TransactionType": "LoanManage",
                "Account": wallets["vault_owner"].address,
                "LoanID": loan_id,
                "Flags": 0x00010000,
            }, wallets["vault_owner"])
            results["meta"]["default_resolution_submitted"] = True

        # Re-query the Loan object post-attempt regardless of outcome
        try:
            obj_resp = await client.request(AccountObjects(account=wallets["vault_owner"].address))
            for obj in obj_resp.result.get("account_objects", []):
                if obj.get("LedgerEntryType") == "Loan":
                    results["ledger_objects"]["Loan_post_default_attempt"] = obj
                    break
        except Exception as e:
            log(f"   WARNING: Post-attempt Loan re-query failed: {e}")

    # ── Final output ───────────────────────────────────────────────────
    await client.close()

    log(f"\n{'='*70}")
    log(f"DONE. Errors: {len(results['errors'])}")
    if results["errors"]:
        log("Errors encountered:")
        for e in results["errors"]:
            log(f"   - {e}")
    log(f"{'='*70}")

    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    log(f"\nFull results written to {out_path}")
    log("Paste this file's contents back for cross-referencing against rippled source.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="phase1_results.json")
    parser.add_argument(
        "--stop-before-default-resolution",
        action="store_true",
        help=(
            "Wait through the payment interval plus grace window, capture the "
            "pre-resolution Loan state, write the artifact, and exit before "
            "submitting LoanManageRetryAfterGrace."
        ),
    )
    args = parser.parse_args()
    asyncio.run(
        main(
            args.out,
            stop_before_default_resolution=args.stop_before_default_resolution,
        )
    )
