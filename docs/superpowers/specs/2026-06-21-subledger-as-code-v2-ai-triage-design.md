# Subledger-as-Code — v2 Design Spec: AI-Assisted Variance Triage

**Date:** 2026-06-21
**Status:** Approved (brainstorming complete; pending spec review → implementation plan)
**Builds on:** v1 (shipped) — `docs/superpowers/specs/2026-06-21-subledger-as-code-v1-design.md`

## Purpose & framing

v1 built a runnable double-entry subledger whose substantive reconciliation control provably catches a
balanced-but-wrong-account posting (the `inject_break`), producing a symmetric ±Σinterest variance on
`cash`/`interest_income` and packaging it as auditor evidence. v2 adds **AI-assisted variance triage**:
given the reconciliation variances a control surfaces, automatically **classify the root cause, point at
the likely locus in the posting logic, and explain it in plain English** — so reconciliation exceptions
arrive pre-triaged instead of being debugged by hand.

This remains a **portfolio piece** in the same public repo (`github.com/jabrunin001/subledger-as-code`).
It must preserve v1's defining strengths: clone-and-run free, CI green and deterministic, no credentials.

### Key decisions (from brainstorming)

- **LLM = local Ollama, not a hosted model.** Inference runs locally, so the prompt — which contains
  financial variances and posting rules — never leaves the machine. That privacy property is the
  compliance narrative, enforced by architecture rather than promised. No cloud-LLM API keys anywhere.
- **Graceful degradation is the core.** One `TriageEngine` interface with two backends: a **deterministic
  heuristic backend** (default, offline, free, CI-tested, the fallback) and an **Ollama local-LLM backend**
  (opt-in, richer prose). Anything that can go wrong with Ollama falls back to the heuristic — the feature
  never hard-fails for lack of a model.
- **Finding shape:** cluster related variances (a symmetric ±X pair = one break) → classify from a small
  taxonomy + confidence → point at the candidate posting-rules locus → natural-language explanation +
  recommended next step. **No auto-fixing** of posting logic (risky/overclaiming).
- **Pack stays deterministic.** `pack` embeds the **heuristic** triage output (checksummed, CI-green);
  Ollama's non-deterministic output is for the ad-hoc `triage` command and the README demo only.
- **Honesty guard:** the LLM may enrich the prose but cannot flip a classification the deterministic
  `net_variance` signal already establishes.

### Out of scope for v2 (deferred)

- Auto-proposed posting-rule fixes / diffs.
- Hosted-LLM backends (Anthropic/OpenAI/etc.).
- Triage of exception types v1's data never generates (timing/source-data) beyond reserving the taxonomy
  slots; the heuristic returns `UNKNOWN` rather than over-claim.
- Spec 3 (optional, unchanged): live-Snowflake deep-dive.

## Architecture & module boundaries

A new `audit_cli/triage/` package, each unit independently testable:

```
audit_cli/triage/
├── __init__.py
├── models.py          # Pydantic: Variance, CandidateRule, TriageFinding, TriageReport + RootCause/Confidence enums
├── context.py         # load triage inputs from DuckDB: variances, posting_rules, dim_account (normal_balance), affected journal lines
├── cluster.py         # pure: group variances into related clusters (net-zero set = one break)
├── heuristic.py       # deterministic backend: cluster + context → TriageFinding (default / CI / fallback)
├── ollama_backend.py  # local-LLM backend: probe + prompt + call local Ollama → validated TriageFinding
├── engine.py          # orchestration: load context → cluster → select backend (+ fallback) → TriageReport
└── render.py          # TriageReport → triage.md
```

**Backend selection:** `engine.triage(backend=...)` accepts `heuristic` (default), `ollama`, or `auto`.
`ollama`/`auto` probe for a reachable local Ollama daemon; on daemon-down, model error, or validation
failure they fall back to the heuristic, recording which backend produced each finding.

**Dependency stance:** the heuristic path needs **zero new dependencies**. The Ollama path uses the Python
**stdlib `urllib`** against Ollama's local HTTP API — no SDK. Model configurable via `OLLAMA_MODEL`
(default a small instruct model, e.g. `llama3.1:8b`); host via `OLLAMA_HOST` (default
`http://localhost:11434`).

## Triage data model & taxonomy

`audit_cli/triage/models.py` (Pydantic v2):

