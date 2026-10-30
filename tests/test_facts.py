from app.facts import extract_facts
from app.core import TriageService
from app.rules import RuleIndex


def test_roles_offsets_and_denial_remain_source_statements():
    payload = {'kind': 'complaint', 'images_count': 2, 'messages': [
        {'role': 'player', 'text': '  Он использует читы  '},
        {'role': 'reported_player', 'text': 'Я не использую читы', 'attachments': 1},
        {'role': 'admin', 'text': 'Нарушение подтверждено'},
        {'role': 'player', 'text': 'Позднее сообщение'}]}
    facts = extract_facts(payload)
    statements = [f for f in facts if f.kind != 'metadata']
    assert [f.kind for f in statements] == ['claim', 'reported_player_statement']
    assert statements[0].value == payload['messages'][0]['text'][statements[0].start:statements[0].end]
    assert statements[1].value == 'Я не использую читы'
    assert not any(f.kind == 'verified' for f in facts)
    assert TriageService(RuleIndex([])).triage(payload)['extracted']['claims'] == ['Он использует читы']


def test_empty_text_and_attachments_are_only_metadata():
    facts = extract_facts({'kind': 'report', 'messages': [{'role': 'player', 'text': ' ', 'attachments': 3}]})
    assert all(f.kind == 'metadata' for f in facts)


def test_separate_claims_keep_original_wording():
    result = TriageService(RuleIndex([])).triage({'kind': 'report', 'messages': [
        {'role': 'player', 'text': 'Я не платил'}, {'role': 'player', 'text': 'Только спрашиваю'}]})
    assert result['extracted']['claims'] == ['Я не платил', 'Только спрашиваю']
