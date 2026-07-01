---------------------------- MODULE ward_validator ----------------------------
(*
  Ward Protocol — Claim Validator State Machine (TLA+ Specification)

  This specification formally models the 9-step Ward Protocol claim validator
  and proves the core safety invariants:

    INV-001/003  WardNeverSigns        ward_signed = FALSE always
    INV-007      ApprovedOnlyAfter9    approved => check_step = 9
    INV-007      FailureFails          check_step < 9 /\ ~pending => ~approved

  Model-check with TLC:
    toolbox: add this file as a spec, set CONSTANTS to model values,
    verify that all three invariants hold under all reachable states.

  TLC invocation (command line):
    tlc ward_validator.tla -deadlock -config ward_validator.cfg

  Safety properties verified by TLC:
    - No state reachable where ward_signed = TRUE
    - No state reachable where approved = TRUE and check_step < 9
    - No state reachable where check_step < 9 and (approved = TRUE)
*)

EXTENDS Naturals, Sequences, FiniteSets

(* ---------------------------------------------------------------------- *)
(* CONSTANTS — override in TLC model config                               *)
(* ---------------------------------------------------------------------- *)

CONSTANTS
    ClaimId,       \* A set of claim identifiers (e.g., {"c1", "c2"})
    PolicyNFT,     \* A set of policy NFT token IDs (e.g., {"nft1"})
    VaultAddress,  \* A set of vault addresses (e.g., {"vault1"})
    LedgerState    \* A set of ledger state values (e.g., {[default |-> TRUE]})

(* ---------------------------------------------------------------------- *)
(* VARIABLES                                                              *)
(* ---------------------------------------------------------------------- *)

VARIABLES
    check_step,        \* INTEGER 0..9: steps validated so far (0 = not started)
    approved,          \* BOOLEAN: TRUE only when all 9 checks have passed
    ward_signed,       \* BOOLEAN: ALWAYS FALSE — Ward never signs anything
    rejection_reason   \* STRING: "" if pending/approved; non-empty if rejected

vars == <<check_step, approved, ward_signed, rejection_reason>>

(* ---------------------------------------------------------------------- *)
(* STATE PREDICATES                                                       *)
(* ---------------------------------------------------------------------- *)

\* Validation is in progress (not yet resolved)
Pending == rejection_reason = "" /\ ~approved

\* Validation has reached a terminal state (approved or rejected)
Terminal == approved \/ rejection_reason # ""

(* ---------------------------------------------------------------------- *)
(* TYPE INVARIANT                                                         *)
(* ---------------------------------------------------------------------- *)

TypeOK ==
    /\ check_step      \in 0..9
    /\ approved        \in BOOLEAN
    /\ ward_signed     = FALSE          \* structural — cannot be set TRUE
    /\ rejection_reason \in STRING

(* ---------------------------------------------------------------------- *)
(* INITIAL STATE                                                          *)
(* ---------------------------------------------------------------------- *)

Init ==
    /\ check_step       = 0
    /\ approved         = FALSE
    /\ ward_signed      = FALSE
    /\ rejection_reason = ""

(* ---------------------------------------------------------------------- *)
(* ACTIONS                                                                *)
(* ---------------------------------------------------------------------- *)

\* A validation step passes: advance the step counter.
\* Only possible when validation is still pending and not yet at step 9.
StepPasses ==
    /\ Pending
    /\ check_step < 9
    /\ check_step'       = check_step + 1
    /\ UNCHANGED <<approved, ward_signed, rejection_reason>>

\* A validation step fails: record the rejection and halt.
\* check_step is NOT incremented — it records how many steps passed.
\* ward_signed remains FALSE regardless of which step failed.
StepFails ==
    /\ Pending
    /\ check_step < 9
    /\ rejection_reason' \in {
           "Step1Fail: NFT not found or wrong taxon",
           "Step2Fail: Policy expired",
           "Step3Fail: Vault binding mismatch",
           "Step4Fail: Default flag not set on-chain",
           "Step5Fail: Vault loss not positive",
           "Step6Fail: Pool coverage breach",
           "Step7Fail: NFT burned",
           "Step8Fail: Claimant does not hold NFT",
           "Step9Fail: Pool insolvency or rate limit"
       }
    /\ UNCHANGED <<check_step, approved, ward_signed>>

\* All 9 checks passed: approve the claim.
\* This is the ONLY action that sets approved = TRUE.
\* check_step must equal 9 — no shortcuts.
Approve ==
    /\ Pending
    /\ check_step = 9
    /\ approved'  = TRUE
    /\ UNCHANGED <<check_step, ward_signed, rejection_reason>>

\* Stutter: terminal states are absorbing — no further transitions.
Stutter ==
    /\ Terminal
    /\ UNCHANGED vars

(* ---------------------------------------------------------------------- *)
(* NEXT-STATE RELATION                                                    *)
(* ---------------------------------------------------------------------- *)

Next ==
    \/ StepPasses
    \/ StepFails
    \/ Approve
    \/ Stutter

(* ---------------------------------------------------------------------- *)
(* FAIRNESS                                                               *)
(* ---------------------------------------------------------------------- *)

\* Weak fairness: validation always eventually completes (never stalls).
Fairness == WF_vars(Next)

(* ---------------------------------------------------------------------- *)
(* SPECIFICATION                                                          *)
(* ---------------------------------------------------------------------- *)

Spec == Init /\ [][Next]_vars /\ Fairness

(* ---------------------------------------------------------------------- *)
(* SAFETY INVARIANTS — verified by TLC                                   *)
(* ---------------------------------------------------------------------- *)

\* INV-001 / INV-003: Ward never holds signing keys and never signs.
\* ward_signed is structurally FALSE. No action can set it TRUE.
WardNeverSigns ==
    ward_signed = FALSE

\* INV-007 (forward direction): Approval is only possible after all 9 checks.
\* No state reachable where approved = TRUE and check_step < 9.
ApprovedOnlyAfterAllChecks ==
    approved => check_step = 9

\* INV-007 (contrapositive): Incomplete validation cannot produce approval.
FailureFails ==
    check_step < 9 => ~approved

\* Combined type-safety and structural invariant.
SafetyInvariant ==
    /\ TypeOK
    /\ WardNeverSigns
    /\ ApprovedOnlyAfterAllChecks
    /\ FailureFails

(* ---------------------------------------------------------------------- *)
(* LIVENESS PROPERTY                                                     *)
(* ---------------------------------------------------------------------- *)

\* Every claim validation eventually reaches a terminal state.
EventuallyTerminates ==
    <>(Terminal)

(* ---------------------------------------------------------------------- *)
(* THEOREM (informal — for documentation)                                *)
(* ---------------------------------------------------------------------- *)
(*
  THEOREM Spec => []SafetyInvariant
  Proof sketch:
    - Init establishes SafetyInvariant (check_step=0, approved=FALSE, ward_signed=FALSE)
    - StepPasses: check_step increases from i to i+1; since i<9, check_step'<=9;
      approved unchanged (FALSE); ward_signed unchanged (FALSE). Invariants hold.
    - StepFails: check_step unchanged (< 9); approved unchanged (FALSE);
      ward_signed unchanged (FALSE). Invariants hold.
    - Approve: only fires when check_step=9; sets approved'=TRUE;
      check_step'=9 satisfies ApprovedOnlyAfterAllChecks. Invariants hold.
    - Stutter: nothing changes. Invariants hold trivially.
*)

==============================================================================
