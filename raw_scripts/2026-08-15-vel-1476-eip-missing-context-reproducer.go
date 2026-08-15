// Origin: Claude's independent VEL-1476 review scratch program.
// Purpose: reproduce that principalv1.Validate accepts a structurally valid
// EIP without harness, session, or turn coordinates; Velio must therefore
// enforce its own observation-context requirements.
// Assumptions: build in a temporary Go module against the reviewed
// velcontracts revision. All identifiers are synthetic.
// Limitation: this proves shared-contract acceptance only; it does not exercise
// Velidentity Core, which separately requires a harness installation.
package main

import (
	"fmt"
	"time"

	identitypb "github.com/wissam/velcontracts/gen/go/velastra/identity/v1"
	"github.com/wissam/velcontracts/identity/principalv1"
	"google.golang.org/protobuf/types/known/timestamppb"
)

func main() {
	at := time.Date(2026, 8, 15, 9, 0, 0, 0, time.UTC)

	principal := &identitypb.EffectiveInteractionPrincipal{
		SchemaVersion:      principalv1.SchemaVersion,
		CompositionKind:    identitypb.CompositionKind_COMPOSITION_KIND_PERSONAL,
		CompositionId:      "personal:synthetic",
		CompositionProfile: "personal.v1",
		Person: &identitypb.SubjectClaim{
			Resolution:   identitypb.SubjectResolutionState_SUBJECT_RESOLUTION_STATE_RESOLVED,
			SubjectId:    "person:synthetic",
			Confidence:   1,
			EvidenceRefs: []string{"identity:test:person"},
		},
		WorkspaceId: "workspace:test",
		Authentication: &identitypb.AuthenticationEvidence{
			AuthenticatedPrincipalId: "person:synthetic",
			Method:                   "fixture",
			Assurance:                "operator_managed",
			Confidence:               1,
			EvidenceRefs:             []string{"auth:test"},
			AuthenticatedAt:          timestamppb.New(at.Add(-time.Minute)),
			ExpiresAt:                timestamppb.New(at.Add(2 * time.Hour)),
		},
		AuthorizationPolicyRef:    "policy:test:authorization",
		AuthorizationPolicyDigest: "sha256:test-authorization",
		DisclosurePolicyRef:       "policy:test:disclosure",
		DisclosurePolicyDigest:    "sha256:test-disclosure",
		IssuedAt:                  timestamppb.New(at.Add(-time.Minute)),
		RevalidateAt:              timestamppb.New(at.Add(30 * time.Minute)),
		ExpiresAt:                 timestamppb.New(at.Add(time.Hour)),
		EvidenceRefs:              []string{"principal:test"},
	}

	if err := principalv1.AssignBindingID(principal); err != nil {
		fmt.Println("AssignBindingID refused it:", err)
		return
	}
	if err := principalv1.Validate(principal, at); err != nil {
		fmt.Println("Validate refused it:", err)
		return
	}

	fmt.Println("Validate accepted a principal naming no harness, session, or turn.")
	fmt.Printf("harness_kind=%q installation=%q session_id=%q turn_id=%q\n",
		principal.GetHarnessKind(), principal.GetHarnessInstallationId(),
		principal.GetSessionId(), principal.GetTurnId())
}
