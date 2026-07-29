from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_conditional_release_cli_emits_schema_versioned_receipt() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_conditional_release.py",
            "examples/conditional-release-input.json",
        ],
        cwd=Path.cwd(),
        check=True,
        capture_output=True,
        text=True,
    )
    receipt = json.loads(result.stdout)

    assert receipt["schema_version"] == "ward-resolution/v1"
    assert receipt["decision"] == "approved"
    assert receipt["ward_signed"] is False
    assert receipt["unsigned_actions"][0]["ward_signed"] is False


def test_conditional_release_cli_is_deterministic() -> None:
    command = [
        sys.executable,
        "scripts/run_conditional_release.py",
        "examples/conditional-release-input.json",
    ]
    first = subprocess.run(
        command, cwd=Path.cwd(), check=True, capture_output=True, text=True
    )
    second = subprocess.run(
        command, cwd=Path.cwd(), check=True, capture_output=True, text=True
    )

    assert json.loads(first.stdout)["receipt_hash"] == json.loads(second.stdout)[
        "receipt_hash"
    ]
