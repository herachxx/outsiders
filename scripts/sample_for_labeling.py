"""Prepare private, blinded annotation tasks with a reporter-disjoint holdout."""
import argparse
from collections import Counter, defaultdict
import csv
import gzip
import hashlib
import json
from pathlib import Path
import re

from app.priority import POLICY_VERSION
from app.preprocess import before_admin

ROOT = Path(__file__).resolve().parents[1]
LABEL_FIELDS = ['annotation_id', 'annotator_id', 'category', 'priority', 'language',
                'needs_human', 'policy_version', 'adjudication_status']


def private_path(path):
    target = Path(path).resolve()
    if target == ROOT or ROOT in target.parents:
        raise ValueError('Private output must be outside the repository')
    return target


def digest(seed, value):
    return hashlib.sha256(f'{seed}:{value}'.encode('utf-8')).hexdigest()


def read_records(path):
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path, 'rt', encoding='utf-8') as stream:
        for number, line in enumerate(stream, 1):
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                raise ValueError(f'Invalid JSON at line {number}') from None


def build_sample(records, size=800, seed=42):
    if size < 4:
        raise ValueError('Sample size must be at least 4')
    pools = defaultdict(list)
    seen = set()
    for row in records:
        ticket_id, reporter = row.get('ticket_id'), row.get('reporter_hash')
        if not isinstance(ticket_id, str) or not ticket_id or not isinstance(reporter, str) or not reporter:
            raise ValueError('Record requires ticket_id and reporter_hash')
        if ticket_id in seen:
            raise ValueError('Duplicate ticket_id in source')
        seen.add(ticket_id)
        if row.get('kind') not in ('report', 'complaint'):
            raise ValueError('Unknown kind')
        messages = []
        for message in before_admin(row['messages']):
            if message['role'] in ('player', 'reported_player'):
                messages.append({'role': message['role'], 'text': message['text']})
        if not any(m['role'] == 'player' for m in messages):
            raise ValueError('Record has no player message before admin')
        text = ' '.join(m['text'] for m in messages if m['role'] == 'player')
        split = 'holdout' if int(digest(seed, reporter)[:8], 16) % 4 == 0 else 'train'
        # Signals are for sampling only; never prefill an annotation label.
        risk = bool(re.search(r'взлом|плат|донат|чит|угроз', text.casefold()))
        stratum = (row['kind'], row.get('lang') or 'und', risk,
                   'short' if len(text) < 25 else 'long', (row.get('created_at') or '')[:7])
        annotation_id = digest(seed, ticket_id)
        task = {'annotation_id': annotation_id, 'kind': row['kind'], 'messages': messages,
                'images_count': row.get('images_count', 0),
                'server_lang': row.get('server_lang'), 'region': row.get('region'),
                'rule_refs_raw': row.get('rule_refs_raw'), 'reported_nick': row.get('reported_nick')}
        item = {'annotation_id': annotation_id, 'ticket_id': ticket_id, 'reporter_hash': reporter,
                'kind': row['kind'], 'split': split, 'language_hint': row.get('lang') or 'und'}
        pools[(split, stratum)].append((annotation_id, task, item))
    selected = []
    for split, count in [('train', size - size // 4), ('holdout', size // 4)]:
        buckets = [sorted(values, key=lambda v: v[0]) for (s, key), values in sorted(pools.items()) if s == split]
        positions = [0] * len(buckets)
        chosen = []
        while len(chosen) < count:
            changed = False
            for i, bucket in enumerate(buckets):
                if positions[i] < len(bucket) and len(chosen) < count:
                    chosen.append(bucket[positions[i]])
                    positions[i] += 1
                    changed = True
            if not changed:
                raise ValueError('Not enough records in a group-disjoint split; reduce size')
        selected.extend(chosen)
    selected.sort(key=lambda v: v[0])
    return {'tasks': [x[1] for x in selected],
            'manifest': {'seed': seed, 'policy_version': POLICY_VERSION,
                         'sampling': 'round-robin kind/language/risk/length/month; not population representative',
                         'group_split': 'sha256(seed:reporter_hash) first 8 hex modulo 4 == 0 => holdout',
                         'items': [x[2] for x in selected]}}


def prepare_package(records, output, size=800, seed=42):
    target = private_path(output)
    if target.exists():
        raise ValueError('Output directory already exists; refusing overwrite')
    package = build_sample(records, size, seed)
    target.mkdir(parents=True)
    (target / 'manifest.json').write_text(json.dumps(package['manifest'], ensure_ascii=False, indent=2), encoding='utf-8')
    with (target / 'tasks.jsonl').open('w', encoding='utf-8') as stream:
        for task in package['tasks']:
            stream.write(json.dumps(task, ensure_ascii=False) + '\n')
    with (target / 'labels.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=LABEL_FIELDS)
        writer.writeheader()
        for task in package['tasks']:
            writer.writerow({'annotation_id': task['annotation_id'], 'policy_version': POLICY_VERSION})
    return {'tasks': len(package['tasks']), 'splits': dict(Counter(x['split'] for x in package['manifest']['items'])),
            'language_hints': dict(Counter(x['language_hint'] for x in package['manifest']['items']))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--size', type=int, default=800)
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()
    print(json.dumps(prepare_package(read_records(args.input), args.output, args.size, args.seed)))


if __name__ == '__main__':
    main()
