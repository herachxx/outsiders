"""Train category models from B1 gold; holdout is never fitted or scored."""
import argparse
from collections import Counter
import hashlib
import json
import platform
from typing import get_args

from app.classifier import ARTIFACT_VERSION, CategoryClassifier, make_pipeline
from app.core import TriageService
from app.preprocess import PREPROCESS_VERSION, normalize, player_text
from app.priority import POLICY_VERSION
from app.schemas import Category, TriageRequest
from scripts.merge_labels import merge_annotations
from scripts.sample_for_labeling import private_path, read_records


def prepare_rows(tasks, manifest, gold):
    if manifest.get('policy_version') != POLICY_VERSION:
        raise ValueError('Unsupported policy version')
    # Validate every reserved reporter, including unlabeled holdout rows.
    merge_annotations(manifest, [])
    items = {i['annotation_id']: i for i in manifest['items']}
    tickets = set()
    for item in items.values():
        if any(not isinstance(item.get(k), str) or not item[k].strip()
               for k in ('annotation_id', 'ticket_id', 'reporter_hash')):
            raise ValueError('Manifest requires nonempty identifiers')
        if item['ticket_id'] in tickets or item.get('kind') not in ('report', 'complaint'):
            raise ValueError('Duplicate ticket or invalid kind')
        tickets.add(item['ticket_id'])
    by_id = {}
    for task in tasks:
        key = task.get('annotation_id')
        if key not in items or key in by_id or task.get('kind') != items[key]['kind']:
            raise ValueError('Unknown, duplicate, or mismatched task')
        # Explicit allowlist: outcomes, labels and annotator metadata never become features.
        try:
            request = TriageRequest.model_validate({k: v for k, v in task.items()
                                                   if k in TriageRequest.model_fields})
        except ValueError:
            raise ValueError('Invalid task request') from None
        by_id[key] = normalize(player_text(request.messages))
    if set(by_id) != set(items):
        raise ValueError('Tasks must match the full manifest')
    seen, rows = set(), []
    for label in gold:
        key = label.get('annotation_id')
        if key not in items or key in seen:
            raise ValueError('Unknown or duplicate gold task')
        seen.add(key)
        if any(label.get(k) != items[key].get(k) for k in ('ticket_id', 'reporter_hash', 'kind', 'split')):
            raise ValueError('Gold/manifest mismatch')
        annotators = label.get('annotators')
        if (not isinstance(annotators, list) or not annotators
                or any(not isinstance(a, str) or not a.strip() for a in annotators)
                or len(set(annotators)) != len(annotators)):
            raise ValueError('Gold requires distinct annotators')
        expected_review = 'agreed' if len(annotators) > 1 else 'single'
        if label.get('review_status') != expected_review:
            raise ValueError('Invalid gold review status')
        merge_annotations(manifest, [{**label, 'annotator_id': a, 'adjudication_status': 'labeled'}
                                     for a in annotators])
        if items[key]['split'] == 'holdout':
            continue
        text = by_id[key]
        if not text or not any(c.isalnum() for c in text):
            raise ValueError('Labeled training task has no usable player text before admin')
        rows.append({**label, 'text': text})
    return sorted(rows, key=lambda r: r['annotation_id'])


