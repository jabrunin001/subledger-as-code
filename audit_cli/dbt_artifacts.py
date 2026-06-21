import json
from .models import TestResult, LineageNode, EvidenceSummary

def parse_run_results(path: str) -> list[TestResult]:
    with open(path) as f:
        data = json.load(f)
    return [TestResult.model_validate(r) for r in data.get("results", [])]

def parse_lineage(path: str) -> list[LineageNode]:
    with open(path) as f:
        data = json.load(f)
    nodes = []
    for uid, node in data.get("nodes", {}).items():
        deps = node.get("depends_on", {}).get("nodes", [])
        nodes.append(LineageNode(unique_id=uid, depends_on=deps))
    return nodes

def summarize(results: list[TestResult]) -> EvidenceSummary:
    tests = [r for r in results if r.unique_id.startswith("test.")]
    passed = sum(1 for r in tests if r.status == "pass")
    failed = sum(1 for r in tests if r.status == "fail")
    errored = sum(1 for r in tests if r.status == "error")
    return EvidenceSummary(total=len(results), passed=passed, failed=failed, errored=errored)
