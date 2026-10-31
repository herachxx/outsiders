"""Stream private datasets and print aggregate diagnostics only."""
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path


def inspect_tickets(path):
    counts = {key: Counter() for key in ('kind', 'lang', 'roles')}
    seen = set()
    rows = invalid = duplicates = missing_player = 0
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path, 'rt', encoding='utf-8') as stream:
        for line in stream:
            rows += 1
            try:
                item = json.loads(line)
                if not isinstance(item, dict) or not isinstance(item.get('ticket_id'), str):
                    raise ValueError()
                if item.get('kind') not in ('report', 'complaint'):
                    raise ValueError()
                messages = item.get('messages')
                if not isinstance(messages, list) or not all(
                    isinstance(m, dict) and isinstance(m.get('text'), str)
                    and m.get('role') in ('player', 'reported_player', 'admin') for m in messages
                ):
                    raise ValueError()
                if not isinstance(item.get('lang', 'und'), str):
                    raise ValueError()
            except (ValueError, TypeError):
                invalid += 1
                continue
            duplicates += item['ticket_id'] in seen
            seen.add(item['ticket_id'])
            counts['kind'][item['kind']] += 1
            counts['lang'][item.get('lang', 'und')] += 1
            counts['roles'].update(m['role'] for m in messages)
            missing_player += not any(m['role'] == 'player' for m in messages)
    return {'rows': rows, 'invalid_rows': invalid, 'duplicate_ids': duplicates,
            'missing_player': missing_player, **{k: dict(v) for k, v in counts.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tickets', nargs='+', type=Path)
    parser.add_argument('--rules', type=Path)
    parser.add_argument('--taxonomy', type=Path)
    args = parser.parse_args()
    reports = [inspect_tickets(path) for path in args.tickets]
    output = {'tickets': reports}
    if args.rules:
        with args.rules.open(encoding='utf-8') as stream:
            rules = json.load(stream)['rules']
        keys = [(section['id'], point['ref']) for section in rules for point in section.get('points', [])]
        if len(keys) != len(set(keys)):
            raise ValueError('Duplicate composite rule key')
        output['rules'] = {'sections': len(rules), 'points': len(keys),
                           'unique_refs': len({ref for _, ref in keys})}
    if args.taxonomy:
        with args.taxonomy.open(encoding='utf-8') as stream:
            taxonomy = json.load(stream)
        categories = [item['code'] for item in taxonomy['categories']]
        priorities = [item['code'] for item in taxonomy['priorities']]
        if len(categories) != len(set(categories)) or set(priorities) != {'p0', 'p1', 'p2', 'p3'}:
            raise ValueError('Invalid taxonomy codes')
        output['taxonomy'] = {'categories': len(categories), 'priorities': len(priorities)}
    print(json.dumps(output, ensure_ascii=True, indent=2))
    raise SystemExit(int(any(r['invalid_rows'] or r['duplicate_ids'] or r['missing_player'] for r in reports)))


if __name__ == '__main__':
    main()
