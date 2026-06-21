from audit_cli.triage.models import (
    RootCause, Confidence, Variance, CandidateRule, Account,
    TriageContext, TriageFinding, TriageReport,
)

def test_enums_have_expected_values():
    assert RootCause.WRONG_ACCOUNT.value == "wrong_account"
    assert RootCause.VALUE_IMBALANCE.value == "value_imbalance"
    assert {c.value for c in Confidence} == {"high", "medium", "low"}

def test_finding_roundtrips_and_defaults_backend_heuristic():
    f = TriageFinding(
        finding_id="cash+interest_income",
        accounts=["cash", "interest_income"],
        net_variance=0.0,
        root_cause=RootCause.WRONG_ACCOUNT,
        confidence=Confidence.HIGH,
        candidate_rules=[CandidateRule(event_type="payment", leg=3,
                                       account_id="interest_income", dr_cr="credit",
                                       amount_source="interest")],
        explanation="x", next_step="y",
    )
    assert f.backend == "heuristic"
    dumped = f.model_dump()
    assert TriageFinding.model_validate(dumped).accounts == ["cash", "interest_income"]

def test_context_defaults_are_empty():
    ctx = TriageContext()
    assert ctx.variances == [] and ctx.posting_rules == [] and ctx.accounts == []
