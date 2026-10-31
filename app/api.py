import hmac
import os
from contextlib import asynccontextmanager
from typing import Literal
from pydantic import ValidationError

from fastapi import Body, FastAPI, HTTPException, Header, Request

from .core import TriageService
from .rules import RuleIndex
from .schemas import TriageRequest, TriageResponse, SubmissionResponse
from .submission import to_submission
from .classifier import CategoryClassifier
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from pathlib import Path
from .schemas import StrictModel, Draft
from .support import auth
from .support.routes import create_routes
from .support.store import TicketStore


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
    decisions_path = os.environ.get('GRAND_DECISIONS_PATH')
    decisions = None
    if decisions_path:
        from scripts.sample_for_labeling import private_path
        from .decisions import Decisions
        decisions = Decisions(str(private_path(decisions_path)))
    api_key = os.environ.get('GRAND_API_KEY', '').strip()

    def check_key(x_api_key, request):
        if not api_key:
            from ipaddress import ip_address
            try:
                local = request.client is not None and ip_address(request.client.host).is_loopback
            except ValueError:
                local = False
            if not local:
                raise HTTPException(status_code=503, detail='Configure GRAND_API_KEY for remote integration access')
        if api_key and not (x_api_key and hmac.compare_digest(x_api_key, api_key)):
            raise HTTPException(status_code=401, detail='Invalid API key')

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            if history:
                history.close()
            if decisions:
                decisions.close()

    store = TicketStore(os.environ.get('GRAND_DB_PATH', 'data/support.sqlite3'))
    app = FastAPI(title='Grand Mobile Support Copilot', version='0.1.0', lifespan=lifespan)

    @app.middleware('http')
    async def safe_headers(request, call_next):
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        policy = ("default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'; "
                  "script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; font-src 'self'")
        response.headers['Content-Security-Policy'] = policy + ('; upgrade-insecure-requests' if request.url.scheme == 'https' else '')
        return response
    ui_path = Path(__file__).parent / 'ui'
    app.mount('/ui', StaticFiles(directory=ui_path), name='ui')

    @app.get('/', include_in_schema=False)
    def dashboard():
        return FileResponse(ui_path / 'index.html', headers={'Cache-Control': 'no-store'})

    @app.get('/admin', include_in_schema=False)
    def operator_dashboard(request: Request):
        if not auth.configured():
            return RedirectResponse('/admin/setup', status_code=303)
        if not auth.session(request):
            return RedirectResponse('/admin/login', status_code=303)
        return FileResponse(ui_path / 'admin.html', headers={'Cache-Control': 'no-store'})

    @app.get('/admin/login', include_in_schema=False)
    def operator_login(request: Request):
        if not auth.configured():
            return RedirectResponse('/admin/setup', status_code=303)
        if auth.session(request):
            return RedirectResponse('/admin', status_code=303)
        return FileResponse(ui_path / 'login.html', headers={'Cache-Control': 'no-store'})

    @app.get('/admin/setup', include_in_schema=False)
    def operator_setup(request: Request):
        if auth.configured():
            return RedirectResponse('/admin/login', status_code=303)
        return FileResponse(ui_path / 'setup.html', headers={'Cache-Control': 'no-store'})

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

    @app.post('/integration/ticket')
    def integration_ticket(http_request: Request, ticket: dict = Body(...), format: Literal['submission', 'internal'] = 'submission',
                           x_api_key: str | None = Header(default=None)) -> dict:
        """Accept a Grand Mobile ticket record as exported (outcome fields are ignored), return triage only."""
        check_key(x_api_key, http_request)
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
        handling = next((r.removeprefix('handling_') for r in result.reasons if r.startswith('handling_')), 'review')
        if decisions:
            decisions.propose(ticket_id, result.category, result.priority, handling)
        return {'ticket_id': ticket_id, 'handling': handling,
                'result': to_submission(result) if format == 'submission' else result.model_dump()}

    class DecisionRequest(StrictModel):
        ticket_id: str
        action: Literal['approved', 'edited', 'rejected']
        category: str | None = None
        priority: Literal['p0', 'p1', 'p2', 'p3'] | None = None

    @app.post('/integration/decision')
    def integration_decision(body: DecisionRequest, http_request: Request, x_api_key: str | None = Header(default=None)) -> dict:
        """Record what the administrator did with the service output: approve, edit or reject."""
        check_key(x_api_key, http_request)
        if decisions is None:
            raise HTTPException(status_code=503, detail='Decision log is not configured')
        from typing import get_args
        from .schemas import Category
        if body.category is not None and body.category not in get_args(Category):
            raise HTTPException(status_code=422, detail='Unknown category')
        try:
            decisions.decide(body.ticket_id, body.action, body.category, body.priority)
        except KeyError:
            raise HTTPException(status_code=404, detail='Unknown ticket') from None
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        return {'ticket_id': body.ticket_id, 'recorded': body.action}

    @app.get('/integration/decisions/stats')
    def integration_stats(http_request: Request, x_api_key: str | None = Header(default=None)) -> dict:
        check_key(x_api_key, http_request)
        if decisions is None:
            raise HTTPException(status_code=503, detail='Decision log is not configured')
        return decisions.stats()

    @app.get("/health")
    def health() -> dict:
        if not service.rules.rules:
            raise HTTPException(status_code=503, detail="Rules are not loaded")
        return {"status": "ok", "rules_loaded": True}

    app.include_router(create_routes(service, store))
    return app


_app = None


def __getattr__(name):
    """`uvicorn app.api:app` builds the application on first access, so importing this module has no side effects."""
    global _app
    if name == 'app':
        if _app is None:
            _app = create_app()
        return _app
    raise AttributeError(name)
