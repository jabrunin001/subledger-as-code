import os
import subprocess
import typer
from . import dbt_artifacts, pack as pack_mod, reconciliation

app = typer.Typer(help="Subledger audit-evidence packaging CLI.")

PROFILES_DIR = os.environ.get("DBT_PROFILES_DIR", ".")
TARGET_DIR = "target"

def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "nogit"

def _dbt_version() -> str:
    try:
        out = subprocess.check_output(["dbt", "--version"], text=True)
        for line in out.splitlines():
            if "installed" in line:
                return line.split(":")[-1].strip()
    except Exception:
        pass
    return "unknown"

def _query_variances(duckdb_path: str) -> list[dict]:
    import duckdb
    con = duckdb.connect(duckdb_path, read_only=True)
    try:
        rows = con.execute(
            """
            select account_id, expected_ending, ledger_ending,
                   expected_ending - ledger_ending as variance
            from fct_balance_rollforward
            where abs(expected_ending - ledger_ending) > 0.005
            """
        ).fetchall()
    finally:
        con.close()
    return [
        {"account_id": r[0], "expected_ending": float(r[1]),
         "ledger_ending": float(r[2]), "variance": float(r[3])}
        for r in rows
    ]

@app.command()
def run(inject_break: bool = typer.Option(False, "--inject-break")):
    """Run `dbt build` (optionally with the injected break)."""
    cmd = ["dbt", "build", "--profiles-dir", PROFILES_DIR]
    if inject_break:
        cmd += ["--vars", "inject_break: true"]
    raise typer.Exit(code=subprocess.call(cmd))

@app.command()
def pack(out_dir: str = typer.Option("evidence", "--out")):
    """Assemble a checksummed evidence pack from the latest dbt run."""
    results = dbt_artifacts.parse_run_results(os.path.join(TARGET_DIR, "run_results.json"))
    lineage = dbt_artifacts.parse_lineage(os.path.join(TARGET_DIR, "manifest.json"))
    duckdb_path = os.environ.get("DBT_DUCKDB_PATH", "subledger.duckdb")
    recon_md = reconciliation.render_statement(_query_variances(duckdb_path))
    pack_dir = pack_mod.build_pack(
        out_dir=out_dir, results=results, lineage=lineage,
        reconciliation_md=recon_md, dbt_version=_dbt_version(), git_sha=_git_sha(),
    )
    typer.echo(f"Evidence pack written to {pack_dir}")

@app.command()
def verify(pack_dir: str):
    """Verify a pack's checksums; exit non-zero if any file was altered."""
    mismatched = pack_mod.verify_manifest(pack_dir)
    if mismatched:
        for name in mismatched:
            typer.echo(f"TAMPERED: {name}")
        raise typer.Exit(code=1)
    typer.echo("Pack verified: all checksums match.")

if __name__ == "__main__":
    app()
