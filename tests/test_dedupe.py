import json
from app.history import History
from app.schemas import TriageRequest
from app.batch import predict_lines
from app.core import TriageService
from app.rules import RuleIndex


def request(reporter='one', text='Где магазин'):
    return TriageRequest(kind='report', reporter_hash=reporter, messages=[{'role': 'player', 'text': text}])


def test_window_identity_reporter_and_fifth_ticket():
    store = History()
    try:
        for n in range(5):
            assert store.observe(request(), str(n), n * 100) == n + 1
        assert store.observe(request(), '4', 450) == 5
        assert store.observe(request('other'), 'other', 450) == 1
        assert store.observe(request(), 'late', 4001) == 1
    finally:
        store.close()


def test_exact_hour_boundary_is_included():
    store = History()
    assert store.observe(request(), 'a', 0) == 1
    assert store.observe(request(), 'b', 3600) == 2
    store.close()


def test_batch_sorts_time_restores_order_and_repeats_deterministically():
    rows = [dict(request().model_dump(), ticket_id=str(n), created_at=f'2026-10-30T10:0{n}:00Z') for n in range(5)]
    lines = [json.dumps(row) for row in reversed(rows)] + ['invalid']
    service = TriageService(RuleIndex([]))
    outputs = list(predict_lines(lines, service, history=True))
    assert outputs == list(predict_lines(lines, service, history=True))
    assert 'five_tickets_within_hour' in outputs[0]['reasons']
    assert outputs[4]['is_spam_or_duplicate'] is False
    assert outputs[-1] == {'error': 'invalid_input'}


def test_sqlite_survives_reopening_without_raw_text(tmp_path):
    path = tmp_path / 'history.sqlite'
    store = History(path)
    store.observe(request(), 'one', 0)
    store.close()
    store = History(path)
    assert store.observe(request(), 'two', 1) == 2
    assert 'Где магазин'.encode() not in path.read_bytes()
    store.close()


def test_http_history_identity_conflict_and_retry(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app.api import create_app
    from test_core import RULES
    monkeypatch.setenv('GRAND_HISTORY_PATH', str(tmp_path / 'http.sqlite'))
    with TestClient(create_app(TriageService(RuleIndex.from_data(RULES)))) as client:
        body = request().model_dump()
        first = client.post('/triage', json=body, headers={'X-Ticket-ID': 'one'})
        retry = client.post('/triage', json=body, headers={'X-Ticket-ID': 'one'})
        assert first.json() == retry.json()
        repeated = client.post('/triage', json=body, headers={'X-Ticket-ID': 'two'})
        assert repeated.json()['is_spam_or_duplicate'] is True
        conflict = client.post('/triage', json=request(text='Другой вопрос').model_dump(), headers={'X-Ticket-ID': 'one'})
        assert conflict.status_code == 409
