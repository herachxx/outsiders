import gzip
import json

import pytest

from scripts.sample_for_labeling import digest
from scripts.weak_labels import load_weak_rows, weak_category


@pytest.mark.parametrize('violation,expected', [
    ('2.1 ОП', 'complaint.insult'), ('нарушение 5.2 ОП', 'complaint.cheat'), ('4.2', 'complaint.scam'),
    ('DM', 'complaint.dm'), ('ДБ', 'complaint.dm'), ('1.1 GZ', None), ('15.2 ОП', None), ('5.20', None),
    ('', None), (None, None), ('закрыто', None)])
def test_weak_category_maps_only_known_points(violation, expected):
    assert weak_category(violation) == expected


def reporter(holdout):
    for i in range(200):
        name = f'r{i}'
        if (int(digest(42, name)[:8], 16) % 4 == 0) == holdout:
            return name


def record(reporter_hash, text, violation, kind='complaint'):
    return {'kind': kind, 'reporter_hash': reporter_hash, 'violation': violation,
            'messages': [{'role': 'player', 'text': text}, {'role': 'admin', 'text': 'SECRETADMIN одобрена'}]}


def test_rows_skip_holdout_reporters_cap_classes_and_exclude_admin_text(tmp_path):
    path = tmp_path / 'train.jsonl.gz'
    train, held = reporter(False), reporter(True)
    records = [record(train, f'оск родни {i}', '2.1 ОП') for i in range(10)]
    records += [record(train, f'читы фаст {i}', '5.2') for i in range(3)]
    records += [record(held, 'оск родни holdout', '2.1 ОП'), record(train, '.', '2.1 ОП'),
                record(train, 'как дела', None), record(train, 'вопрос', '2.1', kind='report')]
    with gzip.open(path, 'wt', encoding='utf-8') as stream:
        stream.writelines(json.dumps(r, ensure_ascii=False) + '\n' for r in records)
    rows = load_weak_rows(path, cap=4)
    counts = {c: sum(r['category'] == c for r in rows) for c in {r['category'] for r in rows}}
    assert counts == {'complaint.insult': 4, 'complaint.cheat': 3}
    assert all('secretadmin' not in r['text'] and 'holdout' not in r['text'] for r in rows)
    assert all(r['review_status'] == 'weak' and r['reporter_hash'] == train for r in rows)
    assert rows == load_weak_rows(path, cap=4)   # deterministic
