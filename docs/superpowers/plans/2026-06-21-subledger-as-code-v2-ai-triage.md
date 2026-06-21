# Subledger-as-Code v2 — AI-Assisted Variance Triage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a triage layer to the shipped subledger that classifies each reconciliation variance, points at the likely posting-rule locus, and explains it in plain English — deterministic heuristic by default (CI-green), with an opt-in local Ollama backend that enriches the prose without changing the classification.

**Architecture:** A new `audit_cli/triage/` package: pure `cluster` + `heuristic` reasoning, a DuckDB `context` loader, an `ollama_backend` behind a mockable HTTP seam, an `engine` that orchestrates backend selection + graceful fallback + an honesty guard, and a `render`. A `triage` CLI command and a `pack` integration embed the **deterministic heuristic** report into the checksummed evidence pack. CI gains a control-proof step asserting heuristic triage explains the injected break.

**Tech Stack:** Python 3.11, Pydantic v2, DuckDB (read-only), Typer, stdlib `urllib` (Ollama HTTP), pytest. No new third-party dependencies.

## Global Constraints

- **No new dependencies.** Heuristic path uses only stdlib + Pydantic (already present). Ollama path uses stdlib `urllib` against the local HTTP API — no SDK.
- **Heuristic is the default and the only thing embedded in the pack/CI** — deterministic, checksum-stable. Ollama never touches the CI-built pack.
- **Graceful fallback:** any Ollama failure (daemon down, model missing, HTTP error, timeout, invalid JSON, Pydantic validation failure) falls back to the heuristic finding for that cluster; `backend` field records provenance per finding.
- **Honesty guard:** classification (`root_cause`) is always the deterministic heuristic result; Ollama supplies only `explanation` prose. On disagreement, keep the heuristic classification and note the model's suggestion.
- **Pydantic v2 API** (`model_validate`, `model_dump`). **Python 3.11+.**
- **Variance convention:** `variance = expected_ending − ledger_ending` (matches v1 `_query_variances`).
- **Money tolerance:** `abs(...) > 0.005` everywhere (matches v1).
- **Run pytest from the repo root** so `audit_cli` imports as a package. **Run dbt with `--profiles-dir .`.** On the dev machine use `.venv/bin/python` / `.venv/bin/dbt` / `.venv/bin/pytest` (bare `python` may be a different interpreter); CI yaml uses plain commands (its own Python 3.11).
- **Break propagation:** any build that must surface the break uses `dbt build --vars 'inject_break: true' --exclude resource_type:unit_test` (a failing unit test otherwise skips downstream tables).
- **DuckDB path** from `env_var('DBT_DUCKDB_PATH', 'subledger.duckdb')`; **Ollama** from `OLLAMA_HOST` (default `http://localhost:11434`), `OLLAMA_MODEL` (default `llama3.1:8b`).

---

## File Structure

```
audit_cli/triage/
├── __init__.py            # exports the package's public names
├── models.py              # Pydantic: enums + Variance, CandidateRule, Account, TriageContext, TriageFinding, TriageReport
├── cluster.py             # pure: cluster_variances()
├── heuristic.py           # pure: triage_cluster(), heuristic_triage()
├── context.py             # load_context(duckdb_path) -> TriageContext
├── ollama_backend.py      # OllamaProse, OllamaError, OllamaClient (HTTP seam)
├── engine.py              # run_triage(context, backend, ollama=None) -> TriageReport
└── render.py              # render_triage_md(report) -> str
audit_cli/cli.py           # MODIFY: add `triage` command; `pack` embeds heuristic triage
audit_cli/pack.py          # MODIFY: build_pack() optional triage_md/triage_json params
audit_cli/tests/           # new: test_triage_cluster.py, test_triage_heuristic.py, test_triage_context.py,
                           #      test_triage_render.py, test_triage_ollama.py, test_triage_engine.py,
                           #      test_triage_cli.py, test_pack_triage.py
scripts/assert_triage_explains.sh   # new: control-proof companion
.github/workflows/ci.yml   # MODIFY: control-proof runs the new script
README.md                  # MODIFY: detection→triage section, capability row, quickstart block
```

---

## Phase 1 — Triage data model & pure reasoning

### Task 1: Triage models

**Files:**
- Create: `audit_cli/triage/__init__.py`, `audit_cli/triage/models.py`, `audit_cli/tests/test_triage_models.py`

**Interfaces:**
- Produces enums `RootCause` (`wrong_account`, `value_imbalance`, `timing`, `source_data`, `unknown`), `Confidence` (`high`/`medium`/`low`); models `Variance(account_id:str, expected_ending:float, ledger_ending:float, variance:float)`, `CandidateRule(event_type:str, leg:int, account_id:str, dr_cr:str, amount_source:str)`, `Account(account_id:str, account_type:str, normal_balance:str)`, `TriageContext(variances, posting_rules, accounts, journal_summary, run_label)`, `TriageFinding(finding_id, accounts, net_variance, root_cause, confidence, candidate_rules, explanation, next_step, backend)`, `TriageReport(findings, backend_requested, generated_from_run)`.

- [ ] **Step 1: Write the failing test `audit_cli/tests/test_triage_models.py`**

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest audit_cli/tests/test_triage_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'audit_cli.triage'`.

- [ ] **Step 3: Write `audit_cli/triage/__init__.py`**

```python
"""Variance triage: classify reconciliation variances, point at the posting-rule
locus, and explain them — deterministic heuristic by default, optional local Ollama."""
```

- [ ] **Step 4: Write `audit_cli/triage/models.py`**

```python
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
```

- [ ] **Step 5: Run to verify it passes**

Run: `pytest audit_cli/tests/test_triage_models.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add audit_cli/triage/__init__.py audit_cli/triage/models.py audit_cli/tests/test_triage_models.py
git commit -m "feat(triage): pydantic models and enums for variance triage"
```

### Task 2: Variance clustering

**Files:**
- Create: `audit_cli/triage/cluster.py`, `audit_cli/tests/test_triage_cluster.py`

**Interfaces:**
- Consumes: `Variance` (Task 1).
- Produces: `cluster_variances(variances: list[Variance], tol: float = 0.005) -> list[list[Variance]]`. A positive and an opposite-sign variance of equal magnitude (within `tol`) form one cluster; unmatched variances are singletons. Deterministic (inputs sorted by `(-abs(variance), account_id)`).

- [ ] **Step 1: Write the failing test `audit_cli/tests/test_triage_cluster.py`**

```python
from audit_cli.triage.cluster import cluster_variances
from audit_cli.triage.models import Variance

