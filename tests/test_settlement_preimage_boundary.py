"""Preimage boundary for EscrowSettlement.

The class docstring must not claim "Ward NEVER learns the preimage" while finish_escrow takes
the fulfillment as input; and the method must not leak the fulfillment except inside the
unsigned EscrowFinish it exists to build. ward_signed = False — always.
"""
from __future__ import annotations

import inspect
import logging
import re

from ward import settlement
from ward.settlement import EscrowSettlement

# Structural checks on source: no network needed.


def test_docstring_does_not_make_an_unqualified_never_learns_claim() -> None:
    doc = inspect.getdoc(EscrowSettlement) or ""
    assert "Ward NEVER learns the preimage" not in doc
    assert "finish_escrow" in doc and "fulfillment" in doc and "UNSIGNED" in doc
    assert "must not call" in doc  # states the hosted-service restriction


def test_finish_escrow_takes_the_fulfillment_so_the_caveat_is_required() -> None:
    assert "fulfillment_hex" in inspect.signature(EscrowSettlement.finish_escrow).parameters


def test_finish_escrow_never_logs_or_returns_the_fulfillment_outside_the_unsigned_tx() -> None:
    src = inspect.getsource(EscrowSettlement.finish_escrow)
    for m in re.finditer(r"logger\.\w+\((?:.|\n)*?\)\n", src):
        assert "fulfillment" not in m.group(0), f"fulfillment reaches a log call: {m.group(0)!r}"
    ret = src[src.rindex("return {"):]
    assert "fulfillment" not in ret
    assert re.search(r'"ward_signed": (False|"false")', ret)


def test_no_module_level_logging_of_fulfillment() -> None:
    src = inspect.getsource(settlement)
    for m in re.finditer(r"logger\.\w+\((?:.|\n)*?\)\n", src):
        assert "fulfillment_hex" not in m.group(0) and "preimage" not in m.group(0).lower().replace("preimage_condition", "")
    assert isinstance(logging.getLogger("ward.settlement"), logging.Logger)
