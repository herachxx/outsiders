import csv
import json

import pytest

from scripts.label_cli import load_package
from scripts.sample_for_labeling import LABEL_FIELDS
from scripts.second_review import create_subset, select_ids


def make_package(folder):
    folder.mkdir()
    tasks, items = [], []
    for n in range(40):
        kind = 'complaint' if n % 2 else 'report'
        task = {'annotation_id': f'id-{n}', 'kind': kind,
                'messages': [{'role': 'player', 'text': 'донат вопрос' if n % 7 == 0 else 'вопрос'}]}
        tasks.append(task)
        items.append({'annotation_id': task['annotation_id'], 'kind': kind,
                      'split': 'holdout' if n % 4 == 0 else 'train',
                      'language_hint': 'kk' if n == 1 else 'uz' if n == 2 else 'ru',
                      'reporter_hash': f'reporter-{n}'})
    manifest = {'policy_version': 'draft', 'items': items}
    (folder / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    with (folder / 'tasks.jsonl').open('w', encoding='utf-8') as stream:
        for task in tasks:
            stream.write(json.dumps(task) + '\n')
    with (folder / 'labels.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=LABEL_FIELDS)
        writer.writeheader()
        for n, task in enumerate(tasks):
            writer.writerow({'annotation_id': task['annotation_id'], 'policy_version': 'draft',
                             'annotator_id': 'first' if n == 1 else '', 'category': 'SECRET' if n == 1 else ''})
    return manifest, tasks


def test_second_review_is_deterministic_blind_and_merge_compatible(tmp_path):
    source, target = tmp_path / 'source', tmp_path / 'review'
    manifest, tasks = make_package(source)
    assert select_ids(manifest, tasks) == select_ids(manifest, list(reversed(tasks)))
    summary = create_subset(source, target)
    assert summary['tasks'] == 8
    submanifest, subtasks, labels = load_package(target)
    assert len(subtasks) == 8
    assert all(not row['annotator_id'] and not row['category'] for row in labels)
    assert 'SECRET' not in (target / 'labels.csv').read_text(encoding='utf-8-sig')
    assert {'kk', 'uz'} <= {item['language_hint'] for item in submanifest['items']}
    assert {'train', 'holdout'} <= {item['split'] for item in submanifest['items']}
    with pytest.raises(ValueError, match='overwrite'):
        create_subset(source, target)


def test_second_review_refuses_small_subset_or_nested_output(tmp_path):
    source = tmp_path / 'source'
    manifest, tasks = make_package(source)
    with pytest.raises(ValueError, match='small'):
        select_ids(manifest, tasks, fraction=.01)
    with pytest.raises(ValueError, match='outside the source'):
        create_subset(source, source / 'nested')
