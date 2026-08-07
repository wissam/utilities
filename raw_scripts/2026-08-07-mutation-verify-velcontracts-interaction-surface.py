"""Mutation-verify the VEL-1430 interaction-surface guards in velcontracts.

Origin: claude-code, VEL-1430 (channel pairing, attribution/addressing split,
push-only input delivery), 2026-08-07.

Purpose: a guard nobody has watched fail proves nothing. Each of the 24 cases
breaks one rule in the schema or the semantic validator, runs only the subtest
that is supposed to catch it, and restores the file. A rule reported NO-OP GUARD
is either dead or covered only incidentally by another rule.

History, kept because it is the argument for running this at all: an earlier
revision reported NO-OP GUARD for a resolver check whose test was being
satisfied by the next check in the same function. The test was rebuilt to
isolate it; review then replaced that whole approach with reuse of the real
validators, and the check no longer exists. Neither the masked guard nor its
replacement is in the case list below.

Assumptions: the required positional argument is a velcontracts worktree with
the VEL-1430 change applied; `go` is on PATH. Mutation anchors are exact source
strings, so they go stale as soon as the surrounding code is reformatted — a
missing anchor is reported, not silently skipped.

Limitations: restores by rewriting the original text, so a concurrent editor
would lose changes. Point ROOT at a worktree, not a shared checkout.
"""

import argparse
import pathlib
import subprocess
import sys

parser = argparse.ArgumentParser(
    description="Mutation-verify VEL-1430 interaction-surface guards in a disposable velcontracts worktree."
)
parser.add_argument(
    "root",
    type=pathlib.Path,
    help="velcontracts worktree to mutate temporarily and restore after each case",
)
ROOT = parser.parse_args().root.resolve()
if not (ROOT / ".git").exists():
    parser.error(f"not a Git worktree: {ROOT}")
GO = ROOT / "plugin/manifestv1/manifest.go"
SCHEMA = ROOT / "schemas/velastra/plugin/v1/plugin_manifest.schema.json"

