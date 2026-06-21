# Subledger-as-Code

A runnable, double-entry **BNPL loan subledger** in dbt + DuckDB whose **substantive
reconciliation control provably catches a posting bug** — packaged with a Python CLI
that produces auditor-ready, tamper-evident evidence. Built to mirror a SOX-compliant
financial-close platform.

## Architecture

```
seeds (synthetic events) → staging → int_postings (posting engine) → facts/dims → semantic
                                          │                              │
                            post_entry macro + posting_rules    fct_balance_rollforward
                                                                 (source-to-ledger reconciliation)
```

- **Posting engine** (`macros/post_entry.sql` + `seeds/posting_rules.csv` + `models/intermediate/int_postings.sql`): every event fans out into balanced double-entry legs, driven by data, not hardcoded SQL.
- **Two invariants:** (1) every entry's debits = credits (internal consistency); (2) ledger balances = balances re-derived independently from source events (substantive reconciliation).

## 60-second quickstart

Requires Python 3.11+ (see `.python-version`).

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
dbt build --profiles-dir .            # seeds → models → tests, all on DuckDB
python -m audit_cli.cli pack --out evidence
cat evidence/evidence-*/control_attestation.md   # macOS/Linux; or: open <path> (macOS)
```

No warehouse, no credentials, no network. It just runs.

The clean build completes with PASS=57, ERROR=0. The attestation file reads **PASS**.

## The control in action

A trial balance can't catch a *right-amount, wrong-account* error — only a substantive
reconciliation can. Prove it:

```bash
# Inject a realistic bug: payment interest credited to Cash instead of Interest Income.
# (Exclude unit tests from this build — they assert the *correct* posting and would otherwise
#  halt the run before the break reaches the materialized tables.)
dbt build --profiles-dir . --vars 'inject_break: true' --exclude resource_type:unit_test
dbt test  --profiles-dir . --vars 'inject_break: true' --select assert_trial_balance assert_entries_balanced   # both stay GREEN
dbt test  --profiles-dir . --vars 'inject_break: true' --select assert_rollforward_reconciles                  # goes RED (break caught)
# restore the clean ledger:
dbt build --profiles-dir .
```

Both internal-consistency controls stay green; the source-to-ledger reconciliation
goes red (FAIL 2, naming the offending accounts). The CI `control-proof` job asserts
exactly this.

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
# Variance Triage

_Backend requested: heuristic_

## cash+interest_income — wrong_account (high confidence)

- Accounts: cash, interest_income
- Net variance: +0.00
- Backend: heuristic
- Candidate rules: origination/2 credit cash (principal); payment/1 debit cash (total); payment/3 credit interest_income (interest)

Accounts cash and interest_income diverge from their source-derived expectations by offsetting
amounts (net +0.00 ≈ 0: cash +4394.83, interest_income -4394.83), indicating value was
reallocated between them rather than created or lost — most consistent with a posting leg
targeting the wrong account. Both accounts are posted by the 'payment' entry; the leg
crediting 'interest_income' (rule payment/3, amount_source 'interest') is the leading
suspect for misrouting.

**Next step:** Inspect the candidate posting rules for a leg posting to the wrong account;
correct it and re-run reconciliation. The trial-balance control will stay green (this is a
balanced reallocation) — only the substantive source-to-ledger reconciliation catches it.
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

## Capability map

| Requirement | Where it lives |
| --- | --- |
| Production dbt (models, tests, macros, docs) | `models/`, `tests/`, `macros/post_entry.sql`, `_*.yml` |
| dbt unit tests | `unit_tests/int_postings_unit_tests.yml` |
| Dimensional modeling | `models/marts/` (facts + conformed dims) |
| SQL + correctness-critical logic | posting engine + reconciliation models (`models/intermediate/int_postings.sql`, `models/marts/fct_balance_rollforward.sql`) |
| Python for financial data | `audit_cli/` (Typer + Pydantic), `scripts/seed_events.py` |
| CI | `.github/workflows/ci.yml` (build+test, control-proof, cli-tests) |
| SOX controls / audit evidence | `tests/assert_*.sql`, `audit_cli/` evidence packs |
| Snowflake (RBAC, masking, clustering) | `snowflake/`, `profiles.yml` snowflake target |
| Semantic layer | `models/semantic/` (MetricFlow) |
| AI/LLM for data quality | `audit_cli/triage/` (deterministic heuristic + optional local Ollama) |

## Running on Snowflake

The default target is DuckDB so this clones-and-runs free. To run on Snowflake, set the
`SNOWFLAKE_*` env vars (see `profiles.yml`) and `dbt build --profiles-dir . --target snowflake`.
Apply `snowflake/rbac.sql`, `snowflake/masking_policies.sql`, and `snowflake/clustering.sql`
first. Clustering `fct_journal_lines` by `(month, account_id)` prunes micro-partitions on the
period+account reconciliation queries; size the warehouse to XS for this data volume.

## Roadmap

- **Spec 3 (optional) — Snowflake deep-dive:** live trial account with query-profile teardown.
