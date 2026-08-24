from __future__ import annotations

from scripts.check_certificate_reproducibility import check_index


def certificate_index() -> dict:
    return {
        "certificates": [
            {
                "certificate_id": "KV-IV-2026-0712-001",
                "artifact": "docs/pilots/xrpl-devnet-independent-verification-2026-07-12.md",
                "network": {
                    "name": "XRPL Devnet",
                    "rpc_url": "https://s.devnet.rippletest.net:51234",
                    "ledger_index": 3_576_434,
                },
            }
        ]
    }


def test_marks_available_pinned_ledger_reproducible() -> None:
    def available(_url, ledger_index):
        return {"result": {"ledger": {"ledger_index": ledger_index}}}

    status = check_index(certificate_index(), query=available)

    assert status["summary"] == {
        "total": 1,
        "reproducible": 1,
        "unreproducible": 0,
        "check_error": 0,
    }
    assert status["certificates"][0]["status"] == "reproducible"


def test_marks_lgr_not_found_unreproducible() -> None:
    def unavailable(_url, _ledger_index):
        return {
            "result": {
                "error": "lgrNotFound",
                "error_message": "ledgerNotFound",
            }
        }

    status = check_index(certificate_index(), query=unavailable)

    assert status["summary"]["unreproducible"] == 1
    assert status["certificates"][0]["status"] == "unreproducible"
    assert status["certificates"][0]["error_code"] == "lgrNotFound"


def test_transient_rpc_failure_is_not_mislabeled_unreproducible() -> None:
    def failed(_url, _ledger_index):
        raise OSError("temporary connection failure")

    status = check_index(certificate_index(), query=failed)

    assert status["summary"]["check_error"] == 1
    assert status["summary"]["unreproducible"] == 0
    assert status["certificates"][0]["status"] == "check_error"
