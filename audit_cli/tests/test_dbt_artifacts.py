from pathlib import Path
from audit_cli import dbt_artifacts

FIX = Path(__file__).parent / "fixtures"

def test_parse_run_results_extracts_tests_only_then_summarizes():
    results = dbt_artifacts.parse_run_results(str(FIX / "run_results.json"))
    statuses = {r.unique_id: r.status for r in results}
    assert statuses["test.subledger.assert_trial_balance"] == "pass"
    assert statuses["test.subledger.assert_rollforward_reconciles"] == "fail"

    summary = dbt_artifacts.summarize(results)
    assert summary.total == 3
    assert summary.failed == 1
    assert summary.passed == 1

def test_parse_lineage_reads_depends_on():
    nodes = dbt_artifacts.parse_lineage(str(FIX / "manifest.json"))
    by_id = {n.unique_id: n.depends_on for n in nodes}
    assert "model.subledger.int_postings" in by_id["model.subledger.fct_journal_lines"]
