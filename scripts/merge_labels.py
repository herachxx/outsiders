"""Validate annotations and separate disagreements from labeled data."""
import argparse
from collections import Counter, defaultdict
from itertools import combinations
import csv
import json
from typing import get_args

from app.schemas import Category, Language
from scripts.sample_for_labeling import private_path


def agreement_report(groups):
    """Pairwise unweighted Cohen kappa on complete shared annotations only."""
    pairs = defaultdict(list)
    for rows in groups.values():
        complete = sorted((row for row in rows if row['status'] == 'labeled'), key=lambda row: row['annotator_id'])
        for left, right in combinations(complete, 2):
            pairs[(left['annotator_id'], right['annotator_id'])].append((left, right))
    result = []
    for annotators, shared in sorted(pairs.items()):
        fields = {}
        for field in ('category', 'priority', 'language', 'needs_human'):
            left = Counter(a[field] for a, _ in shared)
            right = Counter(b[field] for _, b in shared)
            matches = sum(a[field] == b[field] for a, b in shared)
            observed = matches / len(shared)
            expected = sum(count * right[value] for value, count in left.items()) / len(shared) ** 2
            fields[field] = {'matches': matches, 'agreement': observed,
                             'cohen_kappa': (observed - expected) / (1 - expected) if expected < 1 else None}
        result.append({'annotators': list(annotators), 'shared_complete': len(shared), 'fields': fields})
    return {'pairs': result, 'tasks_with_multiple_complete': sum(sum(row['status'] == 'labeled' for row in rows) >= 2 for rows in groups.values()),
            'note': 'Only complete shared labels; adjudication excluded. Kappa is unweighted; null when undefined. No overlap means no estimate.'}


def merge_annotations(manifest, annotations):
    items = {item['annotation_id']: item for item in manifest['items']}
    if len(items) != len(manifest['items']):
        raise ValueError('Duplicate manifest task')
    reporter_splits = defaultdict(set)
    for item in items.values():
        if item['split'] not in ('train', 'holdout'):
            raise ValueError('Invalid manifest split')
        reporter_splits[item['reporter_hash']].add(item['split'])
    if any(len(splits) > 1 for splits in reporter_splits.values()):
        raise ValueError('Reporter leakage between splits')
    groups = defaultdict(list)
    seen = set()
    for row in annotations:
        key = row.get('annotation_id')
        annotator = row.get('annotator_id', '').strip()
        if key in items and not any(row.get(f) for f in ('annotator_id', 'category', 'priority', 'language', 'needs_human', 'adjudication_status')):
            continue
        if key not in items or not annotator:
            raise ValueError('Unknown task or missing annotator')
        if (key, annotator) in seen:
            raise ValueError('Duplicate task/annotator pair')
        seen.add((key, annotator))
        if row.get('policy_version') != manifest['policy_version']:
            raise ValueError('Policy version mismatch')
        status = row.get('adjudication_status')
        if status not in ('labeled', 'needs_adjudication'):
            raise ValueError('Annotation is incomplete or status is invalid')
        if status == 'needs_adjudication':
            groups[key].append({'annotator_id': annotator, 'status': status})
            continue
        if row.get('category') not in get_args(Category) or not row['category'].startswith(items[key]['kind'] + '.'):
            raise ValueError('Category is invalid for ticket kind')
        if row.get('priority') not in ('p0', 'p1', 'p2', 'p3') or row.get('language') not in get_args(Language):
            raise ValueError('Invalid priority or language')
        human = row.get('needs_human')
        if isinstance(human, str) and human.lower() in ('true', 'false'):
            human = human.lower() == 'true'
        if not isinstance(human, bool):
            raise ValueError('needs_human must be true or false')
        if row['category'] in ('report.account', 'report.payment', 'complaint.admin') and not human:
            raise ValueError('Sensitive category requires human review')
        groups[key].append({'annotator_id': annotator, 'status': status,
                            'category': row['category'], 'priority': row['priority'],
                            'language': row['language'], 'needs_human': human})
    gold, conflicts = [], []
    fields = ('category', 'priority', 'language', 'needs_human')
    for key, rows in sorted(groups.items()):
        signatures = {tuple(row.get(f) for f in fields) for row in rows}
        if any(row['status'] == 'needs_adjudication' for row in rows) or len(signatures) != 1:
            conflicts.append({'annotation_id': key, 'annotations': rows})
        else:
            gold.append({**items[key], **{f: rows[0][f] for f in fields},
                         'policy_version': manifest['policy_version'],
                         'review_status': 'agreed' if len(rows) > 1 else 'single',
                         'annotators': [row['annotator_id'] for row in rows]})
    return {'gold': gold, 'conflicts': conflicts, 'unlabeled': len(items) - len(groups),
            'agreement': agreement_report(groups)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--labels', nargs='+', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    target = private_path(args.output)
    if target.exists():
        raise ValueError('Output directory already exists; refusing overwrite')
    with open(args.manifest, encoding='utf-8') as stream:
        manifest = json.load(stream)
    labels = []
    for path in args.labels:
        with open(path, encoding='utf-8-sig', newline='') as stream:
            labels.extend(csv.DictReader(stream))
    result = merge_annotations(manifest, labels)
    target.mkdir(parents=True)
    for name in ('gold', 'conflicts'):
        with (target / f'{name}.jsonl').open('w', encoding='utf-8') as stream:
            for row in result[name]:
                stream.write(json.dumps(row, ensure_ascii=False) + '\n')
    with (target / 'agreement.json').open('w', encoding='utf-8') as stream:
        json.dump(result['agreement'], stream, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps({'labeled': len(result['gold']), 'conflicts': len(result['conflicts']), 'unlabeled': result['unlabeled']}))


if __name__ == '__main__':
    main()
