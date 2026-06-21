# Subledger-as-Code v1 design spec

**Date:** 2026-06-21
**Status:** Approved (brainstorming complete; pending spec review -> implementation plan)
**Project type:** Standalone portfolio showpiece (new directory `subledger-as-code/`, git init deferred to implementation)

## Purpose and framing

An open-source, runnable double-entry BNPL loan subledger built in dbt, with provable balance
controls and a Python CLI that packages auditor-ready evidence. The target audience is recruiters
and engineering leads evaluating analytics-engineering candidates: a recruiter skims it in about
5 minutes, a hiring manager reads deeper.

To work for that audience it has to (a) actually run for anyone who clones it, (b) unmistakably
signal dbt + dimensional modeling + SOX/audit + Snowflake competence, and (c) read cleanly top to
bottom. Legible signal takes priority over learning depth or breadth.

### Key decisions (from brainstorming)

- Portfolio showpiece is the primary goal: legible signal > learning depth > breadth.
- dbt-core + `dbt-duckdb` is the runnable default so it clones and runs free in about 60 seconds.
  Snowflake competence ships as portable artifacts (profile target, RBAC/masking/clustering DDL,
  tuning notes), not executed in CI.
- v1 scope: the core ledger vertical slice only. AI variance triage = spec 2. Snowflake deep-dive
  (live account, query-profile screenshots) = optional spec 3.
- Domain: BNPL loan subledger, scoped tight (see below). Realistic for a consumer-lending fintech
  but bounded for provable correctness.
- Signature feature: a toggleable injected break so the demo shows controls catching a realistic
  posting bug (RED -> fix -> GREEN), with the audit pack capturing the failure as evidence.
  This mirrors the "reproduce the failure, then fix it" pattern from the author's seat-reservation project.

### Out of scope for v1 (deferred)

- Spec 2: AI-assisted variance triage (LLM explains the reconciliation break it catches).
- Spec 3 (optional): Snowflake deep-dive with a live trial account and query-profile teardown.
- Domain deferrals: loan sales / gain-loss accounting, fee revenue, refinancing, delinquency
  staging, daily-compounding amortization.

## Architecture and data flow

Stack: dbt-core + `dbt-duckdb`; Python CLI (Typer + Pydantic); GitHub Actions CI. A `snowflake`
profile target + RBAC/masking/clustering DDL ship as portable artifacts, not run in CI.

```
seeds / synthetic events        staging           intermediate (posting engine)       canonical facts / marts          semantic
────────────────────────        ───────           ─────────────────────────────       ───────────────────────          ────────
raw_loan_originations      → stg_originations ┐
raw_installment_payments   → stg_payments     ├→ int_postings ───────────────────→ fct_journal_lines        ┐
raw_charge_offs            → stg_charge_offs  ┘  (event → balanced Dr/Cr legs       dim_account               ├→ mart_balances
seed_chart_of_accounts     → (dim source)        via post_entry macro +            dim_loan                   │   + metrics
seed_loan_master           → (dim source)        seed_posting_rules)               fct_balance_rollforward    ┘   (semantic layer)
```

The heart of the system is `int_postings`: every business event fans out into balanced double-entry
journal legs, driven by a posting-rules seed (`event_type -> debit_account, credit_account,
amount_expr`) applied through a `post_entry` dbt macro. One design choice puts macros, dimensional
modeling, and correctness-critical logic in one auditable place. It is also where the toggleable
break lives.

Two invariants the system is built to prove:
1. Internal consistency: every event's journal legs sum to zero (debits = credits), so the global
   trial balance always ties.
2. Substantive reconciliation: per account per period, the ledger-derived `ending balance =
   beginning + Σ movements`, where the movements are computed independently from source events (not
   from the journal lines). This is what catches a right-amount/wrong-account misposting that the
   internal-consistency checks cannot.

## Data model

### Seeds (version-controlled inputs)

- `seed_chart_of_accounts`: `account_id, account_name, account_type (asset/liability/revenue/expense),
  normal_balance (debit/credit)`. v1 accounts: Loans Receivable (asset/Dr), Cash (asset/Dr),
  Interest Income (revenue/Cr), Charge-off Expense (expense/Dr).
- `seed_loan_master`: synthetic loan dimension: `loan_id, borrower_id, principal, apr, term_months,
  origination_date`.
