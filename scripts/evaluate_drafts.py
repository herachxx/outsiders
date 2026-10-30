"""Private blind draft review packages and aggregate human ratings."""
import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
import random
import statistics

from app.preprocess import before_admin
from app.schemas import TriageRequest, TriageResponse
from scripts.sample_for_labeling import private_path, read_records, digest

FIELDS = ['case_id', 'side', 'reviewer', 'language', 'native', 'score', 'hallucination', 'comment']


def build_package(records, service, size=100, seed=42):
    if size < 1:
        raise ValueError('Positive size required')
    rng = random.Random(seed)
    selected, seen = [], 0
    for row in records:
        historical = next((m['text'] for m in row.get('messages', []) if m['role'] == 'admin'), '')
        if not historical.strip():
            continue
        messages = list(before_admin(row['messages']))
        try:
            request = TriageRequest.model_validate({**{k: v for k, v in row.items() if k in TriageRequest.model_fields},
                                                    'messages': messages})
        except ValueError:
            continue
        if not row.get('ticket_id'):
            raise ValueError('Ticket identifier required')
        seen += 1
        item = (row, request, historical)
        if len(selected) < size:
            selected.append(item)
        else:
            position = rng.randrange(seen)
            if position < size:
                selected[position] = item
    if len(selected) < size:
        raise ValueError('Not enough eligible historical answers')
    tasks, key, ratings, identities = [], [], [], set()
    for row, request, historical in selected:
        identity = row['ticket_id']
        if identity in identities:
            raise ValueError('Duplicate selected ticket')
        identities.add(identity)
        result = TriageResponse.model_validate(service.triage(request)).model_dump()
        case = hashlib.sha256(f'{seed}:{identity}'.encode()).hexdigest()
        source = ['candidate', 'historical']
        rng.shuffle(source)
        answers = {
            'candidate': result['draft_reply']['text'], 'historical': historical}
        tasks.append({'case_id': case, 'context': request.model_dump(exclude={'reporter_hash', 'reported_hash'}),
                      'A': answers[source[0]], 'B': answers[source[1]]})
        key.append({'case_id': case, 'ticket_id': identity, 'A': source[0], 'B': source[1],
                    'language_hint': row.get('lang', 'und'), 'candidate': result})
        ratings.extend(dict.fromkeys(FIELDS, '') | {'case_id': case, 'side': side} for side in ('A', 'B'))
    return tasks, key, ratings


