"""Synthetic fixtures only: these scores do not measure contest quality."""
import copy
import json

import pytest

pytest.importorskip('sklearn')

from app.classifier import CategoryClassifier
from app.core import TriageService
from app.preprocess import player_text
from app.rules import RuleIndex
from scripts.train import train_classifier, save_training


def package():
    items, tasks, gold = [], [], []
    for n in range(26):
        category = 'report.question' if n % 2 == 0 else 'report.payment'
        item = dict(annotation_id=f'a{n}', ticket_id=f't{n}', reporter_hash=f'g{n // 2}',
                    kind='report', split='train' if n < 24 else 'holdout')
        text = 'где найти магазин' if n % 2 == 0 else 'оплатил донат деньги списаны'
        if n >= 24:
            text = 'holdoutsentinel'
        tasks.append(dict(annotation_id=item['annotation_id'], kind='report',
                          messages=[dict(role='player', text=text)]))
        items.append(item)
        gold.append(dict(**item, category=category, priority='p0' if n % 2 else 'p3',
                         language='ru', needs_human=True, policy_version='draft-2026-10-30',
                         review_status='single', annotators=['reviewer']))
    return tasks, dict(items=items, policy_version='draft-2026-10-30'), gold


def test_cutoff_excludes_outcomes_admin_and_later_player_messages():
    payload = dict(kind='report', verdict='secret', punishment='secret', violation='secret',
                   messages=[dict(role='player', text=' Где  магазин? '),
                             dict(role='reported_player', text='secret'),
                             dict(role='admin', text='secret'),
                             dict(role='player', text='secret')])
    assert player_text(payload['messages']) == 'Где  магазин?'
    service = TriageService(RuleIndex([]))
    base = dict(kind='report', messages=payload['messages'][:1])
    expected = service.triage(base)
    base['messages'] = payload['messages']
    base['messages'][-1]['attachments'] = 5
    assert service.triage(base) == expected


def test_training_reserves_holdout_and_is_reproducible():
    tasks, manifest, gold = package()
    model, report = train_classifier(tasks, manifest, gold, seed=42)
    other, same = train_classifier(list(reversed(tasks)), manifest, list(reversed(gold)), seed=42)
    assert report == same
    assert report['kinds']['report']['train_rows'] == 24
    assert report['kinds']['report']['validation']['status'] == 'complete'
    assert report['holdout_evaluated'] is False
    words = dict(model.models['report'].named_steps['features'].transformer_list)['word'].vocabulary_
    assert 'holdoutsentinel' not in words
    assert model.predict('report', 'где найти магазин') == 'report.question'
    assert model.predict('report', 'оплатил донат') == other.predict('report', 'оплатил донат')
    assert model.predict('complaint', 'читер') is None


@pytest.mark.parametrize('mutation', ['split', 'category', 'policy', 'duplicate', 'reporter', 'task_kind'])
def test_rejects_inconsistent_training_inputs(mutation):
    tasks, manifest, gold = package()
    if mutation == 'split': gold[0]['split'] = 'holdout'
    if mutation == 'category': gold[0]['category'] = 'complaint.cheat'
    if mutation == 'policy': gold[0]['policy_version'] = 'other'
    if mutation == 'duplicate': gold.append(copy.deepcopy(gold[0]))
    if mutation == 'reporter': manifest['items'][-1]['reporter_hash'] = 'g0'
    if mutation == 'task_kind': tasks[0]['kind'] = 'complaint'
    with pytest.raises(ValueError):
        train_classifier(tasks, manifest, gold)


def test_missing_labels_and_single_class_do_not_create_model():
    tasks, manifest, gold = package()
    for labels in ([], [g for g in gold if g['category'] == 'report.question']):
        with pytest.raises(ValueError, match='No trainable'):
            train_classifier(tasks, manifest, labels)


def test_artifact_roundtrip_and_api_batch_agree(tmp_path, monkeypatch):
    from app.api import create_app
    from app.batch import predict_lines
    from fastapi.testclient import TestClient
    tasks, manifest, gold = package()
    model, report = train_classifier(tasks, manifest, gold)
    output = tmp_path / 'model'
    save_training(model, report, output)
    loaded = CategoryClassifier.load(output / 'model.joblib')
    rules = {'rules': [{'id': 30, 'category': 'Общие', 'points': [{'ref': '2.1', 'text': 'Правило'}]}]}
    rules_path = tmp_path / 'rules.json'
    rules_path.write_text(json.dumps(rules), encoding='utf-8')
    monkeypatch.setenv('GRAND_RULES_PATH', str(rules_path))
    monkeypatch.setenv('GRAND_MODEL_PATH', str(output / 'model.joblib'))
    payload = dict(kind='report', messages=[dict(role='player', text='оплатил донат')])
    service = TriageService(RuleIndex.from_data(rules), classifier=loaded)
    batch = list(predict_lines([json.dumps(payload)], service))[0]
    http = TestClient(create_app()).post('/triage', json=payload)
    assert http.status_code == 200
    assert http.json() == batch
    assert batch['category'] == 'report.payment'
    assert batch['confidence'] == 0.0
    assert 'classifier_uncalibrated' in batch['reasons']
    with pytest.raises(ValueError, match='already exists'):
        save_training(model, report, output)
    with pytest.raises(ValueError, match='outside'):
        save_training(model, report, 'models/test')


