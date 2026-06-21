from audit_cli.triage.heuristic import heuristic_triage, triage_cluster
from audit_cli.triage.models import (
    Variance, CandidateRule, Account, TriageContext, RootCause, Confidence,
)

# The real posting_rules and chart-of-accounts rows the project ships.
POSTING_RULES = [
    CandidateRule(event_type="origination", leg=1, account_id="loans_receivable", dr_cr="debit", amount_source="principal"),
    CandidateRule(event_type="origination", leg=2, account_id="cash", dr_cr="credit", amount_source="principal"),
    CandidateRule(event_type="payment", leg=1, account_id="cash", dr_cr="debit", amount_source="total"),
    CandidateRule(event_type="payment", leg=2, account_id="loans_receivable", dr_cr="credit", amount_source="principal"),
    CandidateRule(event_type="payment", leg=3, account_id="interest_income", dr_cr="credit", amount_source="interest"),
    CandidateRule(event_type="charge_off", leg=1, account_id="charge_off_expense", dr_cr="debit", amount_source="total"),
    CandidateRule(event_type="charge_off", leg=2, account_id="loans_receivable", dr_cr="credit", amount_source="total"),
]
ACCOUNTS = [
    Account(account_id="loans_receivable", account_type="asset", normal_balance="debit"),
    Account(account_id="cash", account_type="asset", normal_balance="debit"),
    Account(account_id="interest_income", account_type="revenue", normal_balance="credit"),
    Account(account_id="charge_off_expense", account_type="expense", normal_balance="debit"),
]

def _ctx(variances):
    return TriageContext(variances=variances, posting_rules=POSTING_RULES, accounts=ACCOUNTS)

def test_inject_break_signature_classifies_wrong_account():
    # cash overstated +X, interest_income -X (the real inject_break variance).
    ctx = _ctx([
        Variance(account_id="cash", expected_ending=100.0, ledger_ending=95.6, variance=4.4),
        Variance(account_id="interest_income", expected_ending=-4.4, ledger_ending=0.0, variance=-4.4),
    ])
    findings = heuristic_triage(ctx)
    assert len(findings) == 1
    f = findings[0]
    assert f.root_cause == RootCause.WRONG_ACCOUNT
    assert f.confidence == Confidence.HIGH
    assert f.accounts == ["cash", "interest_income"]
    assert abs(f.net_variance) <= 0.005
    # Locus surfaces the payment/interest leg crediting interest_income.
    assert any(r.event_type == "payment" and r.account_id == "interest_income"
               for r in f.candidate_rules)
    # Explanation names the shared 'payment' entry and the suspect interest leg.
    assert "payment" in f.explanation
    assert "interest_income" in f.explanation
    assert f.backend == "heuristic"

def test_non_netting_variance_is_value_imbalance():
    ctx = _ctx([Variance(account_id="cash", expected_ending=100.0, ledger_ending=80.0, variance=20.0)])
    f = heuristic_triage(ctx)[0]
    assert f.root_cause == RootCause.VALUE_IMBALANCE
    assert f.confidence == Confidence.MEDIUM

def test_empty_variances_yield_no_findings():
    assert heuristic_triage(_ctx([])) == []
