from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_netten_escrow_release.py"
EXAMPLE = ROOT / "examples" / "netten-escrow-release-input.json"

def test_netten_cli_emits_replayable_receipt() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(EXAMPLE)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    receipt = json.loads(result.stdout)

    assert receipt["schema_version"] == "ward-resolution/v1"
    assert receipt["decision"] == "approved"
    assert receipt["ward_signed"] is False
    assert receipt["case"]["workflow_type"] == "netten_escrow_release"

def test_netten_cli_fails_closed_on_bad_input(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("[]", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(bad)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert "input JSON must be an object" in result.stderr
