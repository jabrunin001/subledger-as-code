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
