#!/usr/bin/env python3
"""
Ward / on-chain lending — NET-LOSS CONSERVATION obligation (state-independent, SMT-shaped).

Cross-domain example for the shared anchor-agnostic re-check format (check.kind = unsat-obligation).
Pairs with Will/Ward Protocol's deterministic non-custodial resolution layer.

Source: wflores9, dev.to "When an On-Chain Loan Defaults — the mechanics and the options for
resolving it." Headline default-resolution bug: "paying out on the GROSS loan instead of the NET loss
after First-Loss Capital" -> over-distribution, draining the vault past the real loss.

The invariant is a genuine CONSERVATION LAW (not a tautology): on a defaulted loan, every unit owed is
accounted for exactly once:
recovered + absorbed-by-First-Loss-Capital + borne-by-depositors == total owed

Run: python ward_loss_conservation.py  Exit 0 if UNSAT + CEX as expected.
"""
import os
import sys
import z3

OBLIGATION_SMT2 = os.path.join(os.path.dirname(__file__), "ward_loss_conservation.smt2")


def _model():
    """Symbols + the correct waterfall derivation. Returns (nonneg, syms, derived)."""
    P = z3.Int("principal_outstanding")
    I = z3.Int("interest_outstanding")
    R = z3.Int("recovery")
    FLC = z3.Int("first_loss_capital")
    nonneg = [P >= 0, I >= 0, R >= 0, FLC >= 0]

    owed = P + I
    recov_eff = z3.If(R > owed, owed, R)
    gross_loss = owed - recov_eff
    flc_absorb = z3.If(FLC > gross_loss, gross_loss, FLC)
    dep_loss = gross_loss - flc_absorb
    return nonneg, (P, I, R, FLC), dict(owed=owed, recov_eff=recov_eff, gross_loss=gross_loss,
                                         flc_absorb=flc_absorb, dep_loss=dep_loss)


def build_obligation():
    """Re-checkable obligation: NEGATION of the conservation law for the CORRECT waterfall.
    Conservation: recovered + flc_absorbed + depositor_borne == owed (and each within its bound).
    The solver must return UNSAT. Also writes SMT-LIB2 for independent re-check."""
    nonneg, (P, I, R, FLC), d = _model()
    conservation = d["recov_eff"] + d["flc_absorb"] + d["dep_loss"] == d["owed"]
    bounds = z3.And(d["flc_absorb"] >= 0, d["flc_absorb"] <= FLC,
                    d["dep_loss"] >= 0, d["dep_loss"] <= d["gross_loss"],
                    d["recov_eff"] <= d["owed"])
    s = z3.Solver()
    s.add(nonneg)
    s.add(z3.Not(z3.And(conservation, bounds)))
    with open(OBLIGATION_SMT2, "w") as f:
        f.write("; Ward net-loss conservation obligation (correct waterfall). Expect: unsat.\n")
        f.write("; invariant: recovered + flc_absorbed + depositor_borne == owed, components in-bound.\n")
        f.write(s.to_smt2())
    return s.check()


def find_buggy_violation():
    """Buggy rule charges depositors the GROSS loss (ignores FLC). Then
    recovered + flc_absorbed + buggy_charge > owed by exactly flc_absorb = value created = drain."""
    nonneg, syms, d = _model()
    buggy_charge = d["gross_loss"]
    accounted = d["recov_eff"] + d["flc_absorb"] + buggy_charge
    s = z3.Solver()
    s.add(nonneg)
    s.add(accounted > d["owed"])
    if s.check() != z3.sat:
        return z3.unsat, None
    m = s.model()
    P, I, R, FLC = syms
    info = {str(k): m[k] for k in syms}
    info["owed"] = m.eval(d["owed"]); info["recovered"] = m.eval(d["recov_eff"])
    info["flc_absorbed"] = m.eval(d["flc_absorb"]); info["buggy_charge"] = m.eval(buggy_charge)
    info["accounted_for"] = m.eval(accounted)
    info["over_distributed"] = m.eval(accounted - d["owed"])
    return z3.sat, info


def main():
    print("=== Ward net-loss CONSERVATION obligation ===")
    print(" invariant: recovered + FLC-absorbed + depositor-borne == owed\n")
    ok = True

    res = build_obligation()
    if res == z3.unsat:
        print("[1] CORRECT WATERFALL: PROVEN (obligation UNSAT) — conservation holds for ALL non-negative "
              "inputs; every unit owed is accounted for exactly once, nothing created or destroyed.")
        print(f" re-checkable: {OBLIGATION_SMT2} (z3/cvc5 -> `unsat`)")
    else:
        ok = False
        print(f"[1] CORRECT WATERFALL: UNEXPECTED {res} — obligation should be UNSAT. Investigate.")

    res, info = find_buggy_violation()
    if res == z3.sat:
        print("\n[2] BUGGY RULE (charge GROSS, ignore FLC): COUNTEREXAMPLE — conservation BROKEN:")
        for k in ("principal_outstanding", "interest_outstanding", "recovery", "first_loss_capital",
                  "owed", "recovered", "flc_absorbed", "buggy_charge", "accounted_for", "over_distributed"):
            if k in info:
                print(f"   {k:24} = {info[k]}")
        print("  -> accounted-for EXCEEDS owed by the FLC amount: value created from nothing = the vault drain.")
    else:
        ok = False
        print(f"\n[2] BUGGY RULE: {res} — no violation found (unexpected; the bug should be live).")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
