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


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


async def main(out_path: str):
    try:
        from xrpl.asyncio.clients import AsyncWebsocketClient
        from xrpl.asyncio.wallet import generate_faucet_wallet
        from xrpl.models.requests import AccountObjects, ServerInfo
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
    roles = ["vault_owner", "depositor", "broker_owner", "borrower"]
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

    if len(wallets) < 4:
        log("\nFATAL: not all wallets funded. Cannot proceed safely.")
        log(f"   Got {len(wallets)}/4. Faucet may be rate-limited -- wait and retry.")
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
        log("\nStep 8: LoanManage (attempt default -- likely fails, grace period)...")
        await submit_tx("LoanManage", {
            "TransactionType": "LoanManage",
            "Account": wallets["vault_owner"].address,
            "LoanID": loan_id,
            "Flags": 0x00010000,  # tfLoanImpair (impair first, then default after grace period)
        }, wallets["vault_owner"])
        log("   (Failure here is EXPECTED if grace period hasn't elapsed -- not fatal)")

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
    args = parser.parse_args()
    asyncio.run(main(args.out))
