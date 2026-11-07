"""The structured action proposal every agent emits, in every condition."""

from __future__ import annotations

from dataclasses import dataclass, field

_REQUIRED = {"action", "target", "agent_id"}
_OPTIONAL = {"parameters", "rationale"}


class ProposalFormatError(ValueError):
    """Raised when a proposal is not a well-formed action proposal."""


@dataclass(frozen=True)
class ActionProposal:
    action: str
    target: str
    agent_id: str
    parameters: dict = field(default_factory=dict)
    rationale: str = ""


def parse_proposal(data: object) -> ActionProposal:
    """Strictly parse a proposal. Unknown keys are rejected, not ignored."""
    if isinstance(data, ActionProposal):
        return data
    if not isinstance(data, dict):
        raise ProposalFormatError("proposal must be a JSON object")

    missing = sorted(_REQUIRED - data.keys())
    extra = sorted(data.keys() - _REQUIRED - _OPTIONAL)
    if missing:
        raise ProposalFormatError(f"proposal is missing fields: {missing}")
    if extra:
        raise ProposalFormatError(f"proposal has unexpected fields: {extra}")

    for key in ("action", "target", "agent_id"):
        if not isinstance(data[key], str) or not data[key].strip():
            raise ProposalFormatError(f"{key} must be a non-empty string")

    parameters = data.get("parameters", {})
    if not isinstance(parameters, dict):
        raise ProposalFormatError("parameters must be a JSON object")
    rationale = data.get("rationale", "")
    if not isinstance(rationale, str):
        raise ProposalFormatError("rationale must be a string")

    return ActionProposal(
        action=data["action"],
        target=data["target"],
        agent_id=data["agent_id"],
        parameters=parameters,
        rationale=rationale,
    )