def summarize(key, ratings, seed=42):
    cases = {r['case_id']: r for r in key}
    if len(cases) != len(key):
        raise ValueError('Duplicate review case')
    groups, seen = defaultdict(list), set()
    for row in ratings:
        if not any(row.get(k) for k in ('reviewer', 'score', 'hallucination', 'language', 'native', 'comment')):
            continue
        case, side, reviewer = row.get('case_id'), row.get('side'), row.get('reviewer', '').strip()
        if case not in cases or side not in ('A', 'B') or not reviewer or (case, side, reviewer) in seen:
            raise ValueError('Invalid or duplicate rating identity')
        seen.add((case, side, reviewer))
        if str(row.get('score')) not in ('1', '2', '3', '4', '5') or row.get('hallucination') not in ('true', 'false'):
            raise ValueError('Score 1-5 and hallucination true/false required')
        lang = row.get('language')
        if lang not in ('ru', 'kk', 'uz', 'en', 'es', 'pt', 'lat', 'und'):
            raise ValueError('Reviewer-confirmed language required')
        if row.get('native') not in ('true', 'false') or (lang in ('kk', 'uz') and row['native'] != 'true'):
            raise ValueError('Kazakh and Uzbek require a native reviewer')
        groups[(case, reviewer)].append({**row, 'score': int(row['score'])})
    pairs = []
    case_languages = defaultdict(set)
    for (case, reviewer), rows in groups.items():
        if len(rows) != 2 or {r['side'] for r in rows} != {'A', 'B'} or len({r['language'] for r in rows}) != 1:
            raise ValueError('Each reviewer must score both sides with one confirmed language')
        pairs.append((case, rows))
        case_languages[case].add(rows[0]['language'])
    if any(len(languages) > 1 for languages in case_languages.values()):
        raise ValueError('Conflicting language labels require adjudication')

    def aggregate(selected):
        by_source, deltas, agreement = defaultdict(lambda: defaultdict(list)), defaultdict(list), defaultdict(list)
        flags = defaultdict(set)
        for case, rows in selected:
            values = {}
            for row in rows:
                source = cases[case][row['side']]
                by_source[source][case].append(row['score'])
                if row['hallucination'] == 'true': flags[source].add(case)
                values[source] = row['score']
                agreement[(case, source)].append(row['score'])
            deltas[case].append(values['candidate'] - values['historical'])
        result = {'cases': len(deltas), 'paired_reviewers': len(selected)}
        for source, by_case in by_source.items():
            values = [statistics.mean(v) for v in by_case.values()]
            result[source] = {'mean': statistics.mean(values), 'median': statistics.median(values),
                              'mean_with_flagged_cases_zeroed': statistics.mean(
                                  0 if case in flags[source] else statistics.mean(v) for case, v in by_case.items()),
                              'flagged_hallucination_cases': len(flags[source]),
                              'hallucination_case_rate': len(flags[source]) / len(by_case)}
        if deltas:
            values = [statistics.mean(v) for v in deltas.values()]
            rng = random.Random(seed)
            samples = sorted(statistics.mean(rng.choices(values, k=len(values))) for _ in range(2000))
            result['paired_mean_delta'] = statistics.mean(values)
            result['paired_delta_bootstrap_95'] = [samples[49], samples[1949]]
        differences = [abs(a - b) for values in agreement.values() for i, a in enumerate(values) for b in values[i+1:]]
        result['reviewer_mean_absolute_difference'] = statistics.mean(differences) if differences else None
        return result
    languages = sorted({rows[0]['language'] for _, rows in pairs})
    return {'overall': aggregate(pairs), 'languages': {
        lang: aggregate([(case, rows) for case, rows in pairs if rows[0]['language'] == lang]) for lang in languages},
        'unreviewed_cases': len(cases) - len({c for c, _ in pairs}),
        'note': 'Human flags require adjudication; small samples and sampling bias limit inference.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prepare = sub.add_parser('prepare')
    for name in ('input', 'rules', 'output'): prepare.add_argument('--' + name, required=True)
    prepare.add_argument('--size', type=int, default=100)
    prepare.add_argument('--seed', type=int, default=42)
    prepare.add_argument('--exclude-manifest', help='B1 manifest: exclude reserved reporter split')
    score = sub.add_parser('summarize')
    for name in ('key', 'ratings', 'output'): score.add_argument('--' + name, required=True)
    args = parser.parse_args()
    target = private_path(args.output)
    if target.exists(): parser.exit(2, 'Output exists; refusing overwrite.\n')
    if args.command == 'prepare':
        from app.core import TriageService
        from app.rules import RuleIndex
        rules = RuleIndex.from_file(args.rules)
        records = read_records(args.input)
        if args.exclude_manifest:
            manifest = json.loads(Path(args.exclude_manifest).read_text(encoding='utf-8'))
            reserved = {r['reporter_hash'] for r in manifest['items'] if r['split'] == 'holdout'}
            records = (r for r in records if r.get('reporter_hash') and r['reporter_hash'] not in reserved
                       and int(digest(manifest['seed'], r['reporter_hash'])[:8], 16) % 4 != 0)
        tasks, key, ratings = build_package(records, TriageService(rules), args.size, args.seed)
        target.mkdir(parents=True)
        for name, rows in [('tasks', tasks), ('private-key', key)]:
            (target / f'{name}.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')
        with (target / 'ratings.csv').open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS); writer.writeheader(); writer.writerows(ratings)
        root = Path(__file__).resolve().parents[1]
        hashes = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in sorted((root / 'app').rglob('*')) if p.suffix in ('.py', '.json')}
        (target / 'candidate.json').write_text(json.dumps({'backend': 'heuristic-template', 'seed': args.seed,
            'size': args.size, 'code_hashes': hashes, 'rules_hash': rules.rules[0].rules_hash if rules.rules else None}, indent=2), encoding='utf-8')
        print(json.dumps({'pairs': len(tasks)}))
    else:
        with open(args.ratings, encoding='utf-8-sig', newline='') as stream:
            result = summarize(list(read_records(args.key)), list(csv.DictReader(stream)))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'reviewed_cases': result['overall']['cases']}))


if __name__ == '__main__':
    main()
