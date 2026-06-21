from audit_cli.triage.cluster import cluster_variances
from audit_cli.triage.models import Variance

def _v(acct, var):
    # expected/ledger are not used by clustering; only `variance` matters here.
    return Variance(account_id=acct, expected_ending=0.0, ledger_ending=0.0, variance=var)

def test_symmetric_pair_forms_one_cluster():
    clusters = cluster_variances([_v("cash", 4394.83), _v("interest_income", -4394.83)])
    assert len(clusters) == 1
    assert sorted(v.account_id for v in clusters[0]) == ["cash", "interest_income"]

def test_two_independent_pairs_form_two_clusters():
    clusters = cluster_variances([
        _v("a", 10.0), _v("b", -10.0), _v("c", 3.0), _v("d", -3.0),
    ])
    assert len(clusters) == 2
    assert all(len(c) == 2 for c in clusters)

def test_unmatched_variance_is_a_singleton():
    clusters = cluster_variances([_v("a", 10.0), _v("b", -10.0), _v("x", 7.0)])
    sizes = sorted(len(c) for c in clusters)
    assert sizes == [1, 2]

def test_empty_input_yields_no_clusters():
    assert cluster_variances([]) == []
