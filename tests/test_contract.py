import json
import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient
from app.api import create_app
from app.batch import predict_lines
from app.core import TriageService
from app.rules import RuleIndex
from app.schemas import TriageRequest, TriageResponse
from app.submission import to_submission


def request():
    return {'kind': 'report', 'messages': [{'role': 'player', 'text': 'Оплатил донат'}]}


@pytest.mark.parametrize('change', [
    {'unknown': 'secret'}, {'images_count': '2'}, {'images_count': -1},
    {'messages': [{'role': 'player', 'text': 'x' * 20001}]},
])
def test_bad_request_is_rejected(change):
    with pytest.raises(ValidationError):
        TriageRequest.model_validate({**request(), **change})


def test_pdf_attachment_count_is_accepted():
    data = request()
    data['messages'][0]['attachments'] = 2
    assert TriageRequest.model_validate(data).messages[0].attachments == 2


def test_submission_and_http_batch_agree():
    service = TriageService(RuleIndex.from_data({'rules': [
        {'id': 30, 'category': 'Synthetic', 'points': [{'ref': '2.1', 'text': 'Запрещены оскорбления игроков.'}]}
    ]}))
    internal = service.triage(request())
    parsed = TriageResponse.model_validate(internal)
    assert to_submission(parsed)['draft_reply']['cited'] == []
    client = TestClient(create_app(service))
    assert client.post('/triage', json=request()).json() == list(predict_lines([json.dumps(request())], service))[0]
    assert client.post('/triage?format=internal', json=request()).json() == internal
    assert client.post('/triage', json={**request(), 'unknown': 'x'}).status_code == 422


def test_response_rejects_invalid_category_and_confidence():
    service = TriageService(RuleIndex([]))
    result = service.triage(request())
    for change in ({'category': 'invented'}, {'confidence': 1.1}):
        with pytest.raises(ValidationError):
            TriageResponse.model_validate({**result, **change})


def test_citation_export_preserves_internal_source():
    service = TriageService(RuleIndex.from_data({'rules': [
        {'id': 30, 'category': 'Synthetic', 'points': [{'ref': '2.1', 'text': 'Запрещены оскорбления игроков.'}]}
    ]}))
    data = {'kind': 'complaint', 'messages': [{'role': 'player', 'text': 'оскорбил'}], 'rule_refs_raw': '2.1'}
    internal = service.triage(data)
    assert to_submission(internal)['draft_reply']['cited'] == ['2.1']
    assert internal['draft_reply']['cited'][0]['section_id'] == 30


def test_historical_labels_do_not_change_batch_prediction():
    service = TriageService(RuleIndex([]))
    historical = {**request(), 'verdict': 'approved', 'punishment': 'SECRET', 'ticket_id': 'SECRET'}
    assert list(predict_lines([json.dumps(historical)], service)) == list(predict_lines([json.dumps(request())], service))
