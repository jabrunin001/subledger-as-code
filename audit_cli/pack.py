import hashlib
import json
import os
from .models import TestResult, LineageNode, EvidenceSummary

def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def write_manifest(pack_dir: str) -> str:
    manifest_path = os.path.join(pack_dir, "MANIFEST.sha256")
    entries = []
    for name in sorted(os.listdir(pack_dir)):
        if name == "MANIFEST.sha256":
            continue
        entries.append(f"{_sha256(os.path.join(pack_dir, name))}  {name}")
    with open(manifest_path, "w") as f:
        f.write("\n".join(entries) + "\n")
    return manifest_path

def verify_manifest(pack_dir: str) -> list[str]:
    manifest_path = os.path.join(pack_dir, "MANIFEST.sha256")
    mismatched = []
    with open(manifest_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            expected, name = line.split("  ", 1)
            actual = _sha256(os.path.join(pack_dir, name))
            if actual != expected:
                mismatched.append(name)
    return mismatched

def _attestation(summary: EvidenceSummary, dbt_version: str, git_sha: str) -> str:
    overall = "FAIL" if (summary.failed or summary.errored) else "PASS"
    return (
        "# Control Attestation\n\n"
        f"- Overall control status: **{overall}**\n"
        f"- Tests passed: {summary.passed}\n"
        f"- Tests failed: {summary.failed}\n"
        f"- Tests errored: {summary.errored}\n"
        f"- dbt version: {dbt_version}\n"
        f"- git SHA: {git_sha}\n"
    )

def build_pack(out_dir: str, results: list[TestResult], lineage: list[LineageNode],
               reconciliation_md: str, dbt_version: str, git_sha: str,
               triage_md: str | None = None, triage_json: str | None = None) -> str:
    summary = EvidenceSummary(
        total=len(results),
        passed=sum(1 for r in results if r.unique_id.startswith("test.") and r.status == "pass"),
        failed=sum(1 for r in results if r.unique_id.startswith("test.") and r.status == "fail"),
        errored=sum(1 for r in results if r.unique_id.startswith("test.") and r.status == "error"),
    )
    pack_dir = os.path.join(out_dir, f"evidence-{git_sha}")
    os.makedirs(pack_dir, exist_ok=True)

    with open(os.path.join(pack_dir, "test_results.json"), "w") as f:
        json.dump([r.model_dump() for r in results], f, indent=2)
    with open(os.path.join(pack_dir, "lineage.json"), "w") as f:
        json.dump([n.model_dump() for n in lineage], f, indent=2)
    with open(os.path.join(pack_dir, "reconciliation.md"), "w") as f:
        f.write(reconciliation_md)
    with open(os.path.join(pack_dir, "control_attestation.md"), "w") as f:
        f.write(_attestation(summary, dbt_version, git_sha))
    if triage_md is not None:
        with open(os.path.join(pack_dir, "triage.md"), "w") as f:
            f.write(triage_md)
    if triage_json is not None:
        with open(os.path.join(pack_dir, "triage.json"), "w") as f:
            f.write(triage_json)

    write_manifest(pack_dir)
    return pack_dir
