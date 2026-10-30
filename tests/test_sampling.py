import json
import pytest

from scripts.sample_for_labeling import prepare_package, build_sample
from scripts.merge_labels import merge_annotations


def records():
    return [dict(ticket_id=f't{i}', reporter_hash=f'g{i // 2}', kind='report',
                 lang='kk' if i % 5 == 0 else 'ru', created_at='2026-10-01T12:00:00',
                 messages=[{'role': 'player', 'text': 'Где магазин?'},
                           {'role': 'admin', 'text': 'SECRET ANSWER'},
                           {'role': 'player', 'text': 'AFTER ANSWER'}], verdict='SECRET')
            for i in range(120)]


def test_sample_is_reproducible_group_disjoint_and_blind():
    a = build_sample(records(), size=24, seed=42)
    b = build_sample(reversed(records()), size=24, seed=42)
    assert a == b
    assert len(a['tasks']) == 24
    assert sum(x['split'] == 'holdout' for x in a['manifest']['items']) == 6
    groups = {split: {x['reporter_hash'] for x in a['manifest']['items'] if x['split'] == split}
              for split in ('train', 'holdout')}
    assert not groups['train'] & groups['holdout']
    assert 'SECRET' not in json.dumps(a)
    assert 'AFTER ANSWER' not in json.dumps(a)


def test_private_output_cannot_be_inside_repo():
    with pytest.raises(ValueError, match='outside'):
        prepare_package(records(), 'private-data', size=8, seed=42)


def label(item, annotator='one', category='report.question'):
    return dict(annotation_id=item['annotation_id'], annotator_id=annotator,
                category=category, priority='p3', language='ru', needs_human=False,
                policy_version='draft-2026-10-30', adjudication_status='labeled')


def test_conflict_is_not_silently_converted_to_gold():
    package = build_sample(records(), size=8, seed=42)
    item = package['manifest']['items'][0]
    result = merge_annotations(package['manifest'], [label(item), label(item, 'two', 'report.offtopic')])
    assert not result['gold']
    assert result['conflicts'][0]['annotation_id'] == item['annotation_id']


def test_labels_validate_kind_version_and_duplicate_annotator():
    package = build_sample(records(), size=8, seed=42)
    item = package['manifest']['items'][0]
    for bad in (label(item, category='complaint.insult'), {**label(item), 'policy_version': 'wrong'}):
        with pytest.raises(ValueError):
            merge_annotations(package['manifest'], [bad])
    with pytest.raises(ValueError):
        merge_annotations(package['manifest'], [label(item), label(item)])


def test_agreement_retains_split_and_no_outcome_fields():
    package = build_sample(records(), size=8, seed=42)
    item = package['manifest']['items'][0]
    result = merge_annotations(package['manifest'], [label(item), label(item, 'two')])
    assert result['gold'][0]['split'] == item['split']
    assert result['gold'][0]['review_status'] == 'agreed'


def test_empty_template_remains_unlabeled():
    package = build_sample(records(), size=8, seed=42)
    item = package['manifest']['items'][0]
    result = merge_annotations(package['manifest'], [{'annotation_id': item['annotation_id']}])
    assert result['unlabeled'] == 8
    assert result['gold'] == []


def test_private_package_can_be_written_once(tmp_path):
    target = tmp_path / 'private'
    summary = prepare_package(records(), target, size=8, seed=42)
    assert summary['tasks'] == 8
    assert len((target / 'tasks.jsonl').read_text(encoding='utf-8').splitlines()) == 8
    with pytest.raises(ValueError, match='overwrite'):
        prepare_package(records(), target, size=8, seed=42)
