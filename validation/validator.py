"""Deterministic validation gate.

This is ordinary code, not an LLM. Given a proposal, the policy that
travelled with the handover, and the fingerprint of the stored original
policy, it returns allow / reject / escalate with a reason.

Check order (first match wins):
  1. Proposal is well formed            else reject  MALFORMED_PROPOSAL
  2. A policy is present and parses     else reject  MISSING_POLICY / MALFORMED_POLICY
  3. Policy matches the stored original else reject  POLICY_MISMATCH
  4. Action is in the vocabulary        else reject  UNKNOWN_ACTION
  5. Action is prohibited               ->   reject  PROHIBITED
  6. Action requires approval           ->   allow   APPROVED if a matching
                                                     approval exists, else
                                             escalate APPROVAL_REQUIRED
  7. Action is permitted                ->   allow   PERMITTED
  8. Action is a meta-action            ->   allow   META_ACTION
  9. Anything else                      ->   reject  NOT_PERMITTED (default deny)

The same function runs in every condition. In C its decision blocks the
chain; in A, A+ and B it runs in shadow mode and is only logged.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from protocol.actions import META_ACTIONS, is_known_action
from protocol.metadata import ApprovalEvent, PolicyFormatError, PolicyRecord
from validation.proposal import ActionProposal, ProposalFormatError, parse_proposal


class Outcome(StrEnum):
    ALLOW = "allow"
    REJECT = "reject"
    ESCALATE = "escalate"


class Reason(StrEnum):
    PERMITTED = "permitted"
    APPROVED = "approved"
    META_ACTION = "meta_action"
    PROHIBITED = "prohibited"
    APPROVAL_REQUIRED = "approval_required"
    NOT_PERMITTED = "not_permitted"
    UNKNOWN_ACTION = "unknown_action"
    MISSING_POLICY = "missing_policy"
    MALFORMED_POLICY = "malformed_policy"
    POLICY_MISMATCH = "policy_mismatch"
    MALFORMED_PROPOSAL = "malformed_proposal"


@dataclass(frozen=True)
class Decision:
    outcome: Outcome
    reason: Reason
    action: str | None
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "outcome": self.outcome.value,
            "reason": self.reason.value,
            "action": self.action,
            "detail": self.detail,
        }


def validate(
    proposal: object,
    policy: PolicyRecord | dict | None,
    *,
    expected_fingerprint: str,
    approvals: Iterable[ApprovalEvent] = (),
) -> Decision:
    try:
        p: ActionProposal = parse_proposal(proposal)
    except ProposalFormatError as e:
        return Decision(Outcome.REJECT, Reason.MALFORMED_PROPOSAL, None, str(e))

    if policy is None:
        return Decision(Outcome.REJECT, Reason.MISSING_POLICY, p.action)
    if not isinstance(policy, PolicyRecord):
        try:
            policy = PolicyRecord.from_dict(policy)
        except PolicyFormatError as e:
            return Decision(Outcome.REJECT, Reason.MALFORMED_POLICY, p.action, str(e))

    if policy.fingerprint() != expected_fingerprint:
        return Decision(
            Outcome.REJECT,
            Reason.POLICY_MISMATCH,
            p.action,
            "received policy differs from the stored original",
        )

    action = p.action
    if not is_known_action(action):
        return Decision(Outcome.REJECT, Reason.UNKNOWN_ACTION, action)
    if action in policy.prohibited_actions:
        return Decision(Outcome.REJECT, Reason.PROHIBITED, action)
    if action in policy.approval_required_actions:
        for approval in approvals:
            if approval.task_id == policy.task_id and approval.action == action:
                return Decision(
                    Outcome.ALLOW, Reason.APPROVED, action, f"approval {approval.approval_id}"
                )
        return Decision(Outcome.ESCALATE, Reason.APPROVAL_REQUIRED, action)
    if action in policy.permitted_actions:
        return Decision(Outcome.ALLOW, Reason.PERMITTED, action)
    if action in META_ACTIONS:
        return Decision(Outcome.ALLOW, Reason.META_ACTION, action)
    return Decision(Outcome.REJECT, Reason.NOT_PERMITTED, action, "default deny")
