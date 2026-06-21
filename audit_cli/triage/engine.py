from .cluster import cluster_variances
from .heuristic import triage_cluster
from .models import TriageContext, TriageReport
from .ollama_backend import OllamaError


def run_triage(context: TriageContext, backend: str = "heuristic", ollama=None) -> TriageReport:
    clusters = cluster_variances(context.variances)
    use_ollama = backend in ("ollama", "auto") and ollama is not None and ollama.available()

    findings = []
    for cluster in clusters:
        finding = triage_cluster(cluster, context)  # deterministic spine
        if use_ollama:
            try:
                prose = ollama.explain(cluster, context)
                finding.explanation = prose.explanation
                finding.backend = "ollama"
                if prose.root_cause != finding.root_cause:
                    # Honesty guard: keep the deterministic classification; note the model's view.
                    finding.explanation += (
                        f"\n\n_(Local model suggested '{prose.root_cause.value}'; "
                        f"deterministic classification '{finding.root_cause.value}' retained.)_"
                    )
            except OllamaError:
                pass  # keep the heuristic finding for this cluster
        findings.append(finding)

    findings.sort(key=lambda f: f.finding_id)
    return TriageReport(
        findings=findings, backend_requested=backend, generated_from_run=context.run_label,
    )