```python
class RootCause(str, Enum):
    WRONG_ACCOUNT   = "wrong_account"      # balanced misallocation between accounts (the inject_break case)
    VALUE_IMBALANCE = "value_imbalance"    # cluster doesn't net to zero → missing/extra leg or amount error
    TIMING          = "timing"             # cutoff/period-boundary mismatch (reserved; not auto-claimed in v2)
    SOURCE_DATA     = "source_data"        # upstream/source-row anomaly (reserved; not auto-claimed in v2)
    UNKNOWN         = "unknown"            # no confident classification

class Confidence(str, Enum):
    HIGH = "high"; MEDIUM = "medium"; LOW = "low"

class Variance(BaseModel):
    account_id: str
    expected_ending: float
    ledger_ending: float
    variance: float                   # expected − ledger (v1 convention)

class CandidateRule(BaseModel):
    event_type: str
    leg: int
    account_id: str
    dr_cr: str
    amount_source: str

class TriageFinding(BaseModel):
    finding_id: str                   # stable id derived from the sorted account set
    accounts: list[str]
    net_variance: float               # signed sum across the cluster (~0 ⇒ balanced reallocation)
    root_cause: RootCause
    confidence: Confidence
    candidate_rules: list[CandidateRule]
    explanation: str                  # heuristic = templated; ollama = richer NL
    next_step: str
    backend: str                      # "heuristic" | "ollama" — provenance of THIS finding

class TriageReport(BaseModel):
    findings: list[TriageFinding]
    backend_requested: str
    generated_from_run: str | None
```

`net_variance ≈ 0` is the deterministic signal separating a *balanced misallocation* (`wrong_account`)
from a *value imbalance* (`value_imbalance`). `candidate_rules` is the concrete "where to look," pulled
from the actual `posting_rules` seed. Per-finding `backend` makes heuristic-vs-Ollama provenance auditable.

## Heuristic backend (deterministic reasoning)

The default; genuinely useful, not a stub.

**Clustering (`cluster.py`, pure):** greedily group variances whose signed `variance` values sum to ~0
(within 0.005) into one cluster — a symmetric ±X pair (or n-way net-zero set) is one underlying break.
A variance that can't be paired into a net-zero group stands alone.

**Classification (`heuristic.py`):**
- `net_variance ≈ 0` across ≥2 accounts → **`WRONG_ACCOUNT`**, `HIGH`. Value was reallocated between
  accounts — the signature of a misrouted leg (the `inject_break` case).
- `net_variance ≠ 0` → **`VALUE_IMBALANCE`**, `MEDIUM`. Aggregate value changed — dropped/duplicated leg
  or amount error; the explanation notes the global trial-balance control also flags true global
  imbalance, and a single-account residual points at that account's source.
- Single account, small residual, no rule match → **`UNKNOWN`/`LOW`**. `TIMING`/`SOURCE_DATA` are
  reserved; the heuristic does not guess them.

**Locus:** from `posting_rules`, select rows whose `account_id` is in the cluster → `candidate_rules`.
Direction is derived from the **rules + each account's `normal_balance`** (from `dim_account`), NOT from
the raw variance sign — because the sign's meaning flips between debit-normal and credit-normal accounts,
so a naive "over-stated = wrong destination" rule mislabels direction. The robust derivation: among the
cluster's `candidate_rules`, flag the leg whose legitimate target account shows the unmet expectation
(its ledger balance is missing the value the rule should have posted) as the **leading suspect**, and
identify the other cluster account as where that value appears to have landed. For the `inject_break`
case this deterministically points at the `payment`/`interest` leg whose target `interest_income` is
under-recognized while an offsetting amount sits in `cash`. The explanation presents this as the leading
hypothesis with the candidate rules attached, rather than an over-confident claim — classification and
locus are certain; the precise directional narrative is "most consistent with."

**Explanation + next step (templated, deterministic):** assembled from the above, plus a concrete next
step: "correct the implicated posting rule and re-run reconciliation; the trial-balance control stays
green because this is a balanced reallocation — only the substantive reconciliation catches it."

**Key property:** on the real `inject_break` variances the heuristic alone yields a correct, specific,
actionable finding (the exact mis-routed leg), with no LLM involved.

## Ollama local-LLM backend

Produces the **same `TriageFinding` schema**; only reasoning/prose quality differs.

- **Availability probe:** short-timeout request to `OLLAMA_HOST`; if it doesn't answer quickly, report
  unavailable → engine falls back. No hang on a fresh clone.
- **Prompt:** per cluster, include the chart of accounts, the cluster's variance rows, the `posting_rules`
  rows touching those accounts, and a tight instruction to classify from the exact enum, identify the
  implicated rule(s), explain in 2-3 sentences for an accountant, and give a next step. The model is
  **not** told a break was injected — it reasons from the variance signature.
- **Structured output:** request Ollama's `format: json`, constrained to the `TriageFinding` shape; parse
  and **validate through Pydantic** (validation is the contract).
- **Graceful failure → heuristic fallback** at every step: daemon down, model not pulled, HTTP error,
  timeout, invalid JSON, or Pydantic validation failure → that cluster's finding comes from the heuristic
  with `backend="heuristic"`. `--backend ollama` is always at least as good as heuristic.
- **Transport:** stdlib `urllib` against the local HTTP API; the HTTP boundary is the test seam (no live
  Ollama in CI).
