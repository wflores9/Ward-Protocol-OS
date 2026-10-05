"""Wording regression guards for the OS public repo. ward_signed = False.
OS_WORDING_ROOT can point at another checkout (for example the pre-patch base 5ca3838) to see these FAIL there."""
from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(os.environ.get("OS_WORDING_ROOT") or Path(__file__).resolve().parents[1])
CUSTOMER = "Ward has no production customer deployments and no completed customer pilots as of September 2026."


def read(p: str) -> str:
    f = ROOT / p
    return f.read_text(encoding="utf-8") if f.exists() else ""


def test_commercial_md_has_no_affirmative_sla_or_certification_offer() -> None:
    t = read("COMMERCIAL.md")
    assert not re.search(r"Mainnet API with SLA|Ward-conformant certification", t)
    assert "No SLA" in t and "No certification program" in t


def test_readme_has_no_mainnet_or_verification_overclaims() -> None:
    t = read("README.md")
    assert not re.search(r"live on XRPL mainnet|tests-559|formally verified|independently verified at multiple", t, re.I)


def test_approved_customer_wording_is_exact_and_no_demo_is_called_a_customer() -> None:
    t = read("README.md")
    assert CUSTOMER in t
    assert not re.search(r"first customer|our customers|pilot customer|live with (a )?customer", t, re.I)


# SHA-256 and length of a partner name the toolkit document must not mention (the name itself is kept out of this file).
_TOOLKIT_EXCLUDED_NAME_SHA256 = "921e18803d4b44a037345951fcdf586bd8ddbf7a0e6a8f0800128402e3957956"
_TOOLKIT_EXCLUDED_NAME_LEN = 11


def test_toolkit_doc_does_not_add_a_partner_mention() -> None:
    import hashlib

    t = read("docs/security/independent-verification-toolkit.md")
    n = _TOOLKIT_EXCLUDED_NAME_LEN
    assert not any(hashlib.sha256(t[i:i + n].encode("utf-8")).hexdigest() == _TOOLKIT_EXCLUDED_NAME_SHA256 for i in range(len(t) - n + 1))
