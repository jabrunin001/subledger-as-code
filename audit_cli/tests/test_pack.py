from pathlib import Path
from audit_cli import pack, reconciliation
from audit_cli.models import TestResult, LineageNode

def _results():
    return [
        TestResult(unique_id="test.subledger.assert_trial_balance", status="pass"),
        TestResult(unique_id="test.subledger.assert_rollforward_reconciles", status="fail",
                   message="Got 2 results"),
    ]

def test_render_statement_includes_variance():
    md = reconciliation.render_statement([
        {"account_id": "cash", "expected_ending": 100.0, "ledger_ending": 87.5,
         "variance": 12.5},
    ])
    assert "cash" in md and "12.5" in md

def test_build_pack_writes_all_artifacts_and_manifest(tmp_path):
    recon_md = reconciliation.render_statement([])
    pack_dir = pack.build_pack(
        out_dir=str(tmp_path),
        results=_results(),
        lineage=[LineageNode(unique_id="model.subledger.fct_journal_lines",
                             depends_on=["model.subledger.int_postings"])],
        reconciliation_md=recon_md,
        dbt_version="1.8.0",
        git_sha="abc1234",
    )
    p = Path(pack_dir)
    for name in ["test_results.json", "reconciliation.md", "lineage.json",
                 "control_attestation.md", "MANIFEST.sha256"]:
        assert (p / name).exists(), f"missing {name}"
    # Attestation reflects the failed control.
    attestation = (p / "control_attestation.md").read_text()
    assert "abc1234" in attestation
    assert "FAIL" in attestation.upper()
    assert "1.8.0" in attestation
    # Manifest verifies clean immediately after build.
    assert pack.verify_manifest(pack_dir) == []