- **Honesty guard:** cross-check the model's `root_cause` against the heuristic's deterministic
  `net_variance` signal; on disagreement, keep the deterministic classification and let the LLM supply
  only the prose. The LLM enriches explanations; it cannot flip a correct classification.

## CLI integration, evidence pack & CI

**New `triage` command** (`subledger-audit triage`): `--backend heuristic|ollama|auto` (default
`heuristic`), `--out` to write a report else print `triage.md` to stdout. Loads variances + posting_rules
+ affected journal lines from DuckDB, runs the engine, renders the report; with `ollama`/`auto` uses the
local model when reachable, else falls back and says so.

**`pack` integration (deterministic):** `pack` runs the engine with the **heuristic backend only** and
embeds `triage.json` (validated `TriageReport`) and `triage.md` into the evidence pack; both are folded
into `MANIFEST.sha256`, so the pack stays fully deterministic and checksum-verifiable in CI. Ollama never
touches the CI-built pack. The pack narrative upgrades from "a control caught an exception" to "and here
is the triage of that exception."

**CI (extends the existing 3 jobs, no new external deps):**
- `cli-tests` picks up the new triage unit + integration tests automatically.
- **Extend `control-proof`:** after confirming the break is caught, add a step asserting **heuristic
  triage on the broken run classifies it `wrong_account`, names the `cash`/`interest_income` accounts,
  and surfaces the implicated rule.** Deterministic; no Ollama.

## Testing strategy (TDD, deterministic)

- `cluster.py` (pure): symmetric pair → one cluster; non-netting variance → own cluster; multi-account
  net-zero set → one cluster; empty variances → empty report.
- `heuristic.py` (pure): fixture variances + `posting_rules` → assert `root_cause`, `confidence`,
  `candidate_rules`, and over/under-stated mapping; include the real `inject_break` signature →
  `WRONG_ACCOUNT` on `cash`/`interest_income`.
- `context.py`: against a fixture/built DuckDB — loaders return expected rows.
- `ollama_backend.py`: mock the HTTP seam. Test (a) prompt includes the variance + posting_rules context,
  (b) well-formed JSON → valid `TriageFinding`, (c) malformed JSON / HTTP error / daemon-down → heuristic
  fallback with `backend="heuristic"`, (d) honesty guard keeps deterministic classification on disagreement.
- `engine.py`: backend selection + fallback; `auto` with no daemon → heuristic.
- Integration: `pack` embeds deterministic `triage.json`/`triage.md` and `verify` still passes; triage
  runs end-to-end on the broken-run variances.
- `scripts/assert_break_caught.sh` companion / new control-proof step: heuristic triage classifies the break.

## README & demo additions

- New **"From detection to triage"** section after v1's "control in action": show the deterministic
  heuristic `triage.md` for the injected break, then a **recorded** Ollama `triage.md` for the same break,
  labeled "recorded output, local llama3.1 — your wording will vary." Same correct classification, richer
  prose.
- A short **"Local, private inference"** note: financial variances never leave the machine; Ollama
  optional; heuristic is the always-available default.
- Capability-map row: AI/LLM for data quality → `audit_cli/triage/` (local Ollama + deterministic fallback).
- Quickstart optional **"Try the local-LLM triage"** block: `ollama pull llama3.1:8b` then
  `subledger-audit triage --backend ollama`.

## Component boundaries (for isolation & testability)

- **context** (DuckDB → typed inputs): pure consumer of v1's `fct_balance_rollforward`, `posting_rules`,
  `dim_account` (for `normal_balance`), `fct_journal_lines`. No reasoning.
- **cluster** (variances → clusters): pure function, no I/O.
- **heuristic** (cluster + context → finding): pure, deterministic; the correctness core.
- **ollama_backend** (cluster + context → finding via local HTTP): isolated behind a mockable HTTP seam;
  always degradable to heuristic.
- **engine** (orchestration): selects backend, applies fallback + honesty guard, assembles `TriageReport`.
- **render** (report → markdown): pure.
- **CLI/pack**: `triage` command + `pack` embedding the deterministic report.

## Success criteria

- `subledger-audit triage` on the broken run (heuristic) classifies the break `wrong_account`, names
  `cash`/`interest_income`, and surfaces the implicated `payment`/`interest` posting rule.
- `pack` embeds deterministic `triage.json` + `triage.md`; `verify` still passes; CI stays green.
- The new `control-proof` CI step asserts heuristic triage correctly classifies the caught break.
- With Ollama unavailable (fresh clone / CI), every triage path still produces findings via heuristic
  fallback — no hard failure, no hang.
- With Ollama available, `--backend ollama` yields richer explanations with the same (deterministically
  guarded) classification, and the financial data never leaves the machine.
- README lets a reviewer see detection → triage end-to-end in under five minutes.