def _v(acct, var):
    # expected/ledger are not used by clustering; only `variance` matters here.
    return Variance(account_id=acct, expected_ending=0.0, ledger_ending=0.0, variance=var)

def test_symmetric_pair_forms_one_cluster():
    clusters = cluster_variances([_v("cash", 4394.83), _v("interest_income", -4394.83)])
    assert len(clusters) == 1
    assert sorted(v.account_id for v in clusters[0]) == ["cash", "interest_income"]

def test_two_independent_pairs_form_two_clusters():
    clusters = cluster_variances([
        _v("a", 10.0), _v("b", -10.0), _v("c", 3.0), _v("d", -3.0),
    ])
    assert len(clusters) == 2
    assert all(len(c) == 2 for c in clusters)

def test_unmatched_variance_is_a_singleton():
    clusters = cluster_variances([_v("a", 10.0), _v("b", -10.0), _v("x", 7.0)])
    sizes = sorted(len(c) for c in clusters)
    assert sizes == [1, 2]

def test_empty_input_yields_no_clusters():
    assert cluster_variances([]) == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest audit_cli/tests/test_triage_cluster.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write `audit_cli/triage/cluster.py`**

```python
from .models import Variance

TOL = 0.005


def cluster_variances(variances: list[Variance], tol: float = TOL) -> list[list[Variance]]:
    """Group variances into clusters.

    A positive and an opposite-sign variance of equal magnitude (within ``tol``)
    form one cluster — a balanced reallocation between two accounts. Any variance
    that cannot be paired is its own singleton cluster. Deterministic: items are
    sorted by ``(-abs(variance), account_id)`` before greedy matching.

    n-way net-zero sets beyond simple pairs are out of scope for v2's data; the
    real reconciliation break is the symmetric two-account case.
    """
    items = sorted(variances, key=lambda v: (-abs(v.variance), v.account_id))
    used = [False] * len(items)
    clusters: list[list[Variance]] = []
    for i, v in enumerate(items):
        if used[i]:
            continue
        used[i] = True
        if abs(v.variance) <= tol:
            clusters.append([v])
            continue
        partner = None
        for j in range(i + 1, len(items)):
            if used[j]:
                continue
            w = items[j]
            opposite_sign = (v.variance > 0) != (w.variance > 0)
            if opposite_sign and abs(v.variance + w.variance) <= tol:
                partner = j
                break
        if partner is not None:
            used[partner] = True
            clusters.append([v, items[partner]])
        else:
            clusters.append([v])
    return clusters
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest audit_cli/tests/test_triage_cluster.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add audit_cli/triage/cluster.py audit_cli/tests/test_triage_cluster.py
git commit -m "feat(triage): deterministic variance clustering"
```

### Task 3: Heuristic backend

**Files:**
- Create: `audit_cli/triage/heuristic.py`, `audit_cli/tests/test_triage_heuristic.py`

**Interfaces:**
- Consumes: `cluster_variances` (Task 2); `TriageContext`, `TriageFinding`, `CandidateRule`, `Account`, `RootCause`, `Confidence` (Task 1).
- Produces: `triage_cluster(cluster: list[Variance], context: TriageContext) -> TriageFinding`; `heuristic_triage(context: TriageContext) -> list[TriageFinding]` (clusters internally, returns findings sorted by `finding_id`). A net-zero ≥2-account cluster → `WRONG_ACCOUNT`/`HIGH`; otherwise `VALUE_IMBALANCE`/`MEDIUM` (with candidate rules) or `UNKNOWN`/`LOW`. `candidate_rules` = posting rules whose `account_id` is in the cluster. `backend="heuristic"`.

- [ ] **Step 1: Write the failing test `audit_cli/tests/test_triage_heuristic.py`**

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest audit_cli/tests/test_triage_heuristic.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write `audit_cli/triage/heuristic.py`**

