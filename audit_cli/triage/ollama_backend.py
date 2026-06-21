import json
import urllib.request

from pydantic import BaseModel

from .models import Account, RootCause, TriageContext, Variance


class OllamaError(Exception):
    """Any failure talking to the local Ollama daemon or parsing its output."""


class OllamaProse(BaseModel):
    root_cause: RootCause
    explanation: str


def _urllib_transport(url: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"},
                                 method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


class OllamaClient:
    def __init__(self, model: str, host: str, transport=_urllib_transport):
        self.model = model
        self.host = host.rstrip("/")
        self._transport = transport

    def available(self) -> bool:
        try:
            self._transport(f"{self.host}/api/tags", None)
            return True
        except Exception:
            return False

    def explain(self, cluster: list[Variance], context: TriageContext) -> OllamaProse:
        prompt = self._build_prompt(cluster, context)
        try:
            body = self._transport(f"{self.host}/api/generate", {
                "model": self.model, "prompt": prompt, "stream": False, "format": "json",
            })
            raw = body["response"]
            return OllamaProse.model_validate(json.loads(raw))
        except OllamaError:
            raise
        except Exception as e:
            # Any Ollama/transport/parse/validation failure is surfaced as OllamaError
            # so the engine can fall back to the deterministic heuristic for this cluster.
            raise OllamaError(str(e)) from e

    def _build_prompt(self, cluster: list[Variance], context: TriageContext) -> str:
        normals = {a.account_id: a for a in context.accounts}
        accts = sorted(v.account_id for v in cluster)
        rules = [r for r in context.posting_rules if r.account_id in accts]
        lines = [
            "You are a financial-controls assistant triaging a subledger reconciliation variance.",
            "Classify the root cause from EXACTLY this set: "
            "wrong_account, value_imbalance, timing, source_data, unknown.",
            "Do not assume a bug was injected; reason only from the data below.",
            "",
            "Variances (variance = expected_ending - ledger_ending):",
        ]
        for v in sorted(cluster, key=lambda v: v.account_id):
            acct = normals.get(v.account_id)
            nb = acct.normal_balance if acct else "?"
            lines.append(f"  - {v.account_id} (normal_balance={nb}): "
                         f"expected={v.expected_ending:.2f} ledger={v.ledger_ending:.2f} "
                         f"variance={v.variance:+.2f}")
        lines.append("")
        lines.append("Posting rules touching these accounts:")
        for r in rules:
            lines.append(f"  - {r.event_type}/{r.leg}: {r.dr_cr} {r.account_id} (amount_source={r.amount_source})")
        lines.append("")
        lines.append("Respond ONLY with JSON: {\"root_cause\": <one enum value>, "
                     "\"explanation\": <2-3 sentences for an accountant>}.")
        return "\n".join(lines)
