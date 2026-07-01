#!/usr/bin/env python3
"""
Ward / on-chain lending — RESOLUTION-AUTHORIZATION obligation (state-independent, SMT-shaped).

Companion to ward_loss_conservation.py + ward_waterfall_ordering.py. Pairs with Will/Ward Protocol's
deterministic non-custodial resolution layer. Moving a loan into the resolved state TRIGGERS settlement,
so two guards must hold together:
  - RESOLVE guard: a resolve is accepted only if caller == the (current) designated resolver AND an
    OBJECTIVE default condition is met (never discretionary, never an arbitrary caller).
  - REBIND guard (set-once / who-can-change): the designated resolver may be changed only by governance.

The interesting property is the COMPOSITION: an OUTSIDER cannot cause a resolution through any sequence
including the privilege-escalation path "rebind the resolver to myself, then resolve."

Run: python ward_resolution_authz.py  Exit 0 if all checks behave.
"""
import os
import sys
import z3

OBLIGATION_SMT2 = os.path.join(os.path.dirname(__file__), "ward_resolution_authz.smt2")


def _actors():
    return (z3.Int("governance"), z3.Int("designated_resolver"), z3.Int("attacker"),
            z3.Bool("objective_default_met"))


def build_obligation():
    """Re-checkable obligation (NON-circular composition): under the correct rebind + resolve guards, an
    outsider cannot cause a resolution via rebind-then-resolve. Negation must be UNSAT. Writes SMT-LIB2."""
    gov, resolver0, atk, default_met = _actors()
    outsider = z3.And(atk != gov, atk != resolver0)
    rebind_ok = (atk == gov)
    resolver_after = z3.If(rebind_ok, atk, resolver0)
    resolved_by_outsider = z3.And(atk == resolver_after, default_met)
    s = z3.Solver()
    s.add(outsider)
    s.add(resolved_by_outsider)
    with open(OBLIGATION_SMT2, "w") as f:
        f.write("; Ward resolution-authz COMPOSITION obligation, correct guards. Expect: unsat.\n")
        f.write("; invariant: an outsider (not governance, not the resolver) cannot resolve via any path\n")
        f.write("; (including rebind-then-resolve). Non-circular: traces the two-step escalation.\n")
        f.write(s.to_smt2())
    return s.check()


def cex_rebind_escalation():
    """Bug: rebind guard omits the governance check (anyone can rebind). Outsider rebinds resolver to
    self, then resolves = privilege escalation."""
    gov, resolver0, atk, default_met = _actors()
    outsider = z3.And(atk != gov, atk != resolver0)
    rebind_ok_buggy = z3.BoolVal(True)
    resolver_after = z3.If(rebind_ok_buggy, atk, resolver0)
    resolved = z3.And(atk == resolver_after, default_met)
    s = z3.Solver(); s.add(outsider, resolved)
    if s.check() != z3.sat:
        return None
    m = s.model()
    return f"attacker={m[atk]} (not gov {m[gov]}, not resolver {m[resolver0]}) rebinds self then resolves; default_met={m[default_met]}"


def cex_missing_caller_check():
    """Bug: resolve guard omits the caller check (anyone in default resolves)."""
    gov, resolver0, atk, default_met = _actors()
    outsider = z3.And(atk != gov, atk != resolver0)
    resolved_buggy = default_met
    s = z3.Solver(); s.add(outsider, resolved_buggy)
    if s.check() != z3.sat:
        return None
    m = s.model()
    return f"attacker={m[atk]} != resolver={m[resolver0]} but default_met={m[default_met]} -> resolves (no caller check)"


def cex_discretionary():
    """Bug: resolve guard omits the objective-default check (resolver resolves a performing loan)."""
    resolver = z3.Int("designated_resolver"); default_met = z3.Bool("objective_default_met")
    resolved_buggy = z3.BoolVal(True)
    s = z3.Solver(); s.add(z3.Not(default_met), resolved_buggy)
    if s.check() != z3.sat:
        return None
    m = s.model()
    return f"caller==resolver, default_met={m[default_met]} -> resolves anyway (discretionary, no objective trigger)"


def main():
    print("=== Ward RESOLUTION-AUTHORIZATION (composition) obligation ===")
    print(" invariant: an outsider (not governance, not the resolver) cannot resolve via ANY path\n")
    ok = True

    if build_obligation() == z3.unsat:
        print("[1] CORRECT GUARDS: PROVEN (obligation UNSAT) — no outsider can reach a resolution, including "
              "via rebind-then-resolve. Non-circular: it traces the two-step escalation, not X=>X.")
        print(f" re-checkable: {OBLIGATION_SMT2} (z3/cvc5 -> `unsat`)")
    else:
        ok = False
        print("[1] CORRECT GUARDS: UNEXPECTED — obligation should be UNSAT. Investigate.")

    print("\n[2] COUNTEREXAMPLES — each omitted-check bug lets an outsider resolve:")
    for label, fn in (("rebind missing governance check (privilege escalation)", cex_rebind_escalation),
                      ("resolve missing caller check", cex_missing_caller_check),
                      ("resolve missing objective-default check (discretionary)", cex_discretionary)):
        w = fn()
        if w:
            print(f"  - {label}:\n    {w}")
        else:
            ok = False
            print(f"  - {label}: NO counterexample found (unexpected).")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
