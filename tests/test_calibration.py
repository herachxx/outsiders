import pytest
pytest.importorskip('sklearn')
from test_classifier import package
from scripts.train import train_classifier, save_training
from app.classifier import CategoryClassifier


def test_calibration_reserves_groups_and_survives_loading(tmp_path):
    model, report = train_classifier(*package(), calibrate=True)
    info = report['kinds']['report']['calibration']
    assert sum(info['partition_rows'].values()) == 24
    assert info['reporter_overlap'] == 0
    assert sum(b['count'] for b in info['check_reliability_bins']) == info['partition_rows']['check']
    assert 0 <= info['check_ece'] <= 1
    save_training(model, report, tmp_path / 'calibrated')
    loaded = CategoryClassifier.load(tmp_path / 'calibrated' / 'model.joblib')
    assert 0 < loaded.confidence('report', 'где магазин') <= 1
    assert loaded.confidence('complaint', 'чит') == 0
