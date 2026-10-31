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


@pytest.mark.parametrize('lang', ['ru', 'kk', 'uz', 'en'])
def test_complaint_drafts_have_greeting_and_signature_but_reports_are_short(lang):
    from app.draft import templates
    phrases = templates()[lang]
    complaint = build_draft(request(), 'complaint.cheat', lang, False, [])['text']
    report = build_draft(request(), 'report.help', lang, False, [])['text']
    assert complaint.startswith(phrases['greeting_complaint']) and complaint.endswith(phrases['closing'])
    assert report.startswith(phrases['greeting_report']) and phrases['closing'] not in report
    assert phrases['evidence_missing'] in complaint


def test_missing_fields_and_evidence_change_draft():
    empty = build_draft(request(), 'complaint.cheat', 'ru', False, [])['text']
    supplied = build_draft(request(region='server', reported_nick='player'), 'complaint.cheat', 'ru', True, [])['text']
    assert 'Укажите сервер' in empty and 'Укажите никнейм' in empty
    assert 'Укажите сервер' not in supplied and 'Укажите никнейм' not in supplied
    assert 'ещё не проверено' in supplied


def test_unknown_language_uses_server_language_then_russian():
    assert build_draft(request(), 'report.offtopic', 'und', False, [])['lang'] == 'ru'
    assert build_draft(request(server_lang='uz'), 'report.offtopic', 'lat', False, [])['lang'] == 'uz'
    assert build_draft(request(server_lang='fr'), 'report.offtopic', 'und', False, [])['lang'] == 'ru'
    assert build_draft(request(server_lang='uz'), 'report.offtopic', 'en', False, [])['lang'] == 'en'


@pytest.mark.parametrize('lang', ['ru', 'kk', 'uz', 'en'])
@pytest.mark.parametrize('region', ['cis', 'uz', 'kz', ' CIS '])
def test_geographic_region_does_not_count_as_game_server(lang, region):
    from app.draft import templates
    result = build_draft(request(region=region), 'report.payment', lang, False, [])
    assert templates()[lang]['server_missing'] in result['text']


def test_explicit_server_still_avoids_duplicate_question():
    result = build_draft(request(region='Server 17'), 'report.help', 'ru', False, [])
    assert 'Укажите сервер' not in result['text']


@pytest.mark.parametrize('lang', ['ru', 'kk', 'uz', 'en'])
def test_each_complaint_type_has_its_own_question_and_review_note(lang):
    from app.draft import SPECIFIC_COMPLAINTS, templates
    phrases = templates()[lang]
    texts = {}
    for key in SPECIFIC_COMPLAINTS:
        category = f'complaint.{key}'
        texts[key] = build_draft(request(), category, lang, False, [])['text']
        assert phrases[key] in texts[key] and phrases['review'] in texts[key]
    assert len(set(texts.values())) == len(SPECIFIC_COMPLAINTS)
    other = build_draft(request(), 'complaint.other', lang, False, [])['text']
    assert phrases['complaint'] in other
    assert not any(phrases[key] in other for key in SPECIFIC_COMPLAINTS)
