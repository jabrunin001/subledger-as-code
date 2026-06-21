def render_statement(rows: list[dict]) -> str:
    lines = [
        "# Source-to-Ledger Reconciliation",
        "",
        "| account_id | expected_ending | ledger_ending | variance |",
        "| --- | ---: | ---: | ---: |",
    ]
    if not rows:
        lines.append("| _(no variances — all accounts reconcile)_ |  |  |  |")
    for r in rows:
        lines.append(
            f"| {r['account_id']} | {float(r['expected_ending']):.2f} | "
            f"{float(r['ledger_ending']):.2f} | {float(r['variance']):.2f} |"
        )
    return "\n".join(lines) + "\n"
