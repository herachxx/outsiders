import pytest
pytest.importorskip('sklearn')
from test_classifier import package
from scripts.evaluate import evaluate


def test_calibrated_evaluation_scores_external_groups_and_languages():
    tasks, manifest, gold = package()
    report = evaluate(tasks, manifest, gold, calibrate=True)
    assert report['holdout_evaluated'] is False
    assert report['model_service']['rows'] == 24
    calibration = report['model_service']['calibration']
    assert calibration['scored_rows'] == 24
    assert sum(b['count'] for b in calibration['bins']) == 24
    assert 0 <= calibration['ece'] <= 1
    assert report['languages']['ru']['calibration'] == calibration
    assert report['uncalibrated_service']['calibration']['ece'] is None
    without_holdout = evaluate(tasks, manifest, [r for r in gold if r['split'] == 'train'], calibrate=True)
    assert without_holdout == report
