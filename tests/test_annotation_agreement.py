import pytest
from scripts.merge_labels import agreement_report


def row(annotator, category, status='labeled'):
    return {'annotator_id': annotator, 'category': category, 'priority': 'p2',
            'language': 'ru', 'needs_human': True, 'status': status}


def test_agreement_reports_chance_adjustment_and_undefined_constant():
    groups = {'one': [row('a', 'x'), row('b', 'x')],
              'two': [row('a', 'y'), row('b', 'x')],
              'three': [row('a', 'y'), row('b', 'y')],
              'four': [row('a', 'x'), row('b', 'y')]}
    report = agreement_report(groups)
    pair = report['pairs'][0]
    assert pair['shared_complete'] == 4
    assert pair['fields']['category']['agreement'] == .5
    assert pair['fields']['category']['cohen_kappa'] == pytest.approx(0)
    assert pair['fields']['priority']['agreement'] == 1
    assert pair['fields']['priority']['cohen_kappa'] is None


def test_agreement_excludes_single_and_adjudication_and_handles_three_raters():
    report = agreement_report({'one': [row('a', 'x')],
                               'two': [row('a', 'x'), row('b', 'x', 'needs_adjudication')],
                               'three': [row('a', 'x'), row('b', 'y'), row('c', 'x')]})
    assert report['tasks_with_multiple_complete'] == 1
    assert len(report['pairs']) == 3
    assert all(pair['shared_complete'] == 1 for pair in report['pairs'])
    assert agreement_report({})['pairs'] == []
