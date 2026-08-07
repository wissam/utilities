"""Mutation-verify the VEL-1441 memory-admission adapter guards.

Origin: claude-code, VEL-1441 adapter slice, 2026-08-07.

Purpose: this adapter decides whether a conversation turn is archived, retried,
or quarantined. Each case below breaks one of those decisions and runs only the
test meant to catch it. A guard nobody has watched fail proves nothing, and the
dangerous direction here is treating a survivable failure as permanent.

Assumptions: the positional argument is a velastra worktree with the adapter
applied; `go` is on PATH. Anchors are exact source strings and go stale on
reformat; a missing anchor is reported, not skipped.
"""

import argparse
import pathlib
import subprocess
import sys

parser = argparse.ArgumentParser(
    description="Mutation-verify VEL-1441 adapter guards in a disposable velastra worktree."
)
parser.add_argument("root", type=pathlib.Path, help="velastra worktree to mutate temporarily and restore")
ROOT = parser.parse_args().root.resolve()
if not (ROOT / ".git").exists():
    parser.error(f"not a Git worktree: {ROOT}")
ADMIT = ROOT / "velio/memoryadmit/admit.go"
REQUEST = ROOT / "velio/memoryadmit/request.go"

PACKAGE = "./velio/memoryadmit/"

CASES = [
    ("a replay is reported as a duplicate", ADMIT,
     "\t\tDuplicate: receipt.Outcome == memoryadmissionv1.OutcomeIdempotentReplay,",
     "\t\tDuplicate: false,",
     "TestOutcomesBecomeDispositions/a_replay_commits_as_a_duplicate"),

    ("only typed classes are terminal", ADMIT,
     "\tif _, terminal := terminalErrorClasses[class]; terminal {",
     "\tif status == http.StatusConflict {",
     "TestOnlyTypedRejectionsAreTerminal/review_required"),

    # Restores the rule review removed: an untyped 400 must never quarantine,
    # because the destination answers unpreflightable configuration conditions
    # that way and a spool of good turns would drain on a registry entry.
    ("an untyped 400 defers", ADMIT,
     "\tif _, terminal := terminalErrorClasses[class]; terminal {",
     '\tif _, terminal := terminalErrorClasses[class]; terminal || (status == http.StatusBadRequest && class == "") {',
     "TestOnlyTypedRejectionsAreTerminal/untyped_validation_failure"),

    ("a retired subject type defers", ADMIT,
     "\tif _, terminal := terminalErrorClasses[class]; terminal {",
     "\tif _, terminal := terminalErrorClasses[class]; terminal || status == http.StatusBadRequest {",
     "TestOnlyTypedRejectionsAreTerminal/retired_subject_type"),

    ("the receipt is decoded strictly", ADMIT,
     "\treceipt, err := memoryadmissionv1.DecodeReceiptStrict(envelope.Receipt)",
     "\tvar receipt memoryadmissionv1.Receipt\n\terr = json.Unmarshal(envelope.Receipt, &receipt)",
     "TestAReceiptForSomethingElseIsRefused/unknown_receipt_field"),

    ("a missing receipt is not a success", ADMIT,
     "\tif len(envelope.Receipt) == 0 {",
     "\tif false {",
     "TestAResponseWithoutAReceiptSaysSo"),

    ("the receipt scope must match", ADMIT,
     "\tif receipt.Scope.TenantID != strings.TrimSpace(a.config.TenantID) ||",
     "\tif false ||",
     "TestAReceiptForSomethingElseIsRefused/different_tenant"),

    ("the receipt producer must match", ADMIT,
     "\tif receipt.ExternalEvent.Source != requested.Source {",
     "\tif false {",
     "TestAReceiptForSomethingElseIsRefused/different_producer"),

    ("an unrecognised author is refused", REQUEST,
     "\tif !known {",
     "\tif false {",
     "TestAMalformedRequestNeverLeaves/unrecognised_author"),

    ("a turn without an observation time is refused", REQUEST,
     "\tif turn.ObservedAt.IsZero() {",
     "\tif false {",
     "TestAMalformedRequestNeverLeaves/no_observation_time"),

    ("provenance keys are always written", REQUEST,
     "\t\tmetaUnattributed: turn.Unattributed,",
     "\t\t// omitted when false",
     "TestProvenanceIsAlwaysWritten"),

    ("continuation reaches the durable owner", REQUEST,
     "\t\tmetaContinuation: turn.Continuation,",
     "\t\tmetaContinuation: false,",
     "TestTheAdapterMapsTheContractOntoTheSeam/continuation_survives_admission"),

    ("the receipt event id must match", ADMIT,
     "\tif receipt.ExternalEvent.ID != requested.ID {",
     "\tif false {",
     "TestAReceiptForADifferentEventIsRefused"),

    ("the admission is bounded regardless of client", ADMIT,
     "\tctx, cancel := context.WithTimeout(ctx, a.timeout)",
     "\tctx, cancel := context.WithCancel(ctx)",
     "TestAdmissionIsBoundedEvenWithAnUnboundedClient"),

    ("user id reaches the wire", REQUEST,
     "\t\tUserID:        strings.TrimSpace(a.config.UserID),",
     '\t\tUserID:        "",',
     "TestTheRequestCarriesEveryFieldTheDestinationRequires"),

    ("agent id reaches the wire", REQUEST,
     "\t\tAgentID:       strings.TrimSpace(a.config.AgentID),",
     '\t\tAgentID:       "",',
     "TestTheRequestCarriesEveryFieldTheDestinationRequires"),

    ("user id is required configuration", ADMIT,
     '\t\t{"user id", c.UserID},',
     '\t\t{"user id", "default"},',
     "TestScopeAndProducerHaveNoDefaults/user"),

    ("agent id is required configuration", ADMIT,
     '\t\t{"agent id", c.AgentID},',
     '\t\t{"agent id", "default"},',
     "TestScopeAndProducerHaveNoDefaults/agent"),

    ("a sessionless turn is refused locally", REQUEST,
     '\tif strings.TrimSpace(turn.SessionID) == "" {',
     "\tif false {",
     "TestASessionlessTurnIsRefusedLocally"),

    ("scope and producer have no defaults", ADMIT,
     '\t\t{"producer source", c.Source},',
     '\t\t{"producer source", "default"},',
     "TestScopeAndProducerHaveNoDefaults/producer"),
]

failures = []
for name, path, old, new, test in CASES:
    original = path.read_text()
    if old not in original:
        failures.append(f"{name}: mutation anchor not found")
        continue
    path.write_text(original.replace(old, new, 1))
    try:
        result = subprocess.run(
            ["go", "test", "-buildvcs=false", "-count=1", "-run", test, PACKAGE],
            cwd=ROOT, capture_output=True, text=True)
        broke = result.returncode != 0
    finally:
        path.write_text(original)
    print(f"{'GUARD HELD ' if broke else 'NO-OP GUARD'}  {name}")
    if not broke:
        failures.append(name)

print()
print("all guards mutation-verified" if not failures else f"UNVERIFIED: {failures}")
sys.exit(1 if failures else 0)
