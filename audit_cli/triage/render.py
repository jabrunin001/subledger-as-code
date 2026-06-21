from .models import TriageReport


def render_triage_md(report: TriageReport) -> str:
    lines = ["# Variance Triage", "", f"_Backend requested: {report.backend_requested}_", ""]
    if not report.findings:
        lines.append("_No reconciliation variances to triage; the ledger reconciles._")
        return "\n".join(lines) + "\n"
    for f in report.findings:
        lines.append(f"## {f.finding_id}: {f.root_cause.value} ({f.confidence.value} confidence)")
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
