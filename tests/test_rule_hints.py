import pytest
from app.core import TriageService
from app.rules import RuleIndex


@pytest.mark.parametrize('ref', ['15.2', '5.20', '5.2.1', '4.10', '14.1', '12.3', '5.30'])
def test_other_rule_numbers_do_not_match_shorter_hint(ref):
    result = TriageService(RuleIndex([])).triage({'kind': 'complaint',
        'messages': [{'role': 'player', 'text': 'Проверьте запись'}], 'rule_refs_raw': ref})
    assert result['category'] == 'complaint.other'
    assert result['draft_reply']['cited'] == []


@pytest.mark.parametrize('kind,text,expected', [
    ('report', 'Мой аккаунт взломали', 'report.account'),
    ('report', 'Оплатил, деньги списаны', 'report.payment'),
    ('complaint', 'Админ оскорбил меня', 'complaint.admin'),
])
def test_hints_and_wrong_model_cannot_remove_sensitive_route(kind, text, expected):
    class WrongModel:
        def predict(self, kind, text):
            return 'complaint.insult' if kind == 'complaint' else 'report.question'
    result = TriageService(RuleIndex([]), WrongModel()).triage({'kind': kind,
        'messages': [{'role': 'player', 'text': text}], 'rule_refs_raw': '5.2'})
    assert result['category'] == expected
    assert result['needs_human']
    if kind == 'report':
        assert result['priority'] == 'p0'


@pytest.mark.parametrize('ref,expected', [('5.2 оп', 'complaint.cheat'), ('5.3', 'complaint.dm'),
    ('4.1', 'complaint.scam'), ('2.3', 'complaint.rmt_ads'), ('2.1оп', 'complaint.insult')])
def test_exact_hints_and_legacy_suffix_keep_working(ref, expected):
    assert TriageService._category('complaint', 'Проверьте запись', ref) == expected
