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
