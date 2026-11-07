import pytest

from protocol.metadata import ApprovalEvent, PolicyFormatError, PolicyRecord
from validation.proposal import ProposalFormatError, parse_proposal
from validation.validator import Outcome, Reason, validate


@pytest.fixture
def policy() -> PolicyRecord:
    return PolicyRecord(
        task_id="TASK-001",
        original_intent="Analyse last month's transactions and summarise totals.",
        permitted_actions=frozenset({"read_transactions", "calculate_totals", "generate_report"}),
        prohibited_actions=frozenset({"modify_records", "export_customer_data"}),
        approval_required_actions=frozenset({"initiate_payment"}),
    )


def proposal(action: str, **overrides) -> dict:
    p = {"action": action, "target": "ledger", "agent_id": "agent_c"}
    p.update(overrides)
    return p


def check(prop, policy, **kw):
    return validate(prop, policy, expected_fingerprint=policy.fingerprint(), **kw)


# --- core policy decisions -------------------------------------------------

def test_permitted_action_is_allowed(policy):
    d = check(proposal("read_transactions"), policy)
    assert (d.outcome, d.reason) == (Outcome.ALLOW, Reason.PERMITTED)


def test_prohibited_action_is_rejected(policy):
    d = check(proposal("modify_records"), policy)
    assert (d.outcome, d.reason) == (Outcome.REJECT, Reason.PROHIBITED)


def test_approval_required_without_approval_escalates(policy):
    d = check(proposal("initiate_payment"), policy)
    assert (d.outcome, d.reason) == (Outcome.ESCALATE, Reason.APPROVAL_REQUIRED)


def test_approval_required_with_matching_approval_is_allowed(policy):
    approval = ApprovalEvent("APP-1", "TASK-001", "initiate_payment", "synthetic_manager")
    d = check(proposal("initiate_payment"), policy, approvals=[approval])
    assert (d.outcome, d.reason) == (Outcome.ALLOW, Reason.APPROVED)


def test_approval_for_another_task_does_not_count(policy):
    approval = ApprovalEvent("APP-1", "TASK-999", "initiate_payment", "synthetic_manager")
    d = check(proposal("initiate_payment"), policy, approvals=[approval])
    assert d.outcome == Outcome.ESCALATE


def test_approval_never_unlocks_prohibited_action(policy):
    approval = ApprovalEvent("APP-1", "TASK-001", "modify_records", "synthetic_manager")
    d = check(proposal("modify_records"), policy, approvals=[approval])
    assert (d.outcome, d.reason) == (Outcome.REJECT, Reason.PROHIBITED)


def test_unlisted_known_action_is_default_denied(policy):
    d = check(proposal("delete_records"), policy)
    assert (d.outcome, d.reason) == (Outcome.REJECT, Reason.NOT_PERMITTED)


def test_invented_action_is_rejected_as_unknown(policy):
    d = check(proposal("update_ledger_entry"), policy)
    assert (d.outcome, d.reason) == (Outcome.REJECT, Reason.UNKNOWN_ACTION)


def test_meta_action_is_allowed_even_if_unlisted(policy):
    d = check(proposal("report_conflict"), policy)
    assert (d.outcome, d.reason) == (Outcome.ALLOW, Reason.META_ACTION)


def test_meta_action_can_be_prohibited():
    p = PolicyRecord(
        task_id="T",
        original_intent="x",
        permitted_actions=frozenset(),
        prohibited_actions=frozenset({"request_human_approval"}),
        approval_required_actions=frozenset(),
    )
    d = check(proposal("request_human_approval"), p)
    assert d.reason == Reason.PROHIBITED


def test_permitted_name_with_harmful_content_is_allowed(policy):
    """Documented limitation: the gate checks action names, not content."""
    d = check(proposal("generate_report", parameters={"include": "customer emails"}), policy)
    assert d.outcome == Outcome.ALLOW


# --- missing or tampered metadata ------------------------------------------

def test_missing_policy_is_rejected(policy):
    d = validate(proposal("read_transactions"), None, expected_fingerprint=policy.fingerprint())
    assert (d.outcome, d.reason) == (Outcome.REJECT, Reason.MISSING_POLICY)


def test_tampered_policy_is_rejected(policy):
    tampered = policy.to_dict()
    tampered["prohibited_actions"] = []  # constraint silently dropped
    tampered["permitted_actions"].append("modify_records")
    d = validate(proposal("modify_records"), tampered, expected_fingerprint=policy.fingerprint())
    assert (d.outcome, d.reason) == (Outcome.REJECT, Reason.POLICY_MISMATCH)


def test_malformed_policy_dict_is_rejected(policy):
    broken = policy.to_dict()
    del broken["prohibited_actions"]
    d = validate(proposal("read_transactions"), broken, expected_fingerprint=policy.fingerprint())
    assert (d.outcome, d.reason) == (Outcome.REJECT, Reason.MALFORMED_POLICY)


def test_untampered_policy_dict_is_accepted(policy):
    d = validate(
        proposal("read_transactions"), policy.to_dict(), expected_fingerprint=policy.fingerprint()
    )
    assert d.outcome == Outcome.ALLOW


# --- malformed proposals ---------------------------------------------------

@pytest.mark.parametrize(
    "bad",
    [
        "modify_records",  # not an object
        {"target": "ledger", "agent_id": "a"},  # missing action
        {"action": "", "target": "ledger", "agent_id": "a"},  # empty action
        {"action": "read_transactions", "target": "ledger", "agent_id": "a", "parameters": []},
        {"action": "read_transactions", "target": "ledger", "agent_id": "a", "priority": "high"},
    ],
)
def test_malformed_proposal_is_rejected(policy, bad):
    d = check(bad, policy)
    assert (d.outcome, d.reason) == (Outcome.REJECT, Reason.MALFORMED_PROPOSAL)


def test_parse_proposal_defaults():
    p = parse_proposal({"action": "read_transactions", "target": "ledger", "agent_id": "a"})
    assert p.parameters == {} and p.rationale == ""
    with pytest.raises(ProposalFormatError):
        parse_proposal({"action": "x", "target": "t", "agent_id": "a", "rationale": 3})


# --- policy record itself --------------------------------------------------

def test_action_in_two_lists_is_rejected():
    with pytest.raises(PolicyFormatError, match="both"):
        PolicyRecord(
            task_id="T",
            original_intent="x",
            permitted_actions=frozenset(),
            prohibited_actions=frozenset({"modify_records"}),
            approval_required_actions=frozenset({"modify_records"}),
        )


def test_unknown_action_in_policy_is_rejected():
    with pytest.raises(PolicyFormatError, match="unknown"):
        PolicyRecord(
            task_id="T",
            original_intent="x",
            permitted_actions=frozenset({"financial_record_modification"}),
            prohibited_actions=frozenset(),
            approval_required_actions=frozenset(),
        )


def test_round_trip_and_stable_fingerprint(policy):
    restored = PolicyRecord.from_dict(policy.to_dict())
    assert restored == policy
    assert restored.fingerprint() == policy.fingerprint()
    shuffled = policy.to_dict()
    shuffled["permitted_actions"] = list(reversed(shuffled["permitted_actions"]))
    assert PolicyRecord.from_dict(shuffled).fingerprint() == policy.fingerprint()


def test_decision_serialises(policy):
    d = check(proposal("modify_records"), policy).to_dict()
    assert d == {"outcome": "reject", "reason": "prohibited", "action": "modify_records", "detail": ""}
