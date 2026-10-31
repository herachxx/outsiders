"""Create a blinded, deterministic subset for independent B1 review."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re

from scripts.label_cli import load_package
from scripts.sample_for_labeling import LABEL_FIELDS, private_path


RISK_PATTERN = re.compile(r'взлом|плат|донат|чит|угроз', re.IGNORECASE)


def select_ids(manifest, tasks, fraction=.2, seed=42):
    if not 0 < fraction <= 1:
        raise ValueError('Fraction must be in (0, 1]')
    items = {item['annotation_id']: item for item in manifest['items']}
    count = max(1, round(len(tasks) * fraction))
    def key(task):
        return hashlib.sha256(f"{seed}:{task['annotation_id']}".encode()).hexdigest()
    ordered = sorted(tasks, key=key)
    selected = []
    def add_first(predicate):
        for task in ordered:
            if task['annotation_id'] not in selected and predicate(task):
                selected.append(task['annotation_id'])
                break
    # Cover rare languages, both held-out/train groups, both kinds, and a risk signal.
    for lang in ('kk', 'uz'):
        add_first(lambda task, lang=lang: items[task['annotation_id']]['language_hint'] == lang)
    for split in ('train', 'holdout'):
        add_first(lambda task, split=split: items[task['annotation_id']]['split'] == split)
    for kind in ('complaint', 'report'):
        add_first(lambda task, kind=kind: task['kind'] == kind)
    add_first(lambda task: any(RISK_PATTERN.search(message['text']) for message in task['messages'] if message['role'] == 'player'))
    if len(selected) > count:
        raise ValueError('Subset too small to cover required strata')
    selected.extend(task['annotation_id'] for task in ordered if task['annotation_id'] not in selected)  # deterministic fill
    return set(selected[:count])


def create_subset(source, output, fraction=.2, seed=42):
    source, target = Path(source).resolve(), private_path(output)
    if source == target or source in target.parents:
        raise ValueError('Output must be outside the source package')
    if target.exists():
        raise ValueError('Output directory already exists; refusing overwrite')
    manifest, tasks, _ = load_package(source)
    ids = select_ids(manifest, tasks, fraction, seed)
    chosen = [task for task in tasks if task['annotation_id'] in ids]
    submanifest = {**manifest, 'items': [item for item in manifest['items'] if item['annotation_id'] in ids],
                   'review_subset': {'seed': seed, 'fraction': fraction, 'source_task_count': len(tasks)}}
    target.mkdir(parents=True)
    (target / 'manifest.json').write_text(json.dumps(submanifest, ensure_ascii=False, indent=2), encoding='utf-8')
    with (target / 'tasks.jsonl').open('w', encoding='utf-8') as stream:
        for task in chosen:
            stream.write(json.dumps(task, ensure_ascii=False) + '\n')
    with (target / 'labels.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=LABEL_FIELDS)
        writer.writeheader()
        writer.writerows({'annotation_id': task['annotation_id'], 'policy_version': manifest['policy_version']}
                         for task in chosen)
    return {'tasks': len(chosen), 'splits': dict(Counter(item['split'] for item in submanifest['items'])),
            'language_hints': dict(Counter(item['language_hint'] for item in submanifest['items']))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--fraction', type=float, default=.2)
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()
    print(json.dumps(create_subset(args.package, args.output, args.fraction, args.seed)))


if __name__ == '__main__':
    main()