def test_model_cannot_downgrade_sensitive_heuristic_route():
    class WrongModel:
        def predict(self, kind, text):
            return 'report.question'
    result = TriageService(RuleIndex([]), classifier=WrongModel()).triage(
        dict(kind='report', messages=[dict(role='player', text='аккаунт украли')]))
    assert result['needs_human'] is True
    assert result['priority'] == 'p0'


def test_training_ignores_outcomes_and_post_admin_text():
    tasks, manifest, gold = package()
    _, expected = train_classifier(tasks, manifest, gold)
    for task in tasks:
        task.update(verdict='secretsentinel', punishment='secretsentinel', violation='secretsentinel')
        task['messages'].extend([dict(role='admin', text='secretsentinel'),
                                 dict(role='player', text='secretsentinel')])
    model, actual = train_classifier(tasks, manifest, gold)
    assert actual == expected
    words = dict(model.models['report'].named_steps['features'].transformer_list)['word'].vocabulary_
    assert 'secretsentinel' not in words
    assert model.predict('report', '') is None
    assert model.predict('report', '漢字漢字') is None


def test_both_kinds_train_and_holdout_labels_do_not_change_model_report():
    tasks, manifest, gold = package()
    other_tasks, other_manifest, other_gold = copy.deepcopy((tasks, manifest, gold))
    for row in other_tasks + other_manifest['items'] + other_gold:
        row['annotation_id'] += 'c'
        row['kind'] = 'complaint'
        if 'ticket_id' in row: row['ticket_id'] += 'c'
        if 'category' in row:
            row['category'] = 'complaint.insult' if row['category'] == 'report.question' else 'complaint.cheat'
    tasks += other_tasks
    manifest['items'] += other_manifest['items']
    gold += other_gold
    model, report = train_classifier(tasks, manifest, gold)
    assert set(model.models) == {'complaint', 'report'}
    _, without = train_classifier(tasks, manifest, [r for r in gold if r['split'] == 'train'])
    assert report == without


def test_insufficient_groups_reports_no_validation_score():
    tasks, manifest, gold = package()
    for row in manifest['items'] + gold:
        if row['split'] == 'train': row['reporter_hash'] = 'one_train_group'
    _, report = train_classifier(tasks, manifest, gold)
    validation = report['kinds']['report']['validation']
    assert validation['status'] == 'skipped'
    assert 'model' not in validation


def test_rejects_incompatible_local_artifact(tmp_path):
    import joblib
    model, report = train_classifier(*package())
    output = tmp_path / 'artifact'
    save_training(model, report, output)
    path = output / 'model.joblib'
    artifact = joblib.load(path)
    artifact['preprocess_version'] = 'old'
    joblib.dump(artifact, path)
    with pytest.raises(ValueError, match='Incompatible'):
        CategoryClassifier.load(path)


def test_training_and_batch_cli(tmp_path):
    import subprocess
    import sys
    tasks, manifest, gold = package()
    for name, rows in (('tasks', tasks), ('gold', gold)):
        (tmp_path / f'{name}.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows), encoding='utf-8')
    (tmp_path / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    args = [sys.executable, '-m', 'scripts.train', '--tasks', str(tmp_path / 'tasks.jsonl'),
            '--manifest', str(tmp_path / 'manifest.json'), '--gold', str(tmp_path / 'gold.jsonl'),
            '--output', str(tmp_path / 'trained')]
    trained = subprocess.run(args, capture_output=True, text=True)
    assert trained.returncode == 0, trained.stderr
    assert json.loads(trained.stdout)['trained_kinds'] == ['report']
    (tmp_path / 'rules.json').write_text(json.dumps({'rules': []}), encoding='utf-8')
    payload = dict(kind='report', messages=[dict(role='player', text='где найти магазин')])
    (tmp_path / 'input.jsonl').write_text(json.dumps(payload) + '\nnot json\n', encoding='utf-8')
    result = subprocess.run([sys.executable, '-m', 'app.batch', '--input', str(tmp_path / 'input.jsonl'),
                             '--output', str(tmp_path / 'output.jsonl'), '--rules', str(tmp_path / 'rules.json'),
                             '--model', str(tmp_path / 'trained' / 'model.joblib')], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    output = [json.loads(line) for line in (tmp_path / 'output.jsonl').read_text().splitlines()]
    assert output[0]['category'] == 'report.question'
    assert output[1] == {'error': 'invalid_input'}
    (tmp_path / 'gold.jsonl').write_text('', encoding='utf-8')
    args[-1] = str(tmp_path / 'empty-model')
    empty = subprocess.run(args, capture_output=True, text=True)
    assert empty.returncode == 2
    assert 'No gold labels' in empty.stderr
    assert not (tmp_path / 'empty-model').exists()
