from fastapi.testclient import TestClient

from app.api import create_app
from app.core import TriageService
from app.rules import RuleIndex

RULES = {"rules": [{"id": 30, "category": "Общие правила", "points": [
    {"ref": "2.1", "text": "Запрещены оскорбления игроков."},
    {"ref": "5.2", "text": "Запрещено использовать читы."},
]}]}

RECORD = {
    'ticket_id': 'abc123', 'created_at': '2026-10-01T10:00:00', 'kind': 'complaint', 'lang': 'ru',
    'region': 'kz', 'server_lang': 'ru', 'status': 2, 'images_count': 1, 'rule_refs_raw': '5.2 оп',
    'verdict': 'approved', 'punishment': 'бан на 31 день', 'violation': '5.2 ОП',
    'messages': [{'role': 'player', 'ts': '2026-10-01T10:00:00', 'text': 'читы <url>'},
                 {'role': 'admin', 'ts': '2026-10-01T11:00:00', 'text': 'жалоба одобрена'}],
}


def client():
    return TestClient(create_app(TriageService(RuleIndex.from_data(RULES))), client=('127.0.0.1', 50000))


def test_exported_record_is_accepted_and_outcome_fields_are_ignored():
    response = client().post('/integration/ticket', json=RECORD)
    assert response.status_code == 200
    body = response.json()
    assert body['ticket_id'] == 'abc123'
    assert body['result']['category'] == 'complaint.cheat'
    leaked = {**RECORD, 'verdict': 'rejected', 'punishment': 'x', 'violation': 'y'}
    assert client().post('/integration/ticket', json=leaked).json() == body


def test_ticket_id_is_required_and_bad_tickets_are_rejected():
    no_id = {k: v for k, v in RECORD.items() if k != 'ticket_id'}
    assert client().post('/integration/ticket', json=no_id).status_code == 422
    assert client().post('/integration/ticket', json={**RECORD, 'messages': []}).status_code == 422
    assert client().post('/integration/ticket', json={**RECORD, 'kind': 'other'}).status_code == 422


def test_api_key_is_enforced_when_configured(monkeypatch):
    monkeypatch.setenv('GRAND_API_KEY', 'secret-key')
    app_client = client()
    assert app_client.post('/integration/ticket', json=RECORD).status_code == 401
    assert app_client.post('/integration/ticket', json=RECORD, headers={'X-API-Key': 'wrong'}).status_code == 401
    assert app_client.post('/integration/ticket', json=RECORD, headers={'X-API-Key': 'secret-key'}).status_code == 200


def test_remote_integration_requires_key_but_local_remains_simple(monkeypatch):
    monkeypatch.delenv('GRAND_API_KEY', raising=False)
    app=create_app(TriageService(RuleIndex.from_data(RULES)))
    remote=TestClient(app,client=('192.0.2.10',50000))
    assert remote.post('/integration/ticket',json=RECORD).status_code==503
    assert remote.post('/integration/decision',json={'ticket_id':'x','action':'approved'}).status_code==503
    assert remote.get('/integration/decisions/stats').status_code==503
    assert client().post('/integration/ticket',json=RECORD).status_code==200


def test_no_rules_means_unavailable():
    unavailable = TestClient(create_app(TriageService(RuleIndex([]))))
    assert unavailable.post('/integration/ticket', json=RECORD).status_code == 503


def test_batch_cli_reads_and_writes_gzip(tmp_path):
    import gzip
    import json
    import subprocess
    import sys
    source, rules, out = tmp_path / 'in.jsonl.gz', tmp_path / 'rules.json', tmp_path / 'out.jsonl.gz'
    with gzip.open(source, 'wt', encoding='utf-8') as f:
        f.write(json.dumps({'kind': 'report', 'messages': [{'role': 'player', 'text': 'где автошкола?'}]}) + '\n')
        f.write('not json\n')
    rules.write_text(json.dumps(RULES), encoding='utf-8')
    subprocess.run([sys.executable, '-m', 'app.batch', '--input', str(source), '--output', str(out),
                    '--rules', str(rules)], check=True, capture_output=True)
    rows = [json.loads(line) for line in gzip.open(out, 'rt', encoding='utf-8')]
    assert len(rows) == 2 and rows[0]['category'] == 'report.question' and rows[1] == {'error': 'invalid_input'}


def test_batch_finds_rules_next_to_working_directory_or_runs_without(tmp_path):
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path
    env = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parent.parent)}
    env.pop('GRAND_RULES_PATH', None)
    source = tmp_path / 'in.jsonl'
    source.write_text(json.dumps({'kind': 'complaint', 'messages': [{'role': 'player', 'text': 'оск родни'}]},
                                 ensure_ascii=False) + '\n', encoding='utf-8')
    run = lambda out: subprocess.run([sys.executable, '-m', 'app.batch', '--input', str(source), '--output', str(out)],
                                     cwd=tmp_path, env=env, capture_output=True, text=True, check=True)
    without = run(tmp_path / 'a.jsonl')
    assert 'rules.json not found' in without.stderr
    assert json.loads((tmp_path / 'a.jsonl').read_text(encoding='utf-8'))['draft_reply']['cited'] == []
    (tmp_path / 'rules.json').write_text(json.dumps(RULES), encoding='utf-8')
    run(tmp_path / 'b.jsonl')
    assert json.loads((tmp_path / 'b.jsonl').read_text(encoding='utf-8'))['draft_reply']['cited'] == ['2.1']


def test_make_predict_style_json_array_in_and_out(tmp_path):
    import json
    import subprocess
    import sys
    tickets = [{'kind': 'report', 'messages': [{'role': 'player', 'text': 'где автошкола?'}]},
               {'kind': 'complaint', 'messages': [{'role': 'player', 'text': 'оск родни'}]}, 'oops', {'kind': 'x'}]
    source = tmp_path / 'tickets.json'
    source.write_text(json.dumps(tickets, ensure_ascii=False), encoding='utf-8')
    run = lambda *extra: subprocess.run([sys.executable, '-m', 'app.batch', '--input', str(source), '--output', str(tmp_path / 'pred.json'), *extra],
                                        check=True, capture_output=True, text=True)
    run()
    result = json.loads((tmp_path / 'pred.json').read_text(encoding='utf-8'))
    assert isinstance(result, list) and len(result) == 4
    assert result[0]['category'] == 'report.question' and result[1]['category'] == 'complaint.insult'
    assert result[2] == {'error': 'invalid_input'} and result[3] == {'error': 'invalid_input'}
    (tmp_path / 'pred.json').unlink()
    run('--output-format', 'jsonl')
    lines = (tmp_path / 'pred.json').read_text(encoding='utf-8').splitlines()
    assert len(lines) == 4 and json.loads(lines[0])['category'] == 'report.question'
    # a file that is not parseable at all still yields one error row, not a crash
    source.write_text('[{"kind": ', encoding='utf-8')
    (tmp_path / 'pred.json').unlink()
    run()
    assert json.loads((tmp_path / 'pred.json').read_text(encoding='utf-8')) == [{'error': 'invalid_input'}]
