import json
import pytest
from audit_cli.triage.ollama_backend import OllamaClient, OllamaError, OllamaProse
from audit_cli.triage.models import Variance, CandidateRule, Account, TriageContext, RootCause

CLUSTER = [
    Variance(account_id="cash", expected_ending=100.0, ledger_ending=95.6, variance=4.4),
    Variance(account_id="interest_income", expected_ending=-4.4, ledger_ending=0.0, variance=-4.4),
]
CTX = TriageContext(
    variances=CLUSTER,
    posting_rules=[CandidateRule(event_type="payment", leg=3, account_id="interest_income",
                                 dr_cr="credit", amount_source="interest")],
    accounts=[Account(account_id="cash", account_type="asset", normal_balance="debit"),
              Account(account_id="interest_income", account_type="revenue", normal_balance="credit")],
)

class FakeTransport:
    """Records calls and returns scripted responses for the Ollama HTTP seam."""
    def __init__(self, responses):
        self.responses = responses          # dict: "tags" | "generate" -> value or Exception
        self.last_payload = None
    def __call__(self, url, payload=None):
        self.last_payload = payload
        key = "tags" if url.endswith("/api/tags") else "generate"
        value = self.responses[key]
        if isinstance(value, Exception):
            raise value
        return value

def test_available_true_when_tags_endpoint_responds():
    t = FakeTransport({"tags": {"models": [{"name": "llama3.1:8b"}]}, "generate": {}})
    assert OllamaClient("llama3.1:8b", "http://h", transport=t).available() is True

def test_available_false_when_tags_errors():
    t = FakeTransport({"tags": OSError("refused"), "generate": {}})
    assert OllamaClient("llama3.1:8b", "http://h", transport=t).available() is False

def test_explain_parses_valid_json_response_and_includes_context_in_prompt():
    body = {"response": json.dumps({"root_cause": "wrong_account",
                                    "explanation": "A payment interest credit was routed to cash."})}
    t = FakeTransport({"tags": {"models": []}, "generate": body})
    prose = OllamaClient("llama3.1:8b", "http://h", transport=t).explain(CLUSTER, CTX)
    assert isinstance(prose, OllamaProse)
    assert prose.root_cause == RootCause.WRONG_ACCOUNT
    assert "routed to cash" in prose.explanation
    # The prompt must carry the variance + posting-rule context.
    prompt = t.last_payload["prompt"]
    assert "interest_income" in prompt and "payment" in prompt

def test_explain_raises_on_invalid_json():
    t = FakeTransport({"tags": {"models": []}, "generate": {"response": "not json {"}})
    with pytest.raises(OllamaError):
        OllamaClient("llama3.1:8b", "http://h", transport=t).explain(CLUSTER, CTX)

def test_explain_raises_on_transport_error():
    t = FakeTransport({"tags": {"models": []}, "generate": TimeoutError("slow")})
    with pytest.raises(OllamaError):
        OllamaClient("llama3.1:8b", "http://h", transport=t).explain(CLUSTER, CTX)

def test_explain_raises_on_missing_response_key():
    t = FakeTransport({"tags": {"models": []}, "generate": {"error": "model not found"}})
    with pytest.raises(OllamaError):
        OllamaClient("llama3.1:8b", "http://h", transport=t).explain(CLUSTER, CTX)
