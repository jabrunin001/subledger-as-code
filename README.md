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
open evidence/evidence-*/control_attestation.md
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
dbt test  --profiles-dir . --vars 'inject_break: true' --select assert_trial_balance assert_entries_balanced   # stays GREEN
dbt test  --profiles-dir . --vars 'inject_break: true' --select assert_rollforward_reconciles                  # goes RED
# restore the clean ledger:
dbt build --profiles-dir .
```

The internal-consistency checks stay green (PASS=2); the source-to-ledger reconciliation
goes red (FAIL 2, naming the offending accounts). The CI `control-proof` job asserts
exactly this.

## JD-competency map

| Requirement | Where it lives |
| --- | --- |
| Production dbt (models, tests, macros, docs) | `models/`, `tests/`, `macros/post_entry.sql`, `_*.yml` |
| dbt unit tests | `unit_tests/int_postings_unit_tests.yml` |
| Dimensional modeling | `models/marts/` (facts + conformed dims) |
| SQL + correctness-critical logic | posting engine + reconciliation models |
| Python for financial data | `audit_cli/` (Typer + Pydantic), `scripts/seed_events.py` |
| CI | `.github/workflows/ci.yml` (build+test, control-proof, cli-tests) |
| SOX controls / audit evidence | `tests/assert_*.sql`, `audit_cli/` evidence packs |
| Snowflake (RBAC, masking, clustering) | `snowflake/`, `profiles.yml` snowflake target |
| Semantic layer | `models/semantic/` (MetricFlow) |

## Running on Snowflake

The default target is DuckDB so this clones-and-runs free. To run on Snowflake, set the
`SNOWFLAKE_*` env vars (see `profiles.yml`) and `dbt build --profiles-dir . --target snowflake`.
Apply `snowflake/rbac.sql`, `snowflake/masking_policies.sql`, and `snowflake/clustering.sql`
first. Clustering `fct_journal_lines` by `(month, account_id)` prunes micro-partitions on the
period+account reconciliation queries; size the warehouse to XS for this data volume.

## Roadmap

- **Spec 2 — AI-assisted variance triage:** an LLM explains each reconciliation break the
  control catches, turning the evidence pack into a triage assistant.
- **Spec 3 (optional) — Snowflake deep-dive:** live trial account with query-profile teardown.
