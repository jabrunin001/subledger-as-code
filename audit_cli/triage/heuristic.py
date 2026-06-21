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
        f"between them rather than created or lost. That points to a posting leg targeting "
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
        "reallocation); only the substantive source-to-ledger reconciliation catches it."
    )
    return text, next_step


def _explain_value_imbalance(cluster, candidate_rules, net) -> tuple[str, str]:
    accounts = sorted(v.account_id for v in cluster)
    text = (
        f"Account(s) {', '.join(accounts)} show a net variance of {net:+.2f} that does not net to zero "
        f"against another account, indicating aggregate value changed: a missing or duplicated leg, "
        f"or an amount error, rather than a reallocation. (A true global imbalance would also trip the "
        f"trial-balance control; a single-account residual points at that account's source postings.)"
    )
    next_step = (
        "Check the candidate posting rules and the source events for the affected account(s) for a "
        "dropped, duplicated, or mis-valued leg."
    )
    return text, next_step
