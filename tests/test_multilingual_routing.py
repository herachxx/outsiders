import pytest
from app.core import TriageService
from app.priority import route, multilingual_sensitive_category
from app.rules import RuleIndex


@pytest.mark.parametrize('text,category', [
    ('Аккаунтым бұзылды', 'report.account'),
    ('Аккаунтыма кіре алмаймын', 'report.account'),
    ('Akkauntimga kira olmayapman', 'report.account'),
    ('Төлем жасадым, ақша түспеді', 'report.payment'),
    ('Pul yechildi, donat kelmadi', 'report.payment'),
    ('To‘lov qildim, donat kelmadi', 'report.payment'),
    ('Akkauntimga кіре алмаймын', 'report.account'),
    ('Донат kelmadi', 'report.payment'),
])
def test_sensitive_kk_uz_signals_override_low_category_and_model(text, category):
    class WrongClassifier:
        def predict(self, kind, text):
            return 'report.question'
    service = TriageService(RuleIndex([]), WrongClassifier())
    result = service.triage({'kind': 'report', 'messages': [{'role': 'player', 'text': text}]})
    assert result['category'] == category
    assert result['priority'] == 'p0'
    assert result['needs_human']
    assert route('report.question', text).priority == 'p0'


@pytest.mark.parametrize('text', ['Аккаунт қалай ашылады?', 'Akkaunt qanday ochiladi?', 'Дүкен қайда?', 'Do‘kon qayerda?'])
def test_general_questions_do_not_trigger_critical_routing(text):
    assert route('report.question', text).priority == 'p3'


@pytest.mark.parametrize('text,category', [
    ('Akkauntimga кіре алмаймын', 'report.account'),
    ('Аккаунтыма kira olmayapman', 'report.account'),
    ('Akkauntim buzib kirildi', 'report.account'),
    ('Донат kelmadi', 'report.payment'),
])
def test_mixed_scripts_keep_sensitive_signals(text, category):
    assert multilingual_sensitive_category(text) == category
    assert route('report.question', text).priority == 'p0'


@pytest.mark.parametrize('text', [
    'Akkauntim buzib kirilmagan',
    'Akkauntim buzib kirilgan emas',
    'Аккаунтым бұзылған жоқ',
    'Аккаунтым бұзылмаған',
])
def test_explicit_negation_does_not_create_new_hack_signal(text):
    assert multilingual_sensitive_category(text) is None


def test_negation_does_not_hide_separate_active_problem_or_sensitive_category():
    text = 'Akkauntim buzib kirilmagan. Akkauntimga kira olmayapman'
    assert multilingual_sensitive_category(text) == 'report.account'
    # The category itself still requires critical review under the existing policy.
    assert route('report.account', 'Аккаунтым бұзылған жоқ').priority == 'p0'
