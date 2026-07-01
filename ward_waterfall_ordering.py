#!/usr/bin/env python3
"""
Ward / on-chain lending — WATERFALL-ORDERING obligation (state-independent, SMT-shaped).

Companion to ward_loss_conservation.py. Pairs with Will/Ward Protocol's deterministic non-custodial
resolution layer. Default resolution distributes recovery through tranches in STRICT SENIORITY ORDER:
senior is paid first, then mezzanine, then junior/equity. The invariant ("absolute priority"):

    a tranche may receive a positive payment ONLY IF every tranche senior to it is paid IN FULL.

Run: python ward_waterfall_ordering.py  Exit 0 if UNSAT + CEX as expected.
"""
import os
import sys
import z3

OBLIGATION_SMT2 = os.path.join(os.path.dirname(__file__), "ward_waterfall_ordering.smt2")


def _model():
    """Three tranches senior>mezz>junior with claims; `avail` recovery to distribute. Correct cascade."""
    S = z3.Int("senior_claim")
    M = z3.Int("mezz_claim")
    J = z3.Int("junior_claim")
    A = z3.Int("recovery_available")
    nonneg = [S >= 0, M >= 0, J >= 0, A >= 0]

    pay_S = z3.If(A > S, S, A)
    rem1 = A - pay_S
    pay_M = z3.If(rem1 > M, M, rem1)
    rem2 = rem1 - pay_M
    pay_J = z3.If(rem2 > J, J, rem2)
    return nonneg, (S, M, J, A), dict(S=S, M=M, J=J, A=A, pay_S=pay_S, pay_M=pay_M, pay_J=pay_J)


def build_obligation():
    """Re-checkable obligation: NEGATION of absolute-priority (+ bounds + conservation) for the CORRECT
    cascade. Solver must return UNSAT. Writes SMT-LIB2 for independent re-check."""
    nonneg, _, d = _model()
    pay_S, pay_M, pay_J = d["pay_S"], d["pay_M"], d["pay_J"]
    S, M, A = d["S"], d["M"], d["A"]
    priority = z3.And(
        z3.Implies(pay_M > 0, pay_S == S),
        z3.Implies(pay_J > 0, z3.And(pay_S == S, pay_M == M)),
        pay_S >= 0, pay_M >= 0, pay_J >= 0,
        pay_S <= S, pay_M <= M, pay_J <= d["J"],
        pay_S + pay_M + pay_J <= A,
    )
    s = z3.Solver()
    s.add(nonneg)
    s.add(z3.Not(priority))
    with open(OBLIGATION_SMT2, "w") as f:
        f.write("; Ward waterfall-ordering (absolute priority) obligation, correct cascade. Expect: unsat.\n")
        f.write("; invariant: a junior tranche is paid only if every senior tranche is paid in full.\n")
        f.write(s.to_smt2())
    return s.check()


def find_buggy_violation():
    """A PRO-RATA rule splits recovery proportionally to claims (integer division). Find inputs where it
    pays the mezzanine while the senior tranche is still short = absolute-priority violation."""
    nonneg, syms, d = _model()
    S, M, J, A = syms
    total = S + M + J
    buggy_S = (A * S) / total
    buggy_M = (A * M) / total
    s = z3.Solver()
    s.add(nonneg)
    s.add(total > 0)
    s.add(buggy_M > 0)
    s.add(buggy_S < S)
    if s.check() != z3.sat:
        return z3.unsat, None
    m = s.model()
    info = {str(k): m[k] for k in syms}
    info["prorata_pay_senior"] = m.eval(buggy_S)
    info["prorata_pay_mezz"] = m.eval(buggy_M)
    info["senior_shortfall"] = m.eval(S - buggy_S)
    return z3.sat, info


def main():
    print("=== Ward WATERFALL-ORDERING (absolute priority) obligation ===")
    print(" invariant: a junior tranche is paid only if every senior tranche is paid in full\n")
    ok = True

    if build_obligation() == z3.unsat:
        print("[1] CORRECT CASCADE: PROVEN (obligation UNSAT) — absolute priority holds for ALL non-negative "
              "inputs; no junior tranche is paid while a senior tranche is short (+ no overpay, + conservation).")
        print(f" re-checkable: {OBLIGATION_SMT2} (z3/cvc5 -> `unsat`)")
    else:
        ok = False
        print("[1] CORRECT CASCADE: UNEXPECTED — obligation should be UNSAT. Investigate.")

    res, info = find_buggy_violation()
    if res == z3.sat:
        print("\n[2] PRO-RATA RULE (split proportionally to claims): COUNTEREXAMPLE — priority BROKEN:")
        for k in ("senior_claim", "mezz_claim", "junior_claim", "recovery_available",
                  "prorata_pay_senior", "prorata_pay_mezz", "senior_shortfall"):
            if k in info:
                print(f"   {k:22} = {info[k]}")
        print("  -> mezzanine receives a payment while the senior tranche is still short = absolute-priority breach.")
    else:
        ok = False
        print("\n[2] PRO-RATA RULE: no violation found (unexpected).")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
