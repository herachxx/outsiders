import copy
import pytest
from app.core import TriageService
from app.rules import RuleIndex
from scripts.evaluate_drafts import build_package, summarize


def package():
    rows = [dict(ticket_id=str(i), kind='report', lang='ru', messages=[
        {'role': 'player', 'text': 'Где магазин'}, {'role': 'admin', 'text': 'Исторический ответ'},
        {'role': 'player', 'text': 'ПОСЛЕ ОТВЕТА'}]) for i in range(8)]
    return build_package(rows, TriageService(RuleIndex([])), size=4)


def test_blinded_package_is_reproducible_and_hides_admin_context():
    tasks, key, ratings = package()
    assert (tasks, key, ratings) == package()
    assert len(tasks) == 4 and len(ratings) == 8
    assert 'candidate' not in tasks[0]
    for task in tasks:
        assert len(task['context']['messages']) == 1
        assert 'Исторический ответ' in (task['A'], task['B'])


def test_summary_uses_paired_reviews_and_flags_without_raw_text():
    tasks, key, ratings = package()
    for row in ratings:
        source = next(k for k in key if k['case_id'] == row['case_id'])[row['side']]
        row.update(reviewer='one', language='ru', native='true', score='5' if source == 'candidate' else '3',
                   hallucination='false', comment='PRIVATE NOTE')
    report = summarize(key, ratings)
    assert report['overall']['paired_mean_delta'] == 2
    assert report['overall']['paired_delta_bootstrap_95'] == [2, 2]
    assert report['unreviewed_cases'] == 0
    assert 'PRIVATE NOTE' not in str(report)
    assert summarize(key, [])['unreviewed_cases'] == 4
    ratings[0]['hallucination'] = 'true'
    assert summarize(key, ratings)['overall'][key[0][ratings[0]['side']]]['flagged_hallucination_cases'] == 1


def test_invalid_duplicate_incomplete_and_non_native_reviews_rejected():
    _, key, ratings = package()
    for row in ratings:
        row.update(reviewer='one', language='kk', native='true', score='4', hallucination='false')
    for changed in (ratings[:-1], ratings + [ratings[0]], [dict(r, native='false') for r in ratings],
                    [dict(r, score='6') for r in ratings]):
        with pytest.raises(ValueError): summarize(key, changed)
