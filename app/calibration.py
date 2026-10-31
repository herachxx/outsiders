"""Reporter-disjoint fit/calibration/check split within train only."""


def fit_calibrated(rows, seed=42):
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.frozen import FrozenEstimator
    from sklearn.model_selection import GroupShuffleSplit
    from app.classifier import make_pipeline

    groups = [r['reporter_hash'] for r in rows]
    fit, rest = next(GroupShuffleSplit(n_splits=1, test_size=.4, random_state=seed).split(rows, groups=groups))
    remaining = [rows[i] for i in rest]
    calibration, check = next(GroupShuffleSplit(n_splits=1, test_size=.5, random_state=seed).split(
        remaining, groups=[r['reporter_hash'] for r in remaining]))
    partitions = [[rows[i] for i in fit], [remaining[i] for i in calibration], [remaining[i] for i in check]]
    classes = {r['category'] for r in rows}
    if any({r['category'] for r in part} != classes for part in partitions):
        raise ValueError('Every calibration partition must contain all training classes')
    model = make_pipeline(seed)
    model.fit([r['text'] for r in partitions[0]], [r['category'] for r in partitions[0]])
    features = model.named_steps['features']
    # The base estimator is frozen: all calibration rows may be scored without refitting it.
    indices = list(range(len(partitions[1])))
    estimator = CalibratedClassifierCV(FrozenEstimator(model.named_steps['classifier']),
                                       method='sigmoid', cv=[(indices, indices)], ensemble=False)
    estimator.fit(features.transform([r['text'] for r in partitions[1]]),
                  [r['category'] for r in partitions[1]])
    model.steps[-1] = ('classifier', estimator)
    probabilities = model.predict_proba([r['text'] for r in partitions[2]])
    truth = [r['category'] for r in partitions[2]]
    predicted = model.classes_[probabilities.argmax(axis=1)]
    confidence = probabilities.max(axis=1)
    bins = []
    for index in range(10):
        selected = [i for i, value in enumerate(confidence) if min(int(value * 10), 9) == index]
        bins.append({'lower': index / 10, 'upper': (index + 1) / 10, 'count': len(selected),
                     'confidence': float(sum(confidence[i] for i in selected) / len(selected)) if selected else None,
                     'accuracy': sum(predicted[i] == truth[i] for i in selected) / len(selected) if selected else None})
    return model, {'method': 'sigmoid', 'partition_rows': dict(zip(('fit', 'calibration', 'check'), map(len, partitions))),
                   'reporter_overlap': 0, 'check_reliability_bins': bins,
                   'check_ece': sum(b['count'] * abs(b['confidence'] - b['accuracy']) for b in bins if b['count']) / len(truth)}
