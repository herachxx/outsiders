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


def test_batch_history_accepts_export_timestamps_without_timezone_and_is_on_by_default(tmp_path):
    import json
    import subprocess
    import sys
    rows = [{'ticket_id': f't{i}', 'created_at': f'2026-08-01T10:0{i}:00', 'kind': 'complaint', 'reporter_hash': 'rep1',
             'reported_hash': 'bad1', 'messages': [{'role': 'player', 'text': 'оск родни в чате'}]} for i in range(3)]
    rows.append({**rows[0], 'ticket_id': 'other', 'reporter_hash': 'rep2'})
    source, out = tmp_path / 'in.jsonl', tmp_path / 'out.jsonl'
    source.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')
    subprocess.run([sys.executable, '-m', 'app.batch', '--input', str(source), '--output', str(out)],
                   check=True, capture_output=True)
    result = [json.loads(line) for line in out.read_text(encoding='utf-8').splitlines()]
    assert [r['is_spam_or_duplicate'] for r in result] == [False, True, True, False]
    assert not any('history_metadata_missing_or_invalid' in r['reasons'] for r in result)
    subprocess.run([sys.executable, '-m', 'app.batch', '--input', str(source), '--output', str(tmp_path / 'no.jsonl'), '--no-history'],
                   check=True, capture_output=True)
    plain = [json.loads(line) for line in (tmp_path / 'no.jsonl').read_text(encoding='utf-8').splitlines()]
    assert not any(r['is_spam_or_duplicate'] for r in plain)


def test_batch_reused_ticket_id_keeps_the_result_and_flags_the_conflict(tmp_path):
    import json
    import subprocess
    import sys
    base = {'ticket_id': 'same', 'kind': 'report', 'reporter_hash': 'r', 'created_at': '2026-08-01T10:00:00'}
    rows = [{**base, 'messages': [{'role': 'player', 'text': 'где автошкола'}]},
            {**base, 'created_at': '2026-08-01T10:05:00', 'messages': [{'role': 'player', 'text': 'совсем другой вопрос'}]}]
    source, out = tmp_path / 'in.jsonl', tmp_path / 'out.jsonl'
    source.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')
    subprocess.run([sys.executable, '-m', 'app.batch', '--input', str(source), '--output', str(out)], check=True, capture_output=True)
    result = [json.loads(line) for line in out.read_text(encoding='utf-8').splitlines()]
    assert all('error' not in r for r in result)
    assert 'history_identity_conflict' in result[1]['reasons']


def test_near_copies_from_one_reporter_count_as_the_same_problem_but_other_topics_do_not():
    from app.history import History
    from app.schemas import TriageRequest

    def req(text, reporter='r1', target='bad'):
        return TriageRequest(kind='complaint', reporter_hash=reporter, reported_hash=target,
                             messages=[{'role': 'player', 'text': text}])
    history = History()
    base = 'игрок оскорбил меня и мою семью в общем чате'
    assert history.observe(req(base), 'a', 1000.0) == 1
    assert history.observe(req(base + ' пожалуйста накажите'), 'b', 1100.0) == 2          # near copy
    assert history.observe(req('он читер летает по воздуху над банком'), 'c', 1200.0) == 1   # another problem
    assert history.observe(req(base, reporter='r2'), 'd', 1300.0) == 1                       # another reporter
    assert history.observe(req(base), 'e', 1400.0) == 3
    assert history.observe(req(base), 'f', 1000.0 + 3600 + 1) == 3                           # the first copy (t=1000) fell out of the hour
    assert history.observe(req('ау'), 'g', 1500.0) == 1 and history.observe(req('ау'), 'h', 1501.0) == 2   # exact short repeats


def test_old_history_database_is_upgraded(tmp_path):
    import sqlite3
    from app.history import History
    path = tmp_path / 'old.sqlite'
    connection = sqlite3.connect(path)
    connection.execute('CREATE TABLE history (id TEXT PRIMARY KEY, ts REAL, problem TEXT, count INTEGER)')
    connection.commit()
    connection.close()
    history = History(str(path))
    assert [row[1] for row in history.connection.execute('PRAGMA table_info(history)')][-2:] == ['scope', 'tokens']
