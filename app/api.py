import os
from typing import Literal
from pydantic import ValidationError

from fastapi import FastAPI, HTTPException

from .core import TriageService
from .rules import RuleIndex
from .schemas import TriageRequest, TriageResponse, SubmissionResponse
from .submission import to_submission


def create_app(service: TriageService | None = None) -> FastAPI:
    if service is None:
        rules_path = os.environ.get("GRAND_RULES_PATH")
        service = TriageService(RuleIndex.from_file(rules_path) if rules_path else RuleIndex([]))
    app = FastAPI(title="Grand Mobile Support Copilot", version="0.1.0")

    @app.post("/triage", response_model=SubmissionResponse | TriageResponse)
    def triage(request: TriageRequest, format: Literal['submission', 'internal'] = 'submission') -> dict:
        if not service.rules.rules:
            raise HTTPException(status_code=503, detail="Rules are not loaded")
        try:
            result = TriageResponse.model_validate(service.triage(request))
        except ValidationError:
            raise HTTPException(status_code=503, detail='Invalid service output') from None
        return to_submission(result) if format == 'submission' else result.model_dump()

    @app.get("/health")
    def health() -> dict:
        if not service.rules.rules:
            raise HTTPException(status_code=503, detail="Rules are not loaded")
        return {"status": "ok", "rules_loaded": True}

    return app


app = create_app()
