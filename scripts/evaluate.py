"""Grouped development evaluation of category and priority; never reads holdout for scoring."""
import argparse
import json
from typing import get_args

from app.classifier import CategoryClassifier, make_pipeline
from app.core import TriageService
from app.rules import RuleIndex
from app.schemas import Category, TriageRequest
from scripts.sample_for_labeling import private_path, read_records
from scripts.train import prepare_rows


def evaluate(tasks, manifest, gold, seed=42):
    from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, recall_score
    from sklearn.model_selection import GroupKFold

    rows = prepare_rows(tasks, manifest, gold)
    groups = [r['reporter_hash'] for r in rows]
    if len(set(groups)) < 2:
        raise ValueError('Evaluation requires labeled train from at least two reporters')
    requests = {t['annotation_id']: TriageRequest.model_validate(
        {k: v for k, v in t.items() if k in TriageRequest.model_fields}) for t in tasks}
    scored, folds = [], []
    for train, valid in GroupKFold(min(5, len(set(groups))), shuffle=True,
                                  random_state=seed).split(rows, groups=groups):
        models = {}
        for kind in ('report', 'complaint'):
            selected = [rows[i] for i in train if rows[i]['kind'] == kind]
            if len({r['category'] for r in selected}) >= 2:
                models[kind] = make_pipeline(seed).fit([r['text'] for r in selected],
                                                       [r['category'] for r in selected])
        service = TriageService(RuleIndex([]), CategoryClassifier(models))
        baseline = TriageService(RuleIndex([]))
        folds.append({'train_rows': len(train), 'valid_rows': len(valid),
                      'trained_kinds': sorted(models), 'reporter_overlap': 0})
        for i in valid:
            row = rows[i]
            request = requests[row['annotation_id']]
            scored.append((row, service.triage(request), baseline.triage(request)))

    def metrics(subset, prediction_index):
        result = {'rows': len(subset)}
        for field, labels in [('category', list(get_args(Category))),
                               ('priority', ['p0', 'p1', 'p2', 'p3'])]:
            truth = [s[0][field] for s in subset]
            predicted = [s[prediction_index][field] for s in subset]
            result[field] = {'accuracy': float(accuracy_score(truth, predicted)),
                             'macro_f1': float(f1_score(truth, predicted, labels=labels,
                                                       average='macro', zero_division=0)),
                             'labels': labels,
                             'confusion_matrix': confusion_matrix(truth, predicted, labels=labels).tolist()}
            if field == 'priority':
                for priority in ('p0', 'p1'):
                    support = truth.count(priority)
                    result[field]['recall_' + priority] = float(recall_score(
                        truth, predicted, labels=[priority], average='macro', zero_division=0)) if support else None
                    result[field]['support_' + priority] = support
        result['sensitive_human_misses'] = sum(
            s[0]['category'] in ('report.account', 'report.payment', 'complaint.admin')
            and not s[prediction_index]['needs_human'] for s in subset)
        return result

    return {'scope': 'grouped CV within labeled train; service routing included',
            'seed': seed, 'holdout_evaluated': False, 'confidence_calibrated': False,
            'folds': folds, 'model_service': metrics(scored, 1), 'heuristic': metrics(scored, 2),
            'languages': {lang: metrics([s for s in scored if s[0]['language'] == lang], 1)
                          for lang in sorted({s[0]['language'] for s in scored})}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('tasks', 'manifest', 'gold', 'output'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()
    target = private_path(args.output)
    if target.exists():
        parser.exit(2, 'Output already exists.\n')
    try:
        with open(args.manifest, encoding='utf-8') as stream:
            manifest = json.load(stream)
        report = evaluate(list(read_records(args.tasks)), manifest, list(read_records(args.gold)), args.seed)
    except (ValueError, KeyError, TypeError):
        parser.exit(2, 'Evaluation requires valid B1 gold and at least two train reporter groups.\n')
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'rows': report['model_service']['rows'], 'holdout_evaluated': False}))


if __name__ == '__main__':
    main()
