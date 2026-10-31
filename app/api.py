import hmac
import os
from contextlib import asynccontextmanager
from typing import Literal
from pydantic import ValidationError

from fastapi import Body, FastAPI, HTTPException, Header

from .core import TriageService
from .rules import RuleIndex
from .schemas import TriageRequest, TriageResponse, SubmissionResponse
from .submission import to_submission
from .classifier import CategoryClassifier
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from .schemas import StrictModel, Draft


class DraftCheckRequest(StrictModel):
    request: TriageRequest
    draft: Draft


def create_app(service: TriageService | None = None) -> FastAPI:
    if service is None:
        rules_path = os.environ.get("GRAND_RULES_PATH")
        model_path = os.environ.get('GRAND_MODEL_PATH')
        classifier = CategoryClassifier.load(model_path) if model_path else None
        service = TriageService(RuleIndex.from_file(rules_path) if rules_path else RuleIndex([]), classifier)
    history_path = os.environ.get('GRAND_HISTORY_PATH')
    history = None
    if history_path:
        from scripts.sample_for_labeling import private_path
        from .history import History
        history = History(str(private_path(history_path)))

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            if history:
                history.close()

    app = FastAPI(title='Grand Mobile Support Copilot', version='0.1.0', lifespan=lifespan)
    ui_path = Path(__file__).parent / 'ui'
    app.mount('/ui', StaticFiles(directory=ui_path), name='ui')

    @app.get('/', include_in_schema=False)
    def dashboard():
        return FileResponse(ui_path / 'index.html', headers={'Cache-Control': 'no-store'})

    @app.post('/draft/check')
    def check_edited_draft(payload: DraftCheckRequest):
        if not service.rules.rules:
            raise HTTPException(status_code=503, detail='Rules are not loaded')
        from .safety import check_draft
        result = service.triage(payload.request)
        checked, reasons = check_draft(payload.draft.model_dump(), service.rules, payload.request,
                                      result['category'], result['lang'], result['extracted']['has_evidence'])
        return {'approved': not reasons, 'draft': checked, 'reasons': reasons}

    @app.post("/triage", response_model=SubmissionResponse | TriageResponse)
    def triage(request: TriageRequest, format: Literal['submission', 'internal'] = 'submission',
               x_ticket_id: str | None = Header(default=None)) -> dict:
        if not service.rules.rules:
            raise HTTPException(status_code=503, detail="Rules are not loaded")
        try:
            output = service.triage(request)
            if history and x_ticket_id:
                import time
                from .dedupe import annotate_history
                try:
                    annotate_history(output, request, history, x_ticket_id, time.time())
                except ValueError:
                    raise HTTPException(status_code=409, detail='Ticket identity conflict') from None
            result = TriageResponse.model_validate(output)
        except ValidationError:
            raise HTTPException(status_code=503, detail='Invalid service output') from None
        return to_submission(result) if format == 'submission' else result.model_dump()

    api_key = os.environ.get('GRAND_API_KEY')

    @app.post('/integration/ticket')
    def integration_ticket(ticket: dict = Body(...), format: Literal['submission', 'internal'] = 'submission',
                           x_api_key: str | None = Header(default=None)) -> dict:
        """Accept a Grand Mobile ticket record as exported (outcome fields are ignored), return triage only."""
        if api_key and not (x_api_key and hmac.compare_digest(x_api_key, api_key)):
            raise HTTPException(status_code=401, detail='Invalid API key')
        if not service.rules.rules:
            raise HTTPException(status_code=503, detail='Rules are not loaded')
        ticket_id = ticket.get('ticket_id')
        if not isinstance(ticket_id, str) or not ticket_id.strip():
            raise HTTPException(status_code=422, detail='ticket_id is required')
        payload = {k: v for k, v in ticket.items() if k in TriageRequest.model_fields}
        try:
            request = TriageRequest.model_validate(payload)
        except ValidationError:
            raise HTTPException(status_code=422, detail='Invalid ticket') from None
        try:
            output = service.triage(request)
            if history:
                import time
                from .dedupe import annotate_history
                try:
                    annotate_history(output, request, history, ticket_id, time.time())
                except ValueError:
                    raise HTTPException(status_code=409, detail='Ticket identity conflict') from None
            result = TriageResponse.model_validate(output)
        except ValidationError:
            raise HTTPException(status_code=503, detail='Invalid service output') from None
        return {'ticket_id': ticket_id,
                'result': to_submission(result) if format == 'submission' else result.model_dump()}

    @app.get("/health")
    def health() -> dict:
        if not service.rules.rules:
            raise HTTPException(status_code=503, detail="Rules are not loaded")
        return {"status": "ok", "rules_loaded": True}

    return app


app = create_app()
