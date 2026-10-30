import os

from fastapi import FastAPI

from .core import TriageService
from .rules import RuleIndex
from .schemas import TriageRequest


def create_app(service: TriageService | None = None) -> FastAPI:
    if service is None:
        rules_path = os.environ.get("GRAND_RULES_PATH")
        service = TriageService(RuleIndex.from_file(rules_path) if rules_path else RuleIndex([]))
    app = FastAPI(title="Grand Mobile Support Copilot", version="0.1.0")

    @app.post("/triage")
    def triage(request: TriageRequest) -> dict:
        return service.triage(request)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "rules_loaded": bool(service.rules.rules)}

    return app


app = create_app()
