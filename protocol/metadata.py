"""The policy record: the original task's intent and constraints.

The policy record is immutable and kept separate from the mutable handover
trace (depth, agents, validation results). Agents may add context in their
messages, but the policy record itself is never rewritten during delegation.
An authorised change is represented as a separate ApprovalEvent.

Tamper detection compares a received policy against the fingerprint of the
stored original. This detects changes to the record; it is NOT a
cryptographic integrity guarantee (no signatures, no key management).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from protocol.actions import is_known_action

METADATA_VERSION = "0.1"

_POLICY_KEYS = {
    "metadata_version",
    "task_id",
    "original_intent",
    "permitted_actions",
    "prohibited_actions",
    "approval_required_actions",
}


class PolicyFormatError(ValueError):
    """Raised when a policy record is missing fields, malformed or contradictory."""


@dataclass(frozen=True)
class PolicyRecord:
    task_id: str
    original_intent: str
    permitted_actions: frozenset[str]
    prohibited_actions: frozenset[str]
    approval_required_actions: frozenset[str]
    metadata_version: str = METADATA_VERSION

    def __post_init__(self) -> None:
        for name in ("task_id", "original_intent"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise PolicyFormatError(f"{name} must be a non-empty string")

        lists = {
            "permitted_actions": self.permitted_actions,
            "prohibited_actions": self.prohibited_actions,
            "approval_required_actions": self.approval_required_actions,
        }
        for name, actions in lists.items():
            if not isinstance(actions, frozenset):
                raise PolicyFormatError(f"{name} must be a frozenset")
            unknown = sorted(a for a in actions if not is_known_action(a))
            if unknown:
                raise PolicyFormatError(f"{name} contains unknown actions: {unknown}")

        # Each action may appear in at most one list, so precedence is never
        # needed to resolve a contradiction inside a single policy.
        names = list(lists)
        for i, a in enumerate(names):
            for b in names[i + 1 :]:
                overlap = sorted(lists[a] & lists[b])
                if overlap:
                    raise PolicyFormatError(f"actions in both {a} and {b}: {overlap}")

    def to_dict(self) -> dict:
        return {
            "metadata_version": self.metadata_version,
            "task_id": self.task_id,
            "original_intent": self.original_intent,
            "permitted_actions": sorted(self.permitted_actions),
            "prohibited_actions": sorted(self.prohibited_actions),
            "approval_required_actions": sorted(self.approval_required_actions),
        }

    @classmethod
    def from_dict(cls, data: object) -> PolicyRecord:
        if not isinstance(data, dict):
            raise PolicyFormatError("policy must be a JSON object")
        missing = sorted(_POLICY_KEYS - data.keys())
        extra = sorted(data.keys() - _POLICY_KEYS)
        if missing:
            raise PolicyFormatError(f"policy is missing fields: {missing}")
        if extra:
            raise PolicyFormatError(f"policy has unexpected fields: {extra}")

        def as_set(key: str) -> frozenset[str]:
            value = data[key]
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise PolicyFormatError(f"{key} must be a list of strings")
            return frozenset(value)

        return cls(
            task_id=data["task_id"],
            original_intent=data["original_intent"],
            permitted_actions=as_set("permitted_actions"),
            prohibited_actions=as_set("prohibited_actions"),
            approval_required_actions=as_set("approval_required_actions"),
            metadata_version=data["metadata_version"],
        )

    def fingerprint(self) -> str:
        canonical = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True)
class ApprovalEvent:
    """A predefined, synthetic human approval for one action on one task.

    Approvals only unlock approval-required actions. They never unlock a
    prohibited action.
    """

    approval_id: str
    task_id: str
    action: str
    approved_by: str