- `seed_posting_rules`: the posting engine's data: `event_type, leg, account_id, sign, amount_source`.
- Raw events from a deterministic Python seeder: `raw_loan_originations`, `raw_installment_payments`
  (each carries its principal/interest split), `raw_charge_offs`.

### Layers

- Staging (`stg_*`, 1:1 with sources): type-cast, rename to a consistent convention, light
  validation. No business logic.
- Intermediate (`int_postings`, posting engine): unions staged events, applies `post_entry(event)`
  which joins `seed_posting_rules` to emit one row per journal leg. Grain: one debit or credit line.
  Columns: `journal_entry_id, event_id, event_type, loan_id, account_id, dr_amount, cr_amount, posted_at`.
- Canonical facts and marts:
  - `fct_journal_lines`: the ledger. Grain = one leg. FK to `dim_account`, `dim_loan`.
  - `dim_account`, `dim_loan`: conformed dimensions from seeds.
  - `fct_balance_rollforward`: grain = account x period: `beginning_balance, originations,
    principal_repayments, charge_offs, interest, ending_balance`. Substantive reconciliation by
    construction: `beginning_balance` and `ending_balance` are derived from the ledger
    (`fct_journal_lines`), while the movement columns are computed independently from source events
    (staged originations/payments/charge-offs). So `ending = beginning + Σ movements` only holds if the
    postings agree with the source truth. A wrong-account posting breaks it.
- Semantic layer (thin): `mart_balances` plus a small MetricFlow `semantic_model` exposing three
  metrics: `loans_receivable_balance`, `interest_income`, `charge_off_rate`. Deliberately small:
  enough to demonstrate MetricFlow, not a sprawling catalog.

## Tests and controls

### a) Schema / generic tests
`not_null` + `unique` on keys; `relationships` `fct_journal_lines.account_id -> dim_account` and
`loan_id -> dim_loan`; `accepted_values` on `account_type`, `event_type`.

### b) dbt unit tests (dbt 1.8+ native)
Per event type, feed a fixture event and assert `post_entry` produces the right accounts, right signs,
balanced:
- origination -> `Dr Loans Receivable / Cr Cash`
- payment -> `Dr Cash / Cr Loans Receivable (principal) + Cr Interest Income (interest)`
- charge-off -> `Dr Charge-off Expense / Cr Loans Receivable`

### c) Singular data tests (the financial controls)
- Balanced entries (internal consistency): every `journal_entry_id` sums to zero (Σdr = Σcr).
- Trial balance (internal consistency): global Σdebits = Σcredits.
- Source-to-ledger rollforward reconciliation (substantive): for each account x period,
  ledger-derived `ending = beginning + Σ movements`, where movements come independently from source
  events. This is the control that catches a balanced-but-wrong-account posting.

### d) The toggleable break
A dbt var `inject_break` (default `false`). When `true`, one posting rule is corrupted (interest
credited to Cash instead of Interest Income). The entry stays balanced (still two legs), so the
balanced-entry and trial-balance tests stay GREEN. But the source-to-ledger rollforward
reconciliation goes RED, because the ledger's Cash/Interest-Income balances no longer match the
movements implied by the source events. That is the whole lesson: a right-amount/wrong-account error is
invisible to internal-consistency checks and only a substantive reconciliation catches it. That is a
far stronger SOX story than an obviously unbalanced entry.

### CI (GitHub Actions): three jobs
1. build+test: `dbt build` + `dbt test` on DuckDB. Must be green.
2. control-proof: `dbt build --vars 'inject_break: true'` -> asserts the rollforward
   reconciliation test fails (and confirms balanced-entry/trial-balance stay green), proving the
   substantive control catches the break rather than merely that green tests exist.
3. cli-tests: `pytest` on the Python CLI.

## Python audit-evidence CLI

`subledger-audit` is a Typer CLI with Pydantic models for the evidence schema: every evidence
artifact is a typed, validated model. It turns a dbt run into an auditor-ready evidence pack, the
deliverable a SOX auditor asks Accounting for.

