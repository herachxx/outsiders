import csv
import json

import pytest

from scripts.label_cli import annotate, load_package, run
from scripts.sample_for_labeling import LABEL_FIELDS


def package(tmp_path):
    folder = tmp_path / 'annotation'
    folder.mkdir()
    task = {'annotation_id': 'a', 'kind': 'report', 'messages': [{'role': 'player', 'text': 'private question'}]}
    manifest = {'policy_version': 'draft', 'items': [{'annotation_id': 'a', 'kind': 'report', 'reporter_hash': 'r', 'split': 'train'}]}
    (folder / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    (folder / 'tasks.jsonl').write_text(json.dumps(task) + '\n', encoding='utf-8')
    with (folder / 'labels.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=LABEL_FIELDS)
        writer.writeheader()
        writer.writerow({'annotation_id': 'a', 'policy_version': 'draft'})
    return folder


def test_label_cli_saves_valid_label_and_resumes(tmp_path):
    folder = package(tmp_path)
    # labeled, report.question, p3, ru, false
    answers = iter(['1', '1', '4', '1', '2'])
    run(folder, 'reviewer_1', lambda _: next(answers))
    _, _, rows = load_package(folder)
    assert rows[0]['category'] == 'report.question'
    assert rows[0]['priority'] == 'p3'
    assert rows[0]['annotator_id'] == 'reviewer_1'
    run(folder, 'reviewer_1', lambda _: pytest.fail('Should not ask again'))


def test_label_cli_rejects_sensitive_without_human(tmp_path):
    folder = package(tmp_path)
    manifest, tasks, rows = load_package(folder)
    answers = iter(['1', '4', '1', '1', '2'])  # report.account, p0, ru, false
    with pytest.raises(ValueError, match='Sensitive'):
        annotate(tasks[0], rows[0], manifest, 'reviewer_1', lambda _: next(answers))
    assert not load_package(folder)[2][0]['annotator_id']


def test_label_cli_can_mark_adjudication(tmp_path):
    folder = package(tmp_path)
    run(folder, 'reviewer_1', lambda _: '2')
    assert load_package(folder)[2][0]['adjudication_status'] == 'needs_adjudication'