def grouped_validation(rows, kind, seed):
    from sklearn.metrics import accuracy_score, f1_score
    from sklearn.model_selection import GroupKFold

    texts = [r['text'] for r in rows]
    labels = [r['category'] for r in rows]
    groups = [r['reporter_hash'] for r in rows]
    count = min(5, len(set(groups)))
    if count < 2:
        return {'status': 'skipped', 'reason': 'insufficient_reporter_groups', 'scored_rows': 0}
    truth, predicted, regex, majority, folds = [], [], [], [], []
    for train, valid in GroupKFold(count, shuffle=True, random_state=seed).split(texts, labels, groups):
        train_groups = {groups[i] for i in train}
        valid_groups = {groups[i] for i in valid}
        assert not train_groups & valid_groups
        y_train = [labels[i] for i in train]
        fold = {'train_rows': len(train), 'valid_rows': len(valid), 'reporter_overlap': 0}
        if len(set(y_train)) < 2:
            folds.append({**fold, 'status': 'skipped_single_training_class'})
            continue
        model = make_pipeline(seed)
        model.fit([texts[i] for i in train], y_train)
        predicted.extend(model.predict([texts[i] for i in valid]).tolist())
        truth.extend(labels[i] for i in valid)
        regex.extend(TriageService._category(kind, texts[i]) for i in valid)
        majority.extend([Counter(y_train).most_common(1)[0][0]] * len(valid))
        folds.append({**fold, 'status': 'scored'})
    classes = [c for c in get_args(Category) if c.startswith(kind + '.')]

    def metrics(values):
        return {'accuracy': float(accuracy_score(truth, values)),
                'macro_f1_all_kind_classes': float(f1_score(truth, values, labels=classes,
                                                           average='macro', zero_division=0))}

    result = {'status': 'complete' if len(truth) == len(rows) else ('partial' if truth else 'skipped'),
              'scored_rows': len(truth), 'folds': folds, 'macro_f1_labels': classes}
    if truth:
        result.update(model=metrics(predicted), regex=metrics(regex), majority=metrics(majority))
    return result


def train_classifier(tasks, manifest, gold, seed=42):
    import sklearn
    import numpy
    import scipy
    import joblib

    rows = prepare_rows(tasks, manifest, gold)
    report = {'artifact_version': ARTIFACT_VERSION, 'preprocess_version': PREPROCESS_VERSION,
              'policy_version': POLICY_VERSION, 'sklearn_version': sklearn.__version__,
              'versions': {'python': platform.python_version(), 'numpy': numpy.__version__,
                           'scipy': scipy.__version__, 'joblib': joblib.__version__},
              'seed': seed, 'holdout_evaluated': False, 'confidence_calibrated': False,
              'validation_scope': 'reporter-grouped CV within labeled train only',
              'prediction_scope': 'raw model before service fallback and safety overrides', 'kinds': {}}
    # Fingerprint includes features and labels, but the report contains no raw texts or identifiers.
    report['train_fingerprint'] = hashlib.sha256(json.dumps(rows, sort_keys=True,
                                                          ensure_ascii=False).encode()).hexdigest()
    models = {}
    for kind in ('complaint', 'report'):
        selected = [r for r in rows if r['kind'] == kind]
        counts = dict(sorted(Counter(r['category'] for r in selected).items()))
        info = {'train_rows': len(selected), 'classes': counts,
                'missing_classes': sorted(c for c in get_args(Category) if c.startswith(kind + '.') and c not in counts),
                'review_status': dict(sorted(Counter(r['review_status'] for r in selected).items()))}
        report['kinds'][kind] = info
        if len(counts) < 2:
            info.update(status='not_trained', reason='requires_at_least_two_classes')
            continue
        info.update(status='trained', validation=grouped_validation(selected, kind, seed))
        model = make_pipeline(seed)
        model.fit([r['text'] for r in selected], [r['category'] for r in selected])
        models[kind] = model
    if not models:
        raise ValueError('No trainable kind: fill gold labels with at least two classes in train')
    return CategoryClassifier(models), report


def save_training(model, report, output):
    import joblib

    target = private_path(output)
    if target.exists():
        raise ValueError('Output directory already exists; refusing overwrite')
    target.mkdir(parents=True)
    joblib.dump({**report, 'models': model.models}, target / 'model.joblib')
    (target / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('tasks', 'manifest', 'gold', 'output'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()
    try:
        target = private_path(args.output)
        if target.exists():
            raise ValueError('Output directory already exists; refusing overwrite')
        with open(args.manifest, encoding='utf-8') as stream:
            manifest = json.load(stream)
        gold = list(read_records(args.gold))
        if not gold:
            parser.exit(2, 'No gold labels: complete B1 annotation and merge_labels before training.\n')
        model, report = train_classifier(list(read_records(args.tasks)), manifest,
                                         gold, args.seed)
        save_training(model, report, target)
    except (ValueError, KeyError, TypeError) as error:
        # Do not echo validation payloads or raw ticket text to the console.
        parser.exit(2, f'Training rejected ({type(error).__name__}); check labels, manifest and output.\n')
    print(json.dumps({'trained_kinds': sorted(model.models), 'holdout_evaluated': False}))


if __name__ == '__main__':
    main()
