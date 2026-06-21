from enum import Enum
from pydantic import BaseModel


class RootCause(str, Enum):
    WRONG_ACCOUNT = "wrong_account"
    VALUE_IMBALANCE = "value_imbalance"
    TIMING = "timing"
    SOURCE_DATA = "source_data"
    UNKNOWN = "unknown"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Variance(BaseModel):
    account_id: str
    expected_ending: float
    ledger_ending: float
    variance: float  # expected_ending - ledger_ending


class CandidateRule(BaseModel):
    event_type: str
    leg: int
    account_id: str
    dr_cr: str
    amount_source: str


class Account(BaseModel):
    account_id: str
    account_type: str
    normal_balance: str  # "debit" | "credit"


class TriageContext(BaseModel):
    variances: list[Variance] = []
    posting_rules: list[CandidateRule] = []
    accounts: list[Account] = []
    journal_summary: list[dict] = []
    run_label: str | None = None


class TriageFinding(BaseModel):
    finding_id: str
    accounts: list[str]
    net_variance: float
    root_cause: RootCause
    confidence: Confidence
    candidate_rules: list[CandidateRule] = []
    explanation: str
    next_step: str
    backend: str = "heuristic"


class TriageReport(BaseModel):
    findings: list[TriageFinding] = []
    backend_requested: str = "heuristic"
    generated_from_run: str | None = None
