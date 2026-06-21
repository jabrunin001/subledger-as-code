from audit_cli.triage.render import render_triage_md
from audit_cli.triage.models import (
    TriageReport, TriageFinding, CandidateRule, RootCause, Confidence,
)

def test_render_empty_report():
    md = render_triage_md(TriageReport(findings=[], backend_requested="heuristic"))
    assert "reconciles" in md.lower()

def test_render_includes_classification_and_locus():
    f = TriageFinding(
        finding_id="cash+interest_income", accounts=["cash", "interest_income"],
        net_variance=0.0, root_cause=RootCause.WRONG_ACCOUNT, confidence=Confidence.HIGH,
        candidate_rules=[CandidateRule(event_type="payment", leg=3, account_id="interest_income",
                                       dr_cr="credit", amount_source="interest")],
        explanation="value reallocated", next_step="fix the rule", backend="heuristic",
    )
    md = render_triage_md(TriageReport(findings=[f], backend_requested="heuristic"))
    assert "wrong_account" in md
    assert "interest_income" in md
    assert "payment/3" in md
    assert "fix the rule" in md