```python
from collections import Counter

from .cluster import cluster_variances, TOL
from .models import (
    Account, CandidateRule, Confidence, RootCause, TriageContext, TriageFinding, Variance,
)


def heuristic_triage(context: TriageContext) -> list[TriageFinding]:
    clusters = cluster_variances(context.variances)
    findings = [triage_cluster(c, context) for c in clusters]
    findings.sort(key=lambda f: f.finding_id)
    return findings


def triage_cluster(cluster: list[Variance], context: TriageContext) -> TriageFinding:
    accounts = sorted(v.account_id for v in cluster)
    net = round(sum(v.variance for v in cluster), 2)
    candidate_rules = [r for r in context.posting_rules if r.account_id in accounts]
    finding_id = "+".join(accounts)

    if len(cluster) >= 2 and abs(net) <= TOL:
        root_cause = RootCause.WRONG_ACCOUNT
        confidence = Confidence.HIGH
        explanation, next_step = _explain_wrong_account(cluster, candidate_rules, context)
    elif abs(net) > TOL and candidate_rules:
        root_cause = RootCause.VALUE_IMBALANCE
        confidence = Confidence.MEDIUM
        explanation, next_step = _explain_value_imbalance(cluster, candidate_rules, net)
    else:
        root_cause = RootCause.UNKNOWN
        confidence = Confidence.LOW
        explanation = (
            f"Account(s) {', '.join(accounts)} show a residual variance (net {net:+.2f}) that does not "
            f"match a known signature and has no implicated posting rule."
        )
        next_step = "Inspect the source events feeding these accounts for a data anomaly."

    return TriageFinding(
        finding_id=finding_id, accounts=accounts, net_variance=net,
        root_cause=root_cause, confidence=confidence, candidate_rules=candidate_rules,
        explanation=explanation, next_step=next_step, backend="heuristic",
    )


def _normal_by_account(context: TriageContext) -> dict[str, Account]:
    return {a.account_id: a for a in context.accounts}


def _explain_wrong_account(cluster, candidate_rules, context) -> tuple[str, str]:
    accounts = sorted(v.account_id for v in cluster)
    normals = _normal_by_account(context)
    net = sum(v.variance for v in cluster)
    var_str = ", ".join(
        f"{v.account_id} {v.variance:+.2f}" for v in sorted(cluster, key=lambda v: v.account_id)
    )
    # The event_type whose rules cover the most cluster accounts is the likely site.
    event_counts = Counter(r.event_type for r in candidate_rules)
    shared_event = event_counts.most_common(1)[0][0] if event_counts else None
    # Leading suspect: a credit-normal leg within that event (a revenue/liability credit
    # is the kind of leg most plausibly misrouted to an asset like cash).
    suspect = None
    for r in candidate_rules:
        if shared_event and r.event_type != shared_event:
            continue
        acct = normals.get(r.account_id)
        if acct and acct.normal_balance == "credit":
            suspect = r
            break

    text = (
        f"Accounts {' and '.join(accounts)} diverge from their source-derived expectations by "
        f"offsetting amounts (net {net:+.2f} ≈ 0: {var_str}), indicating value was reallocated "
        f"between them rather than created or lost — most consistent with a posting leg targeting "
        f"the wrong account."
    )
    if shared_event:
        text += f" Both accounts are posted by the '{shared_event}' entry"
        if suspect:
            text += (
                f"; the leg crediting '{suspect.account_id}' (rule {suspect.event_type}/{suspect.leg}, "
                f"amount_source '{suspect.amount_source}') is the leading suspect for misrouting."
            )
        else:
            text += "."
    next_step = (
        "Inspect the candidate posting rules for a leg posting to the wrong account; correct it and "
        "re-run reconciliation. The trial-balance control will stay green (this is a balanced "
        "reallocation) — only the substantive source-to-ledger reconciliation catches it."
    )
    return text, next_step


def _explain_value_imbalance(cluster, candidate_rules, net) -> tuple[str, str]:
    accounts = sorted(v.account_id for v in cluster)
    text = (
        f"Account(s) {', '.join(accounts)} show a net variance of {net:+.2f} that does not net to zero "
        f"against another account, indicating aggregate value changed — a missing or duplicated leg, "
        f"or an amount error, rather than a reallocation. (A true global imbalance would also trip the "
        f"trial-balance control; a single-account residual points at that account's source postings.)"
    )
    next_step = (
        "Check the candidate posting rules and the source events for the affected account(s) for a "
        "dropped, duplicated, or mis-valued leg."
    )
    return text, next_step
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest audit_cli/tests/test_triage_heuristic.py -v`
Expected: PASS (3 tests). In particular `test_inject_break_signature_classifies_wrong_account` confirms the explanation names the `payment` entry and the `interest_income` suspect leg.

- [ ] **Step 5: Commit**

```bash
git add audit_cli/triage/heuristic.py audit_cli/tests/test_triage_heuristic.py
git commit -m "feat(triage): deterministic heuristic backend (classify + locus + explain)"
```

---

## Phase 2 — Context loading & rendering

### Task 4: DuckDB context loader

**Files:**
- Create: `audit_cli/triage/context.py`, `audit_cli/tests/test_triage_context.py`

**Interfaces:**
- Consumes: `Variance`, `CandidateRule`, `Account`, `TriageContext` (Task 1).
- Produces: `load_context(duckdb_path: str, run_label: str | None = None) -> TriageContext`. Reads variances from `fct_balance_rollforward` (where `abs(expected_ending - ledger_ending) > 0.005`), `posting_rules`, `dim_account`, and a per-affected-account `fct_journal_lines` dr/cr summary. Resolves each table's schema via `information_schema` (seeds may live in a non-`main` schema). Read-only connection.

- [ ] **Step 1: Write the failing test `audit_cli/tests/test_triage_context.py`**

```python
import duckdb
from audit_cli.triage.context import load_context

def _build_fixture_db(path):
    con = duckdb.connect(path)
    con.execute("""
        create table fct_balance_rollforward (
            account_id varchar, beginning_balance double, originations double,
            principal_repayments double, charge_offs double, interest double,
            expected_ending double, ledger_ending double)
    """)
    con.execute("""
        insert into fct_balance_rollforward values
        ('cash', 0, 0, 0, 0, 0, 100.0, 95.6),            -- variance +4.4
        ('interest_income', 0, 0, 0, 0, 0, -4.4, 0.0),   -- variance -4.4
        ('loans_receivable', 0, 0, 0, 0, 0, 50.0, 50.0)  -- reconciles, excluded
    """)
    con.execute("create table posting_rules (event_type varchar, leg integer, account_id varchar, dr_cr varchar, amount_source varchar)")
    con.execute("""insert into posting_rules values
        ('payment', 3, 'interest_income', 'credit', 'interest'),
        ('payment', 1, 'cash', 'debit', 'total')""")
    con.execute("create table dim_account (account_id varchar, account_name varchar, account_type varchar, normal_balance varchar)")
    con.execute("""insert into dim_account values
        ('cash', 'Cash', 'asset', 'debit'),
        ('interest_income', 'Interest Income', 'revenue', 'credit')""")
    con.execute("create table fct_journal_lines (journal_line_id varchar, account_id varchar, dr_amount double, cr_amount double)")
    con.execute("""insert into fct_journal_lines values
        ('a', 'cash', 100.0, 4.4), ('b', 'interest_income', 0.0, 0.0)""")
    con.close()

def test_load_context_reads_variances_rules_accounts(tmp_path):
    db = str(tmp_path / "fix.duckdb")
    _build_fixture_db(db)
    ctx = load_context(db, run_label="test-run")

    # Only non-reconciling accounts become variances.
    assert sorted(v.account_id for v in ctx.variances) == ["cash", "interest_income"]
    cash = next(v for v in ctx.variances if v.account_id == "cash")
    assert abs(cash.variance - 4.4) < 1e-6  # expected - ledger

    assert any(r.event_type == "payment" and r.account_id == "interest_income"
               for r in ctx.posting_rules)
    assert {a.account_id: a.normal_balance for a in ctx.accounts}["interest_income"] == "credit"
    assert ctx.run_label == "test-run"
    # Journal summary covers only affected accounts.
    assert {j["account_id"] for j in ctx.journal_summary} == {"cash", "interest_income"}
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest audit_cli/tests/test_triage_context.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write `audit_cli/triage/context.py`**

```python
import duckdb

