from pathlib import Path
from typer.testing import CliRunner
from audit_cli import pack
from audit_cli.cli import app
from audit_cli.models import TestResult

runner = CliRunner()

def _build(tmp_path):
    return pack.build_pack(
        out_dir=str(tmp_path),
        results=[TestResult(unique_id="test.subledger.assert_trial_balance", status="pass")],
        lineage=[], reconciliation_md="# r\n", dbt_version="1.8.0", git_sha="deadbee",
    )

def test_verify_passes_on_intact_pack(tmp_path):
    pack_dir = _build(tmp_path)
    result = runner.invoke(app, ["verify", pack_dir])
    assert result.exit_code == 0

def test_verify_fails_on_tampered_pack(tmp_path):
    pack_dir = _build(tmp_path)
    # Tamper: append a byte to an evidence file after the manifest was written.
    target = Path(pack_dir) / "reconciliation.md"
    target.write_text(target.read_text() + "TAMPERED")
    result = runner.invoke(app, ["verify", pack_dir])
    assert result.exit_code != 0
    assert "reconciliation.md" in result.stdout
