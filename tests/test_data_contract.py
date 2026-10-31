import gzip
import json

from scripts.inspect_data import inspect_tickets


def test_inspection_reports_errors_without_leaking_text(tmp_path):
    path = tmp_path / 'tickets.jsonl.gz'
    row = {'ticket_id': 'private-id', 'kind': 'report', 'lang': 'ru',
           'messages': [{'role': 'player', 'text': 'SECRET TEXT'}]}
    with gzip.open(path, 'wt', encoding='utf-8') as stream:
        stream.write(json.dumps(row) + '\n' + json.dumps(row) + '\n{bad\n')
    result = inspect_tickets(path)
    assert result['rows'] == 3
    assert result['invalid_rows'] == 1
    assert result['duplicate_ids'] == 1
    assert 'SECRET' not in json.dumps(result)
    assert 'private-id' not in json.dumps(result)
