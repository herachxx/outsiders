import pytest
from app.core import TriageService
from app.priority import route
from app.rules import RuleIndex


@pytest.mark.parametrize('text,category', [
    ('Аккаунтым бұзылды', 'report.account'),
    ('Аккаунтыма кіре алмаймын', 'report.account'),
    ('Akkauntimga kira olmayapman', 'report.account'),
    ('Төлем жасадым, ақша түспеді', 'report.payment'),
    ('Pul yechildi, donat kelmadi', 'report.payment'),
    ('To‘lov qildim, donat kelmadi', 'report.payment'),
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