CASES = [
    ("output-only attribution forbidden", GO,
     "\t\tif surface.Attribution != nil {\n\t\t\treturn fmt.Errorf(\n\t\t\t\t\"capability %q output-only surface must not declare attribution",
     "\t\tif false {\n\t\t\treturn fmt.Errorf(\n\t\t\t\t\"capability %q output-only surface must not declare attribution",
     "TestPluginManifestSemanticValidationRejectsContradictions/output-only_surface_claims_a_sender"),

    ("push-only input delivery", GO,
     "\t\tif surface.InputDelivery != \"push\" {",
     "\t\tif false {",
     "TestPluginManifestSemanticValidationRejectsContradictions/poll-shaped_ingestion"),

    ("input-only addressing forbidden", GO,
     "\t} else if surface.Addressing != nil {",
     "\t} else if false {",
     "TestPluginManifestSemanticValidationRejectsContradictions/input-only_surface_resolves_recipients"),

    ("addressing required on output", GO,
     "\t\tif surface.Addressing == nil {",
     "\t\tif false {",
     "TestPluginManifestSemanticValidationRejectsContradictions/output-carrying_surface_without_addressing"),

    ("conduit must pass addressing through", GO,
     "\t\tif surface.RouteRole != \"endpoint\" && addressing.Method != \"passthrough\" {",
     "\t\tif false {",
     "TestPluginManifestSemanticValidationRejectsContradictions/conduit_resolves_its_own_recipient"),

    ("endpoint must resolve its own recipient", GO,
     "\t\tif surface.RouteRole == \"endpoint\" && addressing.Method == \"passthrough\" {",
     "\t\tif false {",
     "TestPluginManifestSemanticValidationRejectsContradictions/endpoint_passes_addressing_through"),

    ("group needs two members", GO,
     "\t\tif len(members) < 2 {",
     "\t\tif false {",
     "TestPairingGroupsMustDescribeACoherentChannel/group_with_nothing_to_complement"),

    ("group must span directions", GO,
     "\t\tif !carriesInput || !carriesOutput {",
     "\t\tif false {",
     "TestPairingGroupsMustDescribeACoherentChannel/group_covers_only_one_direction"),

    ("group route roles uniform", GO,
     "\t\t\tif surface.RouteRole != routeRole {",
     "\t\t\tif false {",
     "TestPairingGroupsMustDescribeACoherentChannel/group_is_terminal_and_intermediate_at_once"),

    ("one reply target per group", GO,
     "\t\tif len(replyAddressable) > 1 {",
     "\t\tif false {",
     "TestPairingGroupsMustDescribeACoherentChannel/group_offers_two_reply_targets"),

    ("resolver refuses ambiguity", GO,
     "\tif len(eligible) > 1 {\n\t\treturn Capability{}, fmt.Errorf(\"%w: %q\", ErrAmbiguousReplySurface, group)",
     "\tif false {\n\t\treturn Capability{}, fmt.Errorf(\"%w: %q\", ErrAmbiguousReplySurface, group)",
     "TestReplySurfaceResolutionRefusesRatherThanGuesses/two_surfaces_could_carry_the_reply"),

    ("resolver applies the group rules", GO,
     "\tif err := validatePairingGroups(map[string][]Capability{group: members}); err != nil {",
     "\tif err := validatePairingGroups(map[string][]Capability{}); err != nil {",
     "TestReplySurfaceResolutionRefusesRatherThanGuesses/lone_bidirectional_member_paired_to_itself"),

    ("resolver applies the surface rules", GO,
     "\tfor _, member := range members {\n\t\tif err := validateInteractionSurface(",
     "\tfor _, member := range []Capability(nil) {\n\t\tif err := validateInteractionSurface(",
     "TestReplySurfaceResolutionRefusesRatherThanGuesses/declared_reply_target_resolves_no_recipient"),

    ("resolver requires an origin that receives", GO,
     '\tif surface.Direction != "input" && surface.Direction != "bidirectional" {',
     "\tif false {",
     "TestReplySurfaceResolutionRefusesRatherThanGuesses/origin_receives_nothing"),

    ("attribution omitted when absent", GO,
     '`json:"attribution,omitempty"`',
     '`json:"attribution"`',
     "TestInteractionSurfacesSerializeBackToASchemaValidShape"),

    ("addressing omitted when absent", GO,
     '`json:"addressing,omitempty"`',
     '`json:"addressing"`',
     "TestInteractionSurfacesSerializeBackToASchemaValidShape"),

    ("input_delivery omitted when absent", GO,
     '`json:"input_delivery,omitempty"`',
     '`json:"input_delivery"`',
     "TestInteractionSurfacesSerializeBackToASchemaValidShape"),

    ("pairing omitted when absent", GO,
     '`json:"pairing,omitempty"`',
     '`json:"pairing"`',
     "TestInteractionSurfacesSerializeBackToASchemaValidShape"),

    ("input subject kinds omitted when absent", GO,
     '`json:"input_subject_kinds,omitempty"`',
     '`json:"input_subject_kinds"`',
     "TestInteractionSurfacesSerializeBackToASchemaValidShape"),

    ("output subject kinds omitted when absent", GO,
     '`json:"output_subject_kinds,omitempty"`',
     '`json:"output_subject_kinds"`',
     "TestInteractionSurfacesSerializeBackToASchemaValidShape"),

    ("schema forbids output attribution", SCHEMA,
     '              {"not": {"required": ["attribution"]}},\n',
     "",
     "TestPluginManifestRejectsContractDriftAndUnsafeShapes/output-only_surface_claims_a_sender"),

    ("schema requires addressing on output", SCHEMA,
     '"then": {"required": ["output_subject_kinds", "addressing"]}',
     '"then": {"required": ["output_subject_kinds"]}',
     "TestPluginManifestRejectsContractDriftAndUnsafeShapes/output_surface_without_addressing"),

    ("schema pins input delivery to push", SCHEMA,
     '"enum": ["push"]',
     '"type": "string"',
     "TestPluginManifestRejectsContractDriftAndUnsafeShapes/poll-shaped_ingestion"),

    ("schema seals the pairing object", SCHEMA,
     '"$comment": "Manifest-scoped grouping of the complementary capabilities that make up one channel. Composition only. Membership never makes a participant wakeable, never confers delivery authority, and is not an identity mapping.",\n          "type": "object",\n          "additionalProperties": false,',
     '"type": "object",',
     "TestPluginManifestRejectsContractDriftAndUnsafeShapes/pairing_carries_more_than_a_group"),
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
            ["go", "test", "-count=1", "-run", test, "."],
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
