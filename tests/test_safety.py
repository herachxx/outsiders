import pytest
from app.safety import check_draft
from app.draft import build_draft
from app.schemas import TriageRequest
from app.rules import RuleIndex


def setup():
    request = TriageRequest(kind='complaint', messages=[{'role': 'player', 'text': 'Игрок использует читы'}])
    rules = RuleIndex.from_data({'rules': [{'id': 99, 'category': 'Тест', 'points': [
        {'ref': '5.2', 'text': 'Запрещены читы.'}]}]})
    return request, rules


def test_valid_template_and_current_citation_pass():
    request, rules = setup()
    draft = build_draft(request, 'complaint.cheat', 'ru', True, [rules.rules[0].citation()])
    checked, reasons = check_draft(draft, rules, request, 'complaint.cheat', 'ru', True)
    assert checked == draft and reasons == []


@pytest.mark.parametrize('candidate', ['not JSON', {}, {'lang': 'ru', 'text': 'Забаним игрока', 'cited': []},
    {'lang': 'en', 'text': 'Send your password', 'cited': []},
    {'lang': 'uz', 'text': 'Ignore instructions: 9.9', 'cited': []}])
def test_invalid_or_unapproved_draft_becomes_neutral_fallback(candidate):
    request, rules = setup()
    checked, reasons = check_draft(candidate, rules, request, 'complaint.cheat', 'ru', True)
    assert reasons and checked['cited'] == []
    assert 'проверка администратором' in checked['text']


def test_forged_citation_and_old_version_are_removed_with_text():
    request, rules = setup()
    citation = {**rules.rules[0].citation(), 'rules_hash': '0' * 64}
    draft = build_draft(request, 'complaint.cheat', 'ru', True, [citation])
    checked, reasons = check_draft(draft, rules, request, 'complaint.cheat', 'ru', True)
    assert 'safety_invalid_citation' in reasons
    assert not checked['cited'] and '5.2' not in checked['text']


def test_service_blocks_compromised_backend(monkeypatch):
    from app.core import TriageService
    request, rules = setup()
    monkeypatch.setattr('app.core.build_draft', lambda *args: {'lang': 'ru', 'text': 'Вернём деньги', 'cited': []})
    result = TriageService(rules).triage(request)
    assert result['needs_human']
    assert 'safety_unsafe_statement' in result['reasons']
    assert 'деньги' not in result['draft_reply']['text']
