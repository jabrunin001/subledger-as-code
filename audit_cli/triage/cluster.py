from .models import Variance

TOL = 0.005


def cluster_variances(variances: list[Variance], tol: float = TOL) -> list[list[Variance]]:
    """Group variances into clusters.

    A positive and an opposite-sign variance of equal magnitude (within ``tol``)
    form one cluster — a balanced reallocation between two accounts. Any variance
    that cannot be paired is its own singleton cluster. Deterministic: items are
    sorted by ``(-abs(variance), account_id)`` before greedy matching.

    n-way net-zero sets beyond simple pairs are out of scope for v2's data; the
    real reconciliation break is the symmetric two-account case.
    """
    items = sorted(variances, key=lambda v: (-abs(v.variance), v.account_id))
    used = [False] * len(items)
    clusters: list[list[Variance]] = []
    for i, v in enumerate(items):
        if used[i]:
            continue
        used[i] = True
        if abs(v.variance) <= tol:
            clusters.append([v])
            continue
        partner = None
        for j in range(i + 1, len(items)):
            if used[j]:
                continue
            w = items[j]
            opposite_sign = (v.variance > 0) != (w.variance > 0)
            if opposite_sign and abs(v.variance + w.variance) <= tol:
                partner = j
                break
        if partner is not None:
            used[partner] = True
            clusters.append([v, items[partner]])
        else:
            clusters.append([v])
    return clusters