from .models import Account, CandidateRule, TriageContext, Variance


def _schema_of(con, table: str) -> str:
    row = con.execute(
        "select table_schema from information_schema.tables where table_name = ? "
        "order by case when table_schema = 'main' then 0 else 1 end limit 1",
        [table],
    ).fetchone()
    return row[0] if row else "main"


def _q(con, table: str) -> str:
    return f'"{_schema_of(con, table)}"."{table}"'


def load_context(duckdb_path: str, run_label: str | None = None) -> TriageContext:
    con = duckdb.connect(duckdb_path, read_only=True)
    try:
        rf = _q(con, "fct_balance_rollforward")
        variances = [
            Variance(account_id=r[0], expected_ending=float(r[1]),
                     ledger_ending=float(r[2]), variance=float(r[3]))
            for r in con.execute(
                f"select account_id, expected_ending, ledger_ending, "
                f"expected_ending - ledger_ending as variance from {rf} "
                f"where abs(expected_ending - ledger_ending) > 0.005 order by account_id"
            ).fetchall()
        ]
        pr = _q(con, "posting_rules")
        posting_rules = [
            CandidateRule(event_type=r[0], leg=int(r[1]), account_id=r[2],
                          dr_cr=r[3], amount_source=r[4])
            for r in con.execute(
                f"select event_type, leg, account_id, dr_cr, amount_source from {pr} "
                f"order by event_type, leg"
            ).fetchall()
        ]
        da = _q(con, "dim_account")
        accounts = [
            Account(account_id=r[0], account_type=r[1], normal_balance=r[2])
            for r in con.execute(
                f"select account_id, account_type, normal_balance from {da} order by account_id"
            ).fetchall()
        ]
        journal_summary = []
        if variances:
            affected = [v.account_id for v in variances]
            jl = _q(con, "fct_journal_lines")
            placeholders = ",".join("?" for _ in affected)
            journal_summary = [
                {"account_id": r[0], "dr_total": float(r[1]), "cr_total": float(r[2])}
                for r in con.execute(
                    f"select account_id, sum(dr_amount), sum(cr_amount) from {jl} "
                    f"where account_id in ({placeholders}) group by account_id order by account_id",
                    affected,
                ).fetchall()
            ]
    finally:
        con.close()
    return TriageContext(
        variances=variances, posting_rules=posting_rules, accounts=accounts,
        journal_summary=journal_summary, run_label=run_label,
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest audit_cli/tests/test_triage_context.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add audit_cli/triage/context.py audit_cli/tests/test_triage_context.py
git commit -m "feat(triage): DuckDB context loader (variances, rules, accounts, journal summary)"
```

### Task 5: Markdown renderer

**Files:**
- Create: `audit_cli/triage/render.py`, `audit_cli/tests/test_triage_render.py`

**Interfaces:**
- Consumes: `TriageReport`, `TriageFinding` (Task 1).
- Produces: `render_triage_md(report: TriageReport) -> str`. Empty findings → a "ledger reconciles" line; otherwise one section per finding with accounts, net variance, backend, candidate rules, explanation, next step.

- [ ] **Step 1: Write the failing test `audit_cli/tests/test_triage_render.py`**

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest audit_cli/tests/test_triage_render.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write `audit_cli/triage/render.py`**

```python
from .models import TriageReport


def render_triage_md(report: TriageReport) -> str:
    lines = ["# Variance Triage", "", f"_Backend requested: {report.backend_requested}_", ""]
    if not report.findings:
        lines.append("_No reconciliation variances to triage — the ledger reconciles._")
        return "\n".join(lines) + "\n"
    for f in report.findings:
        lines.append(f"## {f.finding_id} — {f.root_cause.value} ({f.confidence.value} confidence)")
        lines.append("")
        lines.append(f"- Accounts: {', '.join(f.accounts)}")
        lines.append(f"- Net variance: {f.net_variance:+.2f}")
        lines.append(f"- Backend: {f.backend}")
        if f.candidate_rules:
            rules = "; ".join(
                f"{r.event_type}/{r.leg} {r.dr_cr} {r.account_id} ({r.amount_source})"
                for r in f.candidate_rules
            )
            lines.append(f"- Candidate rules: {rules}")
        lines.append("")
        lines.append(f.explanation)
        lines.append("")
        lines.append(f"**Next step:** {f.next_step}")
        lines.append("")
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest audit_cli/tests/test_triage_render.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add audit_cli/triage/render.py audit_cli/tests/test_triage_render.py
git commit -m "feat(triage): markdown renderer for triage reports"
```

---

## Phase 3 — Ollama backend & engine

### Task 6: Ollama backend (behind a mockable HTTP seam)

**Files:**
- Create: `audit_cli/triage/ollama_backend.py`, `audit_cli/tests/test_triage_ollama.py`

**Interfaces:**
- Consumes: `RootCause`, `TriageContext`, `Variance`, `CandidateRule`, `Account` (Task 1).
- Produces: `OllamaError(Exception)`; `OllamaProse(BaseModel)` with `root_cause: RootCause`, `explanation: str`; `OllamaClient(model, host, transport=None)` with `available() -> bool` and `explain(cluster: list[Variance], context: TriageContext) -> OllamaProse`. `transport` is an injectable callable `transport(url: str, payload: dict | None) -> dict` (the HTTP seam); the default uses stdlib `urllib`. `explain` builds a JSON-mode prompt, calls the model, parses+validates the response into `OllamaProse`, and raises `OllamaError` on any failure (HTTP, timeout, bad JSON, validation).

- [ ] **Step 1: Write the failing test `audit_cli/tests/test_triage_ollama.py`**

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest audit_cli/tests/test_triage_ollama.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write `audit_cli/triage/ollama_backend.py`**

```python
import json
import urllib.request

from pydantic import BaseModel, ValidationError

from .models import Account, RootCause, TriageContext, Variance


class OllamaError(Exception):
    """Any failure talking to the local Ollama daemon or parsing its output."""


class OllamaProse(BaseModel):
    root_cause: RootCause
    explanation: str


def _urllib_transport(url: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"},
                                 method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


class OllamaClient:
    def __init__(self, model: str, host: str, transport=_urllib_transport):
        self.model = model
        self.host = host.rstrip("/")
        self._transport = transport

    def available(self) -> bool:
        try:
            self._transport(f"{self.host}/api/tags", None)
            return True
        except Exception:
            return False

    def explain(self, cluster: list[Variance], context: TriageContext) -> OllamaProse:
        prompt = self._build_prompt(cluster, context)
        try:
            body = self._transport(f"{self.host}/api/generate", {
                "model": self.model, "prompt": prompt, "stream": False, "format": "json",
            })
            raw = body["response"]
            return OllamaProse.model_validate(json.loads(raw))
        except OllamaError:
            raise
        except (ValidationError, json.JSONDecodeError, KeyError, ValueError, OSError, Exception) as e:
            raise OllamaError(str(e)) from e

    def _build_prompt(self, cluster: list[Variance], context: TriageContext) -> str:
        normals = {a.account_id: a for a in context.accounts}
        accts = sorted(v.account_id for v in cluster)
        rules = [r for r in context.posting_rules if r.account_id in accts]
        lines = [
            "You are a financial-controls assistant triaging a subledger reconciliation variance.",
            "Classify the root cause from EXACTLY this set: "
            "wrong_account, value_imbalance, timing, source_data, unknown.",
            "Do not assume a bug was injected; reason only from the data below.",
            "",
            "Variances (variance = expected_ending - ledger_ending):",
        ]
        for v in sorted(cluster, key=lambda v: v.account_id):
            acct = normals.get(v.account_id)
            nb = acct.normal_balance if acct else "?"
            lines.append(f"  - {v.account_id} (normal_balance={nb}): "
                         f"expected={v.expected_ending:.2f} ledger={v.ledger_ending:.2f} "
                         f"variance={v.variance:+.2f}")
        lines.append("")
        lines.append("Posting rules touching these accounts:")
        for r in rules:
            lines.append(f"  - {r.event_type}/{r.leg}: {r.dr_cr} {r.account_id} (amount_source={r.amount_source})")
        lines.append("")
        lines.append("Respond ONLY with JSON: {\"root_cause\": <one enum value>, "
                     "\"explanation\": <2-3 sentences for an accountant>}.")
        return "\n".join(lines)
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest audit_cli/tests/test_triage_ollama.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add audit_cli/triage/ollama_backend.py audit_cli/tests/test_triage_ollama.py
git commit -m "feat(triage): Ollama backend behind a mockable HTTP seam with structured output"
```

### Task 7: Engine (selection, fallback, honesty guard)

**Files:**
- Create: `audit_cli/triage/engine.py`, `audit_cli/tests/test_triage_engine.py`

**Interfaces:**
- Consumes: `cluster_variances` (Task 2), `triage_cluster` (Task 3), `OllamaClient`/`OllamaProse`/`OllamaError` (Task 6), `TriageContext`/`TriageReport`/`TriageFinding` (Task 1).
- Produces: `run_triage(context: TriageContext, backend: str = "heuristic", ollama: OllamaClient | None = None) -> TriageReport`. `backend` ∈ {`heuristic`, `ollama`, `auto`}. Heuristic finding is always the classification spine; when `ollama`/`auto` and the client is `available()`, each finding's `explanation` is replaced by the model's prose and `backend` set to `"ollama"`; the heuristic `root_cause` is always kept (honesty guard) — on disagreement a note is appended. Any `OllamaError` keeps that finding's heuristic prose. Findings sorted by `finding_id`.

- [ ] **Step 1: Write the failing test `audit_cli/tests/test_triage_engine.py`**

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest audit_cli/tests/test_triage_engine.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write `audit_cli/triage/engine.py`**

```python
from .cluster import cluster_variances
from .heuristic import triage_cluster
from .models import TriageContext, TriageReport
from .ollama_backend import OllamaError


def run_triage(context: TriageContext, backend: str = "heuristic", ollama=None) -> TriageReport:
    clusters = cluster_variances(context.variances)
    use_ollama = backend in ("ollama", "auto") and ollama is not None and ollama.available()

    findings = []
    for cluster in clusters:
        finding = triage_cluster(cluster, context)  # deterministic spine
        if use_ollama:
            try:
                prose = ollama.explain(cluster, context)
                finding.explanation = prose.explanation
                finding.backend = "ollama"
                if prose.root_cause != finding.root_cause:
                    # Honesty guard: keep the deterministic classification; note the model's view.
                    finding.explanation += (
                        f"\n\n_(Local model suggested '{prose.root_cause.value}'; "
                        f"deterministic classification '{finding.root_cause.value}' retained.)_"
                    )
            except OllamaError:
                pass  # keep the heuristic finding for this cluster
        findings.append(finding)

    findings.sort(key=lambda f: f.finding_id)
    return TriageReport(
        findings=findings, backend_requested=backend, generated_from_run=context.run_label,
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest audit_cli/tests/test_triage_engine.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add audit_cli/triage/engine.py audit_cli/tests/test_triage_engine.py
git commit -m "feat(triage): engine with backend selection, fallback, and honesty guard"
```

---

## Phase 4 — CLI & evidence-pack integration

### Task 8: `triage` CLI command

**Files:**
- Modify: `audit_cli/cli.py`
- Create: `audit_cli/tests/test_triage_cli.py`

**Interfaces:**
- Consumes: `load_context` (Task 4), `run_triage` (Task 7), `render_triage_md` (Task 5), `OllamaClient` (Task 6).
- Produces: a Typer `triage` command on the existing `app`: `--backend heuristic|ollama|auto` (default `heuristic`), `--out PATH` (optional; writes `triage.md`, else prints to stdout). Reads DuckDB at `env DBT_DUCKDB_PATH` (default `subledger.duckdb`). For `ollama`/`auto`, constructs `OllamaClient(env OLLAMA_MODEL default 'llama3.1:8b', env OLLAMA_HOST default 'http://localhost:11434')`.

- [ ] **Step 1: Write the failing test `audit_cli/tests/test_triage_cli.py`**

This uses the same DuckDB fixture builder as the context test, points `DBT_DUCKDB_PATH` at it, and runs the heuristic backend (deterministic, no Ollama).

```python
import duckdb
from typer.testing import CliRunner
from audit_cli.cli import app

runner = CliRunner()

def _build_fixture_db(path):
    con = duckdb.connect(path)
    con.execute("create table fct_balance_rollforward (account_id varchar, expected_ending double, ledger_ending double)")
    con.execute("""insert into fct_balance_rollforward values
        ('cash', 100.0, 95.6), ('interest_income', -4.4, 0.0)""")
    con.execute("create table posting_rules (event_type varchar, leg integer, account_id varchar, dr_cr varchar, amount_source varchar)")
    con.execute("""insert into posting_rules values
        ('payment', 1, 'cash', 'debit', 'total'),
        ('payment', 3, 'interest_income', 'credit', 'interest')""")
    con.execute("create table dim_account (account_id varchar, account_name varchar, account_type varchar, normal_balance varchar)")
    con.execute("""insert into dim_account values
        ('cash','Cash','asset','debit'), ('interest_income','Interest Income','revenue','credit')""")
    con.execute("create table fct_journal_lines (journal_line_id varchar, account_id varchar, dr_amount double, cr_amount double)")
    con.execute("insert into fct_journal_lines values ('a','cash',100.0,4.4)")
    con.close()

def test_triage_heuristic_classifies_break(tmp_path, monkeypatch):
    db = str(tmp_path / "fix.duckdb")
    _build_fixture_db(db)
    monkeypatch.setenv("DBT_DUCKDB_PATH", db)
    result = runner.invoke(app, ["triage", "--backend", "heuristic"])
    assert result.exit_code == 0
    assert "wrong_account" in result.stdout
    assert "cash" in result.stdout and "interest_income" in result.stdout

def test_triage_writes_to_out(tmp_path, monkeypatch):
    db = str(tmp_path / "fix.duckdb")
    _build_fixture_db(db)
    monkeypatch.setenv("DBT_DUCKDB_PATH", db)
    out = tmp_path / "triage.md"
    result = runner.invoke(app, ["triage", "--out", str(out)])
    assert result.exit_code == 0
    assert out.exists() and "wrong_account" in out.read_text()
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest audit_cli/tests/test_triage_cli.py -v`
Expected: FAIL — no `triage` command on `app`.

- [ ] **Step 3: Add imports and the `triage` command to `audit_cli/cli.py`**

Add these imports near the top of `audit_cli/cli.py` (with the existing imports):

```python
from .triage.context import load_context
from .triage.engine import run_triage
from .triage.render import render_triage_md
from .triage.ollama_backend import OllamaClient
```

Add this command (place it after the existing `pack` command, before `if __name__`):

```python
def _ollama_from_env() -> OllamaClient:
    return OllamaClient(
        model=os.environ.get("OLLAMA_MODEL", "llama3.1:8b"),
        host=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
    )


@app.command()
def triage(
    backend: str = typer.Option("heuristic", "--backend",
                                help="heuristic | ollama | auto"),
    out: str = typer.Option("", "--out", help="write triage.md here; else print to stdout"),
):
    """Triage reconciliation variances: classify, locate, and explain."""
    duckdb_path = os.environ.get("DBT_DUCKDB_PATH", "subledger.duckdb")
    context = load_context(duckdb_path, run_label=_git_sha())
    ollama = _ollama_from_env() if backend in ("ollama", "auto") else None
    report = run_triage(context, backend=backend, ollama=ollama)
    md = render_triage_md(report)
    if out:
        with open(out, "w") as f:
            f.write(md)
        typer.echo(f"Triage written to {out}")
    else:
        typer.echo(md)
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest audit_cli/tests/test_triage_cli.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Run the full CLI suite (no regressions, pristine)**

Run: `pytest audit_cli/ -v`
Expected: all PASS, no warnings.

- [ ] **Step 6: Commit**

```bash
git add audit_cli/cli.py audit_cli/tests/test_triage_cli.py
git commit -m "feat(triage): subledger-audit triage command"
```

### Task 9: Embed deterministic triage in the evidence pack

**Files:**
- Modify: `audit_cli/pack.py` (extend `build_pack`), `audit_cli/cli.py` (`pack` command)
- Create: `audit_cli/tests/test_pack_triage.py`

**Interfaces:**
- Consumes: `build_pack` (v1), `load_context`/`run_triage`/`render_triage_md` (Tasks 4/7/5).
- Produces: `build_pack(..., triage_md: str | None = None, triage_json: str | None = None)` — when provided, writes `triage.md` and `triage.json` into the pack dir before the manifest (so both are checksummed). Backward-compatible: existing callers omit them and the files are simply absent. The `pack` command runs the **heuristic** engine and passes both artifacts.

- [ ] **Step 1: Write the failing test `audit_cli/tests/test_pack_triage.py`**

```python
from pathlib import Path
from audit_cli import pack
from audit_cli.models import TestResult

def test_build_pack_embeds_triage_and_manifest_covers_them(tmp_path):
    pack_dir = pack.build_pack(
        out_dir=str(tmp_path),
        results=[TestResult(unique_id="test.subledger.assert_rollforward_reconciles", status="fail")],
        lineage=[],
        reconciliation_md="# r\n",
        dbt_version="1.8.9",
        git_sha="deadbee",
        triage_md="# Variance Triage\nwrong_account\n",
        triage_json='{"findings": [], "backend_requested": "heuristic"}',
    )
    p = Path(pack_dir)
    assert (p / "triage.md").exists()
    assert (p / "triage.json").exists()
    manifest = (p / "MANIFEST.sha256").read_text()
    assert "triage.md" in manifest and "triage.json" in manifest
    assert pack.verify_manifest(pack_dir) == []  # freshly built pack verifies clean

def test_build_pack_without_triage_is_unchanged(tmp_path):
    pack_dir = pack.build_pack(
        out_dir=str(tmp_path),
        results=[], lineage=[], reconciliation_md="# r\n",
        dbt_version="1.8.9", git_sha="abc1234",
    )
    p = Path(pack_dir)
    assert not (p / "triage.md").exists()
    assert pack.verify_manifest(pack_dir) == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest audit_cli/tests/test_pack_triage.py -v`
Expected: FAIL — `build_pack()` got an unexpected keyword argument `triage_md`.

- [ ] **Step 3: Extend `build_pack` in `audit_cli/pack.py`**

Change the `build_pack` signature and add the triage writes before `write_manifest`. Replace the existing `build_pack` function with:

```python
def build_pack(out_dir: str, results: list[TestResult], lineage: list[LineageNode],
               reconciliation_md: str, dbt_version: str, git_sha: str,
               triage_md: str | None = None, triage_json: str | None = None) -> str:
    summary = EvidenceSummary(
        total=len(results),
        passed=sum(1 for r in results if r.unique_id.startswith("test.") and r.status == "pass"),
        failed=sum(1 for r in results if r.unique_id.startswith("test.") and r.status == "fail"),
        errored=sum(1 for r in results if r.unique_id.startswith("test.") and r.status == "error"),
    )
    pack_dir = os.path.join(out_dir, f"evidence-{git_sha}")
    os.makedirs(pack_dir, exist_ok=True)

    with open(os.path.join(pack_dir, "test_results.json"), "w") as f:
        json.dump([r.model_dump() for r in results], f, indent=2)
    with open(os.path.join(pack_dir, "lineage.json"), "w") as f:
        json.dump([n.model_dump() for n in lineage], f, indent=2)
    with open(os.path.join(pack_dir, "reconciliation.md"), "w") as f:
        f.write(reconciliation_md)
    with open(os.path.join(pack_dir, "control_attestation.md"), "w") as f:
        f.write(_attestation(summary, dbt_version, git_sha))
    if triage_md is not None:
        with open(os.path.join(pack_dir, "triage.md"), "w") as f:
            f.write(triage_md)
    if triage_json is not None:
        with open(os.path.join(pack_dir, "triage.json"), "w") as f:
            f.write(triage_json)

    write_manifest(pack_dir)
    return pack_dir
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest audit_cli/tests/test_pack_triage.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Wire heuristic triage into the `pack` command in `audit_cli/cli.py`**

Replace the body of the existing `pack` command with this version (adds the triage artifacts; heuristic backend only, so the pack stays deterministic):

```python
@app.command()
def pack(out_dir: str = typer.Option("evidence", "--out")):
    """Assemble a checksummed evidence pack (now including deterministic variance triage)."""
    results = dbt_artifacts.parse_run_results(os.path.join(TARGET_DIR, "run_results.json"))
    lineage = dbt_artifacts.parse_lineage(os.path.join(TARGET_DIR, "manifest.json"))
    duckdb_path = os.environ.get("DBT_DUCKDB_PATH", "subledger.duckdb")
    recon_md = reconciliation.render_statement(_query_variances(duckdb_path))
    run_results_path = os.path.join(TARGET_DIR, "run_results.json")

    context = load_context(duckdb_path, run_label=_git_sha())
    report = run_triage(context, backend="heuristic")
    triage_md = render_triage_md(report)
    triage_json = json.dumps(report.model_dump(), indent=2)

    pack_dir = pack_mod.build_pack(
        out_dir=out_dir, results=results, lineage=lineage,
        reconciliation_md=recon_md,
        dbt_version=_dbt_version_from_run_results(run_results_path),
        git_sha=_git_sha(),
        triage_md=triage_md, triage_json=triage_json,
    )
    typer.echo(f"Evidence pack written to {pack_dir}")
```

- [ ] **Step 6: Run the full CLI suite + a live pack smoke**

Run:
```bash
pytest audit_cli/ -v
dbt build --profiles-dir .
python -m audit_cli.cli pack --out evidence
python -m audit_cli.cli verify evidence/evidence-$(git rev-parse --short HEAD)
```
Expected: all tests pass; pack written including `triage.md` + `triage.json`; verify reports "all checksums match." (On a clean build the triage report shows "the ledger reconciles." `evidence/` is gitignored.)

- [ ] **Step 7: Commit**

```bash
git add audit_cli/pack.py audit_cli/cli.py audit_cli/tests/test_pack_triage.py
git commit -m "feat(triage): embed deterministic triage.json/triage.md in the evidence pack"
```

---

## Phase 5 — CI & README

### Task 10: Control-proof asserts triage explains the break

**Files:**
- Create: `scripts/assert_triage_explains.sh`
- Modify: `.github/workflows/ci.yml` (control-proof job)

**Interfaces:**
- Produces `scripts/assert_triage_explains.sh`: rebuilds with the break (so `fct_balance_rollforward` holds the variance), runs heuristic triage, and asserts the output classifies `wrong_account` naming `cash` and `interest_income`. Exit 0 only on success.

- [ ] **Step 1: Write `scripts/assert_triage_explains.sh`**

```bash
#!/usr/bin/env bash
# Proves the deterministic triage explains the caught break: classifies it
# wrong_account and names the cash / interest_income accounts.
set -uo pipefail

# Rebuild with the break so fct_balance_rollforward holds the variance.
# Exclude unit tests (they assert the *correct* posting and would otherwise halt the
# build before the break reaches the materialized tables).
dbt build --profiles-dir . --vars 'inject_break: true' \
  --exclude resource_type:unit_test >/dev/null 2>&1 || true

out=$(python -m audit_cli.cli triage --backend heuristic 2>/dev/null)
echo "$out"

if echo "$out" | grep -qi "wrong_account" \
   && echo "$out" | grep -qi "cash" \
   && echo "$out" | grep -qi "interest_income"; then
  echo "PASS: triage classified the break as wrong_account on cash/interest_income."
  exit 0
fi
echo "FAIL: triage did not classify the break as expected."
exit 1
```

- [ ] **Step 2: Make it executable and verify locally**

Run:
```bash
chmod +x scripts/assert_triage_explains.sh
./scripts/assert_triage_explains.sh; echo "exit=$?"
dbt build --profiles-dir .   # restore clean state
```
Expected: prints the triage output + "PASS: triage classified the break ..." and `exit=0`.

- [ ] **Step 3: Add a step to the `control-proof` job in `.github/workflows/ci.yml`**

In the `control-proof` job, after the existing `./scripts/assert_break_caught.sh` step, add:

```yaml
      - run: chmod +x scripts/assert_triage_explains.sh
      - run: ./scripts/assert_triage_explains.sh
```

- [ ] **Step 4: Verify the whole control-proof sequence locally**

Run:
```bash
./scripts/assert_break_caught.sh
./scripts/assert_triage_explains.sh
dbt build --profiles-dir .   # restore clean
```
Expected: both scripts exit 0 (the second prints the triage PASS line).

- [ ] **Step 5: Commit**

```bash
git add scripts/assert_triage_explains.sh .github/workflows/ci.yml
git commit -m "ci(triage): control-proof asserts heuristic triage explains the break"
```

### Task 11: README — detection → triage

**Files:**
- Modify: `README.md`

**Interfaces:**
- Adds a "From detection to triage" section (heuristic output + a recorded Ollama example), a "Local, private inference" note, a capability-map row, and an optional quickstart block. Every documented command must be one that actually runs.

- [ ] **Step 1: Add a "From detection to triage" section after the "control in action" section in `README.md`**

```markdown
## From detection to triage

v1 *caught* the break; v2 *explains* it. Triage clusters the reconciliation variances,
classifies the root cause, points at the implicated posting rule, and writes a plain-English
explanation — deterministically, no LLM required:

```bash
# after a broken build (see "control in action" above):
subledger-audit triage --backend heuristic
```

Output (deterministic):

```
## cash+interest_income — wrong_account (high confidence)
- Accounts: cash, interest_income
- Net variance: +0.00
- Candidate rules: payment/1 debit cash (total); payment/3 credit interest_income (interest)
Accounts cash and interest_income diverge ... value was reallocated between them ... Both accounts
are posted by the 'payment' entry; the leg crediting 'interest_income' (rule payment/3, amount_source
'interest') is the leading suspect for misrouting.
**Next step:** ... the trial-balance control stays green — only the substantive reconciliation catches it.
```

`pack` embeds this deterministic triage (`triage.json` + `triage.md`) into the checksummed evidence
pack, so the auditor evidence now triages each exception, not just records it. The `control-proof` CI
job asserts this classification.

### Optional: richer explanations with a local LLM

```bash
ollama pull llama3.1:8b
subledger-audit triage --backend ollama
```

With Ollama running, the `--backend ollama` path produces a richer natural-language explanation for the
same finding. **Local, private inference:** the prompt — financial variances and posting rules — never
leaves the machine. Classification stays deterministic (the local model enriches the prose but cannot
change the root cause), and if Ollama isn't available the command silently falls back to the heuristic.

> _Recorded example (local llama3.1; your wording will vary):_
> "The payment entry's interest component appears to be crediting Cash instead of Interest Income:
> Cash holds an extra $4,394.83 while Interest Income is short by the same amount. Inspect the
> `payment`/`interest` leg in `posting_rules`."
```

- [ ] **Step 2: Add a capability-map row** in the existing "Capability map" table:

```markdown
| AI/LLM for data quality | `audit_cli/triage/` (deterministic heuristic + optional local Ollama) |
```

- [ ] **Step 3: Verify every documented command runs**

Run (venv active):
```bash
dbt build --profiles-dir . --vars 'inject_break: true' --exclude resource_type:unit_test
python -m audit_cli.cli triage --backend heuristic     # matches the documented output shape
dbt build --profiles-dir .                              # restore clean
```
Expected: the heuristic triage prints the `wrong_account` finding naming `cash`/`interest_income` and the `payment/3` suspect, consistent with the README. (The Ollama block is documented as optional/recorded; do not require a live model.)

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs(triage): detection→triage section, local-LLM note, capability row"
```

---

## Self-Review

**1. Spec coverage** (each spec section → task):
- Architecture & module boundaries (`audit_cli/triage/` package) → Tasks 1–7 ✓
- Triage data model & taxonomy (enums + models) → Task 1 ✓
- Heuristic backend (cluster + classify + locus + explain, normal_balance-aware direction) → Tasks 2–3 ✓
- Context loader (variances, posting_rules, dim_account, journal summary) → Task 4 ✓
- Renderer → Task 5 ✓
- Ollama backend (probe, prompt, structured output, graceful failure, HTTP seam) → Task 6 ✓
- Engine (selection, fallback, honesty guard) → Task 7 ✓
- CLI `triage` command → Task 8 ✓
- `pack` embeds deterministic triage; pack stays checksummed → Task 9 ✓
- CI control-proof asserts triage explains the break → Task 10 ✓
- README detection→triage + local-private-inference + capability row + quickstart → Task 11 ✓
- Testing strategy (all deterministic; mock the HTTP seam) → Tasks 2–9 (each ships its tests) ✓
- Success criteria (heuristic classifies break; pack embeds deterministic triage + verify passes;
  control-proof step; fallback never hard-fails; Ollama enriches with guarded classification; README
  detection→triage in 5 min) → Tasks 8/9/10/11 verifications ✓

**2. Placeholder scan:** No TBD/TODO/"handle edge cases"/"similar to Task N" — every code step shows real content. ✓

**3. Type consistency:** Model names and fields (`TriageContext`, `TriageFinding`, `TriageReport`, `CandidateRule`, `Account`, `Variance`, `RootCause`, `Confidence`, `OllamaProse`) consistent across tasks. Function signatures consistent: `cluster_variances(list[Variance])→list[list[Variance]]` (Task 2) used in Task 3 & 7; `triage_cluster(cluster, context)` (Task 3) used in Task 7; `load_context(duckdb_path, run_label)` (Task 4) used in Tasks 8/9; `run_triage(context, backend, ollama)` (Task 7) used in Tasks 8/9; `render_triage_md(report)` (Task 5) used in Tasks 8/9; `OllamaClient(model, host, transport)` with `available()`/`explain(cluster, context)` (Task 6) used in Tasks 7/8; `build_pack(..., triage_md, triage_json)` (Task 9) matches the `pack` command call. `backend` field strings (`"heuristic"`/`"ollama"`) consistent. ✓

**Note:** No new dependencies are added (heuristic = stdlib + Pydantic; Ollama = stdlib `urllib`), so `requirements.txt` is unchanged and the CI `cli-tests` job picks up the new tests automatically.
