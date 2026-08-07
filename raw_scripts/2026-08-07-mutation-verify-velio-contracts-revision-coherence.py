"""Mutation-verify the VEL-1443 revision-coherence guards in velio/pluginadmission.

Origin: claude-code, VEL-1443, 2026-08-07.

Purpose: the point of VEL-1443 is that a cross-repo test must not report green
or red for reasons unrelated to the revision under review. A regression that
never fails would reintroduce exactly that. Each case below breaks one property
of the resolver and runs only the test meant to catch it.

The first case is the important one: it restores the pre-fix behaviour of
resolving velcontracts by relative path, and the redirected-module regression
must fail by finding the decoy tree instead of the pinned branch.

Assumptions: the positional argument is a velastra worktree with VEL-1443
applied; `go` is on PATH. Anchors are exact source strings and go stale on
reformat; a missing anchor is reported, not skipped.
"""

import argparse
import pathlib
import subprocess
import sys

parser = argparse.ArgumentParser(
    description="Mutation-verify VEL-1443 revision-coherence guards in a disposable velastra worktree."
)
parser.add_argument("root", type=pathlib.Path, help="velastra worktree to mutate temporarily and restore")
ROOT = parser.parse_args().root.resolve()
if not (ROOT / ".git").exists():
    parser.error(f"not a Git worktree: {ROOT}")
RESOLVER = ROOT / "velio/pluginadmission/contractsroot_test.go"

PACKAGE = "./velio/pluginadmission/"

CASES = [
    ("files follow the module, not a relative guess", RESOLVER,
     "\treturn module.Dir, nil\n}",
     '\treturn filepath.Join(dir, "..", "..", "..", "velcontracts"), nil\n}',
     "TestSchemaAndFixturesFollowTheRedirectedModule"),

    ("an empty module directory is refused", RESOLVER,
     '\tif strings.TrimSpace(module.Dir) == "" {',
     "\tif false {",
     "TestResolutionFailsClosed/module_resolves_to_no_directory"),

    ("an unreadable directory is refused", RESOLVER,
     "\tinfo, err := os.Stat(module.Dir)\n\tif err != nil {",
     "\tinfo, err := os.Stat(module.Dir)\n\tif false {",
     "TestResolutionFailsClosed/directory_is_absent"),

    ("a non-directory is refused", RESOLVER,
     "\tif !info.IsDir() {",
     "\tif false {",
     "TestResolutionFailsClosed/directory_is_a_file"),

    ("a root without the artifacts is refused", RESOLVER,
     "\t\tif _, err := os.Stat(required); err != nil {",
     "\t\tif _, err := os.Stat(required); false {",
     "TestResolutionFailsClosed/directory_carries_no_artifacts"),

    ("malformed output is refused", RESOLVER,
     "\tif err := json.Unmarshal(stdout, &module); err != nil {",
     "\tif err := json.Unmarshal(stdout, &module); false {",
     "TestResolutionFailsClosed/output_is_not_json"),

    ("diagnostics stay bounded", RESOLVER,
     "\tif len(value) <= maxDiagnostic {\n\t\treturn value\n\t}",
     "\tif true {\n\t\treturn value\n\t}",
     "TestDiagnosticsAreBounded"),

    ("both artifacts derive from one root", RESOLVER,
     'func fixtureDirIn(root string) string {\n\treturn filepath.Join(root, "fixtures", "plugin", "v1")',
     'func fixtureDirIn(root string) string {\n\treturn filepath.Join("/nonexistent", "fixtures", "plugin", "v1")',
     "TestBothArtifactsShareOneRoot"),
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
