from audit_cli.triage.engine import run_triage
from audit_cli.triage.ollama_backend import OllamaProse, OllamaError
from audit_cli.triage.models import (
    Variance, CandidateRule, Account, TriageContext, RootCause,
)

RULES = [
    CandidateRule(event_type="payment", leg=1, account_id="cash", dr_cr="debit", amount_source="total"),
    CandidateRule(event_type="payment", leg=3, account_id="interest_income", dr_cr="credit", amount_source="interest"),
]
ACCTS = [
    Account(account_id="cash", account_type="asset", normal_balance="debit"),
    Account(account_id="interest_income", account_type="revenue", normal_balance="credit"),
]
CTX = TriageContext(
    variances=[
        Variance(account_id="cash", expected_ending=100.0, ledger_ending=95.6, variance=4.4),
        Variance(account_id="interest_income", expected_ending=-4.4, ledger_ending=0.0, variance=-4.4),
    ],
    posting_rules=RULES, accounts=ACCTS,
)

class FakeOllama:
    def __init__(self, available, prose=None, raises=False):
        self._available = available
        self._prose = prose
        self._raises = raises
    def available(self):
        return self._available
    def explain(self, cluster, context):
        if self._raises:
            raise OllamaError("boom")
        return self._prose

def test_heuristic_backend_default():
    report = run_triage(CTX, backend="heuristic")
    assert report.backend_requested == "heuristic"
    assert report.findings[0].backend == "heuristic"
    assert report.findings[0].root_cause == RootCause.WRONG_ACCOUNT

def test_auto_falls_back_to_heuristic_when_unavailable():
    report = run_triage(CTX, backend="auto", ollama=FakeOllama(available=False))
    assert report.findings[0].backend == "heuristic"

def test_ollama_enriches_prose_but_keeps_heuristic_classification():
    # Model AGREES on classification but supplies richer prose.
    prose = OllamaProse(root_cause=RootCause.WRONG_ACCOUNT, explanation="Richer LLM explanation.")
    report = run_triage(CTX, backend="ollama", ollama=FakeOllama(available=True, prose=prose))
    f = report.findings[0]
    assert f.backend == "ollama"
    assert f.explanation == "Richer LLM explanation."
    assert f.root_cause == RootCause.WRONG_ACCOUNT  # unchanged

def test_honesty_guard_keeps_heuristic_class_on_disagreement():
    # Model DISAGREES (says value_imbalance); deterministic wrong_account is retained.
    prose = OllamaProse(root_cause=RootCause.VALUE_IMBALANCE, explanation="Model thinks imbalance.")
    report = run_triage(CTX, backend="ollama", ollama=FakeOllama(available=True, prose=prose))
    f = report.findings[0]
    assert f.root_cause == RootCause.WRONG_ACCOUNT
    assert "value_imbalance" in f.explanation.lower()  # noted, not adopted

def test_ollama_error_falls_back_to_heuristic_prose():
    report = run_triage(CTX, backend="ollama", ollama=FakeOllama(available=True, raises=True))
    f = report.findings[0]
    assert f.backend == "heuristic"
    assert "reallocated" in f.explanation  # the heuristic text