Subcommands:
- `audit run`: invokes `dbt build`, then parses `target/run_results.json` + `manifest.json`.
- `audit pack`: assembles a timestamped pack into `evidence/<run_id>/`:
  - `test_results.json`: every test, pass/fail, duration, timestamp (control execution log).
  - `reconciliation.md`: trial-balance and rollforward statements, human-readable.
  - `lineage.json`: model lineage snapshot from the manifest (provenance).
  - `control_attestation.md`: one-page summary: controls run, pass/fail, run hash, dbt + git SHA.
  - `MANIFEST.sha256`: checksums of every file in the pack (tamper-evidence).
- `audit verify <pack>`: re-checks manifest checksums; confirms a pack is unaltered.

Demo: `audit pack` on a clean build produces a green attestation. Flip `inject_break: true`, run
again, and the pack documents the failed control with the exact reconciliation variance. The
"Accounting stops debugging reconciliation by hand" pitch, shown not told.

## Snowflake portability layer

- `profiles.yml` ships both `duckdb` (default/CI) and `snowflake` targets. Models use portable SQL;
  any dialect divergence is isolated behind macros.
- `snowflake/` directory with real, commented DDL:
  - `rbac.sql`: role hierarchy (`subledger_reader`, `subledger_transformer`, `auditor_ro`) + grants
    (least-privilege SOX story).
  - `masking_policies.sql`: column masking on PII (`borrower_id`, name fields) so `auditor_ro` sees
    masked values.
  - `clustering.sql`: recommended clustering key on `fct_journal_lines` (e.g. `(posted_at_month,
    account_id)`) with rationale.
- README subsection "Running on Snowflake": warehouse sizing, clustering rationale, query-pruning
  expectations.

## Repo layout and README narrative

For a portfolio piece, the README is the product.

```
subledger-as-code/
├── README.md            # the narrative (below)
├── dbt_project.yml
├── profiles.yml         # duckdb + snowflake targets
├── seeds/               # chart of accounts, loan master, posting rules
├── models/
│   ├── staging/
│   ├── intermediate/    # int_postings (the posting engine)
│   ├── marts/           # fct_journal_lines, dims, fct_balance_rollforward
│   └── semantic/        # mart_balances + MetricFlow models
├── macros/              # post_entry, break-injection
├── tests/               # singular data tests (balanced, trial balance, rollforward)
├── unit_tests/          # dbt unit tests for posting logic
├── snowflake/           # rbac, masking, clustering DDL
├── audit_cli/           # Typer + Pydantic CLI
│   └── tests/           # pytest
├── scripts/seed_events.py
└── .github/workflows/ci.yml   # build+test, control-proof, cli-tests
```

README arc (skim-optimized):
1. One-liner + architecture diagram (the data-flow above).
2. 60-second quickstart: clone -> `dbt build` -> `audit pack` -> open the evidence pack.
3. "The control in action": the RED->GREEN break demo with the reconciliation variance shown.
4. Capability map: a table linking each must-have capability (dbt models/tests/macros/CI/docs,
   dimensional modeling, Snowflake, Python, SOX evidence) to where it lives in the repo.
5. Running on Snowflake.
6. Roadmap: spec 2 (AI variance triage), spec 3 (Snowflake deep-dive).

## Component boundaries (for isolation and testability)

- Posting engine (`seed_posting_rules` + `post_entry` macro + `int_postings`): given an event,
  produces balanced legs. Testable in isolation via dbt unit tests. The break toggle lives here.
- Balance/rollforward models (`fct_journal_lines`, `fct_balance_rollforward`): given legs, produce
  balances that satisfy the rollforward equation. Verified by singular data tests.
- Audit CLI (`audit_cli/`): given dbt artifacts (`run_results.json`, `manifest.json`) + the
  reconciliation models, produces a typed, checksummed evidence pack. Pure consumer of dbt outputs;
  pytest-tested against fixture artifacts.
- Snowflake layer (`snowflake/`, `profiles.yml` target): static DDL + portable SQL; no runtime
  dependency from the rest of the pipeline.

## Success criteria

- `git clone` -> `dbt build` -> `dbt test` is green on DuckDB with zero external accounts.
- `dbt build --vars 'inject_break: true'` makes the source-to-ledger rollforward reconciliation test
  fail while balanced-entry and trial-balance stay green (the substantive control is what catches it).
- `subledger-audit pack` produces a complete, checksum-verified evidence pack for both the clean and
  broken runs.
- CI runs all three jobs green (including control-proof asserting failure-on-break).
- README lets a reviewer map every must-have capability to a file in under five minutes.
