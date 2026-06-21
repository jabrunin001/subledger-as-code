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
