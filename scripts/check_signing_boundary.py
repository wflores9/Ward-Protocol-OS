#!/usr/bin/env python3
"""
Ward Protocol — Signing Boundary Static Check (INV-003)

Scans ward/ and sdk/python/ for forbidden signing patterns that would
violate the core invariant: Ward never holds keys, never signs transactions.

Forbidden patterns
------------------
  submit_and_wait        direct XRPL signing submission
  Wallet.from_seed       seed-based key derivation
  wallet.sign            explicit signing call
  sign_transaction       transaction signing helper
  wallet_seed            parameter name — key material at API boundary
  private_key            parameter name — raw private key at API boundary

Exemptions
----------
  Lines starting with # (comments)
  Lines in triple-quoted docstrings
  Lines containing the marker: # ward-signing-permitted
  Excluded paths (legacy / example code, not production SDK):
    sdk/python/ward_legacy/
    sdk/python/examples/
    sdk/python/tests/

Exit codes
----------
  0  No violations found
  1  One or more violations found
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SCAN_ROOTS = [
    "ward",
    "sdk/python",
]

EXCLUDED_SUBPATHS = [
    "sdk/python/ward_legacy",
    "sdk/python/examples",
    "sdk/python/tests",
]

# Pattern name → compiled regex
FORBIDDEN: list[tuple[str, re.Pattern[str]]] = [
    ("submit_and_wait",    re.compile(r'\bsubmit_and_wait\s*\(')),
    ("Wallet.from_seed",   re.compile(r'Wallet\.from_seed\b')),
    ("wallet.sign",        re.compile(r'\bwallet\.sign\b')),
    ("sign_transaction",   re.compile(r'\bsign_transaction\b')),
    ("wallet_seed param",  re.compile(r'\bwallet_seed\b')),
    ("private_key param",  re.compile(r'\bprivate_key\b')),
]

EXEMPTION_MARKER = "ward-signing-permitted"


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

def _is_excluded(path: Path, repo_root: Path) -> bool:
    rel = path.relative_to(repo_root).as_posix()
    return any(rel.startswith(exc) for exc in EXCLUDED_SUBPATHS)


def scan_file(path: Path) -> list[tuple[int, str, str]]:
    """
    Return a list of (line_number, pattern_name, line_content) violations.
    Skips comment lines, docstring lines, and lines with the exemption marker.
    """
    violations: list[tuple[int, str, str]] = []
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return violations

    lines = source.splitlines()
    in_docstring = False
    docstring_char = ""

    for lineno, raw_line in enumerate(lines, start=1):
        stripped = raw_line.strip()

        # Track triple-quoted string boundaries
        if not in_docstring:
            for dq in ('"""', "'''"):
                count = stripped.count(dq)
                if count == 1:
                    # Opening triple-quote without a matching close on the same line
                    in_docstring = True
                    docstring_char = dq
                    break
                elif count >= 2:
                    # Opened and closed on the same line — not a multi-line docstring
                    pass
        else:
            if docstring_char in stripped:
                in_docstring = False
            continue  # inside multi-line docstring — skip

        # Skip blank lines and comment lines
        if not stripped or stripped.startswith("#"):
            continue

        # Skip lines with the exemption marker
        if EXEMPTION_MARKER in raw_line:
            continue

        # Check forbidden patterns
        for name, pattern in FORBIDDEN:
            if pattern.search(raw_line):
                violations.append((lineno, name, raw_line.rstrip()))
                break  # one violation per line is enough

    return violations


def main() -> int:
    repo_root = Path(__file__).parent.parent.resolve()
    all_violations: list[tuple[Path, int, str, str]] = []

    for root_rel in SCAN_ROOTS:
        root = repo_root / root_rel
        if not root.exists():
            continue
        for py_file in sorted(root.rglob("*.py")):
            if _is_excluded(py_file, repo_root):
                continue
            for lineno, pattern_name, line in scan_file(py_file):
                rel_path = py_file.relative_to(repo_root)
                all_violations.append((rel_path, lineno, pattern_name, line))

    if all_violations:
        print("SIGNING BOUNDARY VIOLATIONS (INV-003):")
        print("=" * 60)
        for rel_path, lineno, pattern_name, line in all_violations:
            print(f"  {rel_path}:{lineno}  [{pattern_name}]")
            print(f"    {line}")
        print("=" * 60)
        print(f"\n{len(all_violations)} violation(s) found.")
        print("Ward must never hold keys, sign transactions, or accept")
        print("key material at API boundaries. To exempt a single known-good")
        print(f"call site, add:  # {EXEMPTION_MARKER}")
        return 1

    print(f"Signing boundary check passed — 0 violations in {_count_files(repo_root)} files.")
    return 0


def _count_files(repo_root: Path) -> int:
    total = 0
    for root_rel in SCAN_ROOTS:
        root = repo_root / root_rel
        if not root.exists():
            continue
        for py_file in root.rglob("*.py"):
            if not _is_excluded(py_file, repo_root):
                total += 1
    return total


if __name__ == "__main__":
    sys.exit(main())
