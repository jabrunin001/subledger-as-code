from pathlib import Path
from audit_cli import pack
from audit_cli.models import TestResult

def test_build_pack_embeds_triage_and_manifest_covers_them(tmp_path):
    pack_dir = pack.build_pack(
        out_dir=str(tmp_path),
        results=[TestResult(unique_id="test.subledger.assert_rollforward_reconciles", status="fail")],
        lineage=[],
        reconciliation_md="# r\n",
        dbt_version="1.8.9",
        git_sha="deadbee",
        triage_md="# Variance Triage\nwrong_account\n",
        triage_json='{"findings": [], "backend_requested": "heuristic"}',
    )
    p = Path(pack_dir)
    assert (p / "triage.md").exists()
    assert (p / "triage.json").exists()
    manifest = (p / "MANIFEST.sha256").read_text()
    assert "triage.md" in manifest and "triage.json" in manifest
    assert pack.verify_manifest(pack_dir) == []  # freshly built pack verifies clean

def test_build_pack_without_triage_is_unchanged(tmp_path):
    pack_dir = pack.build_pack(
        out_dir=str(tmp_path),
        results=[], lineage=[], reconciliation_md="# r\n",
        dbt_version="1.8.9", git_sha="abc1234",
    )
    p = Path(pack_dir)
    assert not (p / "triage.md").exists()
    assert pack.verify_manifest(pack_dir) == []
