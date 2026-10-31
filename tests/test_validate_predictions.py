from scripts.validate_predictions import validate

REFS = {'2.1', '5.2'}
CATEGORIES = {'complaint.insult', 'report.payment', 'report.question'}
PRIORITIES = {'p0', 'p1', 'p2', 'p3'}


def row(**changes):
    base = {'lang': 'ru', 'category': 'complaint.insult', 'priority': 'p2', 'is_spam_or_duplicate': False,
            'extracted': {'nickname': None, 'rule_refs': [], 'has_evidence': True, 'server': None},
            'draft_reply': {'lang': 'ru', 'text': 'Здравствуйте!', 'cited': ['2.1']},
            'needs_human': True, 'confidence': 0.8, 'reasons': ['решение о наказании подтверждает администратор']}
    base.update(changes)
    return base


def check(source, prediction):
    return dict(validate([source], [prediction], REFS, CATEGORIES, PRIORITIES))


def test_good_row_passes_and_each_defect_is_named():
    complaint = {'kind': 'complaint'}
    assert check(complaint, row()) == {}
    assert check(complaint, row(draft_reply={'lang': 'ru', 'text': 'x', 'cited': ['99.9']})) == {'hallucinated_citation': 1}
    assert check(complaint, row(extracted={'nickname': None, 'rule_refs': [], 'has_evidence': True})) == {'extracted_keys': 1}
    assert check(complaint, row(category='report.payment', priority='p1', needs_human=False))['sensitive_not_p0'] == 1
    assert check(complaint, row(needs_human=True, reasons=[])) == {'human_without_reason': 1}
    assert check({'kind': 'report'}, row()) == {'category_kind_mismatch': 1}
    assert check(complaint, row(draft_reply={'lang': 'ru', 'text': 'Мы разбаним вас', 'cited': []})) == {'promise_in_draft': 1}
    assert check(complaint, {'error': 'invalid_input'}) == {'error_row': 1}
    assert dict(validate([complaint, complaint], [row()], REFS, CATEGORIES, PRIORITIES)) == {'row_count_mismatch': 1}
