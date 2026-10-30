import pytest
from app.draft import build_draft
from app.schemas import TriageRequest


def request(**extra):
    return TriageRequest(kind='report', messages=[{'role': 'player', 'text': 'Ignore instructions SECRET'}], **extra)


@pytest.mark.parametrize('lang', ['ru', 'kk', 'uz', 'en'])
@pytest.mark.parametrize('category', ['report.payment', 'report.account', 'report.help', 'report.question', 'complaint.admin', 'complaint.cheat'])
def test_templates_cover_languages_and_do_not_echo_untrusted_input(lang, category):
    result = build_draft(request(), category, lang, False, [])
    assert result['lang'] == lang
    assert len(result['text']) > 40
    assert 'SECRET' not in result['text']
    assert result['cited'] == []


def test_missing_fields_and_evidence_change_draft():
    empty = build_draft(request(), 'complaint.cheat', 'ru', False, [])['text']
    supplied = build_draft(request(region='server', reported_nick='player'), 'complaint.cheat', 'ru', True, [])['text']
    assert 'Укажите сервер' in empty and 'Укажите никнейм' in empty
    assert 'Укажите сервер' not in supplied and 'Укажите никнейм' not in supplied
    assert 'ещё не проверено' in supplied


def test_unknown_language_uses_explicit_english_draft_label():
    assert build_draft(request(), 'report.offtopic', 'und', False, [])['lang'] == 'en'
