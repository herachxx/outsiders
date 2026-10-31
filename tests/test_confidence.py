from app.confidence import lookup, table
from app.core import TriageService
from app.rules import RuleIndex


def ticket(text, kind='complaint', **extra):
    return {'kind': kind, 'messages': [{'role': 'player', 'text': text}], **extra}


def test_table_has_only_aggregates_in_unit_interval():
    assert table()
    for key, cell in table().items():
        assert key.count('|') == 1 and set(cell) == {'confidence', 'n'}
        assert 0 < cell['confidence'] < 1 and cell['n'] >= 1
    assert lookup('rule', 'complaint.nonexistent') == 0.0


def test_rule_decisions_get_empirical_confidence_and_fallback_other_is_low():
    service = TriageService(RuleIndex([]))
    insult = service.triage(ticket('оск родни'))
    other = service.triage(ticket('что-то странное'))
    assert insult['confidence'] == lookup('rule', 'complaint.insult') > 0.8
    assert other['confidence'] == lookup('heuristic', 'complaint.other') < 0.2


def test_confidence_can_be_disabled_and_is_zero_on_safety_override():
    assert TriageService(RuleIndex([]), empirical_confidence=False).triage(ticket('оск родни'))['confidence'] == 0.0

    class WrongModel:
        def predict(self, kind, text):
            return 'report.question'
    result = TriageService(RuleIndex([]), classifier=WrongModel()).triage(ticket('аккаунт украли', kind='report'))
    assert result['confidence'] == 0.0
