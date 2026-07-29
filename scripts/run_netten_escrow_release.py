#!/usr/bin/env python3
"""Run one offline Ward Netten escrow-release resolution and emit its receipt."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ward.resolution import ResolutionError
from ward.workflows import NettenEscrowReleaseInput, resolve_netten_escrow_release

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Netten escrow-release input JSON")
    parser.add_argument("--out", type=Path, help="Write receipt to this path")
    args = parser.parse_args()

    try:
        raw = json.loads(args.input.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ResolutionError("input JSON must be an object")
        receipt = resolve_netten_escrow_release(NettenEscrowReleaseInput(**raw))
    except (OSError, json.JSONDecodeError, TypeError, ResolutionError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    rendered = json.dumps(receipt.to_dict(), indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
