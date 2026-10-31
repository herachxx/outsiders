"""Fit the empirical confidence table (aggregates only) from labeled train rows; holdout is never read."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

from app.core import TriageService
from app.schemas import TriageRequest
from scripts.sample_for_labeling import read_records
from scripts.train import make_pipeline, prepare_rows

PRIOR = 2  # Laplace smoothing: (hits + 1) / (n + 2)


def fit(tasks, manifest, gold, seed=42):
    from sklearn.model_selection import GroupKFold

    rows = prepare_rows(tasks, manifest, gold)
    refs = {t['annotation_id']: t.get('rule_refs_raw') or '' for t in tasks}
    counts = defaultdict(lambda: [0, 0])
    # Rules and heuristics: no fitting, so every labeled train row is a fair sample.
    for row in rows:
        kind = row['kind']
        guess = TriageService._category(kind, row['text'], refs[row['annotation_id']])
        source = 'rule' if kind == 'complaint' and guess != 'complaint.other' else 'heuristic'
        counts[(source, guess)][0] += guess == row['category']
        counts[(source, guess)][1] += 1
    # Model: out-of-fold predictions grouped by reporter, only where no rule decides.
    groups = [r['reporter_hash'] for r in rows]
    for kind in ('complaint', 'report'):
        idx = [i for i, r in enumerate(rows) if r['kind'] == kind]
        if len({rows[i]['category'] for i in idx}) < 2 or len({groups[i] for i in idx}) < 2:
            continue
        sub_groups = [groups[i] for i in idx]
        for train, valid in GroupKFold(min(5, len(set(sub_groups))), shuffle=True, random_state=seed).split(idx, groups=sub_groups):
            fit_rows = [rows[idx[i]] for i in train]
            if len({r['category'] for r in fit_rows}) < 2:
                continue
            model = make_pipeline(seed).fit([r['text'] for r in fit_rows], [r['category'] for r in fit_rows])
            for i in valid:
                row = rows[idx[i]]
                if kind == 'complaint' and TriageService._category(kind, row['text'], refs[row['annotation_id']]) != 'complaint.other':
                    continue
                guess = str(model.predict([row['text']])[0])
                counts[('model', guess)][0] += guess == row['category']
                counts[('model', guess)][1] += 1
    table = {f'{s}|{c}': {'confidence': round((h + 1) / (n + PRIOR), 3), 'n': n} for (s, c), (h, n) in sorted(counts.items())}
    return {'version': 1, 'smoothing': 'laplace', 'rows': len(rows), 'table': table}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('tasks', 'manifest', 'gold', 'output'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()
    tasks = list(read_records(args.tasks))
    manifest = json.loads(Path(args.manifest).read_text(encoding='utf-8'))
    gold = list(read_records(args.gold))
    result = fit(tasks, manifest, gold, args.seed)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'rows': result['rows'], 'cells': len(result['table'])}))


if __name__ == '__main__':
    main()
