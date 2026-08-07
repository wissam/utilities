"""Mutation-verify that the VEL-1441 bridge end-to-end tests exercise the real chain.

Origin: claude-code, VEL-1441 bridge slice, 2026-08-07.

Purpose: this package adds almost no logic of its own — deliberately, since the
ceremonial version was rejected in review. Its value is the end-to-end proof
that harnesshook -> spool -> harnessingest -> memoryadmit -> owner works as one
chain. So what needs verifying is not the bridge's branches but whether those
tests would notice if a layer beneath them broke.

Each case therefore breaks production code in a *dependency* and asserts the
bridge's own tests catch it. A green end-to-end suite that survives a broken
adapter would be proving nothing about integration.

Assumptions: the positional argument is a velastra worktree with the bridge
applied; `go` is on PATH. Anchors are exact source strings and go stale on
reformat; a missing anchor is reported, not skipped. The focused mutation runs
use `-buildvcs=false` because they repeatedly rewrite source in a disposable
worktree; this helper is not the verification of record, whose repository gates
must retain VCS stamping through `scripts/go-worktree-vcs.sh`.
"""

import argparse
import pathlib
import subprocess
import sys

parser = argparse.ArgumentParser(
    description="Mutation-verify VEL-1441 bridge end-to-end coverage in a disposable velastra worktree."
)
parser.add_argument("root", type=pathlib.Path, help="velastra worktree to mutate temporarily and restore")
ROOT = parser.parse_args().root.resolve()
if not (ROOT / ".git").exists():
    parser.error(f"not a Git worktree: {ROOT}")

ADMIT = ROOT / "velio/memoryadmit/admit.go"
REQUEST = ROOT / "velio/memoryadmit/request.go"
INGEST = ROOT / "velio/harnessingest/ingest.go"
BRIDGE = ROOT / "velio/harnessbridge/bridge.go"

PACKAGE = "./velio/harnessbridge/"

CASES = [
    # The adapter's replay mapping, seen from the far end of the chain.
    ("replay survives the whole chain", ADMIT,
     "\t\tDuplicate: receipt.Outcome == memoryadmissionv1.OutcomeIdempotentReplay,",
     "\t\tDuplicate: false,",
     "TestACrashBetweenAdmissionAndArchiveRedeliversAndCommitsOnce"),

    ("a typed conflict still quarantines through the chain", ADMIT,
     "\tif _, terminal := terminalErrorClasses[class]; terminal {",
     "\tif false {",
     "TestATypedConflictLeavesTheBufferForReview"),

    ("an outage still defers through the chain", ADMIT,
     '\tif _, terminal := terminalErrorClasses[class]; terminal {',
     '\tif _, terminal := terminalErrorClasses[class]; terminal || status >= 500 {',
     "TestAnOwnerOutageHoldsTheBufferAndRecovers"),

    # The adapter must reach the dedicated external-event endpoint. The fake
    # owner refuses anything else, so a wrong path fails the chain rather than
    # being quietly answered.
    ("the adapter reaches the external-event endpoint", ADMIT,
     'const admissionPath = "/v1/ingest/conversation-turn/external-event"',
     'const admissionPath = "/v1/ingest/conversation-turn"',
     "TestBothHarnessesReachTheDurableOwnerInOneShape"),

    ("the adapter posts", ADMIT,
     "http.MethodPost, a.endpoint",
     "http.MethodPut, a.endpoint",
     "TestBothHarnessesReachTheDurableOwnerInOneShape"),

    # Provenance the destination has no typed home for must survive from the
    # hook boundary all the way to the owner.
    ("provenance reaches the owner from a real hook payload", REQUEST,
     "\t\tmetaUnattributed: turn.Unattributed,",
     "\t\t// omitted",
     "TestBothHarnessesReachTheDurableOwnerInOneShape"),

    ("both harnesses are carried", REQUEST,
     "\t\t\tChannel:   turn.Harness,",
     '\t\t\tChannel:   "",',
     "TestBothHarnessesReachTheDurableOwnerInOneShape"),

    # The ingestor's archive-after-confirmation rule, seen end to end.
    ("archive happens only after confirmed admission", INGEST,
     "\tif err := i.move(item.file, i.options.SpoolDir, i.options.ArchiveDir); err != nil {",
     "\tif err := error(nil); err != nil {",
     "TestACrashBetweenAdmissionAndArchiveRedeliversAndCommitsOnce"),

    # The scoped identity, checked at the far end rather than assumed.
    #
    # These prove the complete chain refuses an omitted component. They do not
    # isolate the owner-side check: even with the stand-in's request validation
    # disabled, strict receipt decoding rejects a response that echoes an
    # invalid scope or producer. The stand-in validates too for fidelity with a
    # real owner, while the guard truthfully covers the chain as a whole.
    ("the destination scope reaches the owner", REQUEST,
     "\t\tTenantID:      strings.TrimSpace(a.config.TenantID),",
     '\t\tTenantID:      "",',
     "TestBothHarnessesReachTheDurableOwnerInOneShape"),

    # Blanks the producer namespace and neuters the adapter's request preflight.
    # The far side of the chain must still refuse it, either while admitting or
    # while strictly validating the echoed receipt.
    ("the producer namespace reaches the owner", REQUEST,
     "\tidentity := memoryadmissionv1.ExternalEventIdentity{\n"
     "\t\tSource: strings.TrimSpace(a.config.Source),\n"
     "\t\tID:     strings.TrimSpace(turn.EventID),\n"
     "\t}\n"
     "\tif err := identity.Validate(); err != nil {",
     "\tidentity := memoryadmissionv1.ExternalEventIdentity{\n"
     '\t\tSource: "",\n'
     "\t\tID:     strings.TrimSpace(turn.EventID),\n"
     "\t}\n"
     "\tif err := identity.Validate(); err != nil && false {",
     "TestBothHarnessesReachTheDurableOwnerInOneShape"),

    # The composition itself: the two directories are not interchangeable.
    ("the bridge wires the directories through", BRIDGE,
     "\t\tSpoolDir:      config.SpoolDir,",
     "\t\tSpoolDir:      config.ArchiveDir,",
     "TestBothHarnessesReachTheDurableOwnerInOneShape"),

    ("the bridge wires the durable owner through", BRIDGE,
     "\t\tAdmitter:      admitter,",
     "\t\tAdmitter:      nil,",
     "TestBothHarnessesReachTheDurableOwnerInOneShape"),
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
            ["go", "test", "-buildvcs=false", "-count=1", "-timeout", "120s", "-run", test, PACKAGE],
            cwd=ROOT, capture_output=True, text=True)
        broke = result.returncode != 0
    finally:
        path.write_text(original)
    print(f"{'CHAIN COVERED  ' if broke else 'NOT COVERED    '}{name}")
    if not broke:
        failures.append(name)

print()
print("every layer is covered end to end" if not failures else f"UNCOVERED: {failures}")
sys.exit(1 if failures else 0)
