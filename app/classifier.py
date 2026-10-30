"""Optional local category model. Only load artifacts from a trusted trainer."""
from typing import get_args

from .preprocess import PREPROCESS_VERSION, normalize
from .priority import POLICY_VERSION
from .schemas import Category

ARTIFACT_VERSION = 1


def make_pipeline(seed=42):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import FeatureUnion, Pipeline

    features = FeatureUnion([
        ('word', TfidfVectorizer(ngram_range=(1, 2), token_pattern=r'(?u)\b\w+\b',
                                sublinear_tf=True, max_features=40000)),
        ('char', TfidfVectorizer(analyzer='char', ngram_range=(2, 5),
                                sublinear_tf=True, max_features=80000)),
    ])
    return Pipeline([('features', features),
                     ('classifier', LogisticRegression(C=2.0, class_weight='balanced',
                                                       max_iter=1000, random_state=seed))])


class CategoryClassifier:
    def __init__(self, models, calibrated_kinds=()):
        self.models = models
        self.calibrated_kinds = set(calibrated_kinds)

    def confidence(self, kind, text):
        if kind not in self.calibrated_kinds or self.predict(kind, text) is None:
            return 0.0
        return float(self.models[kind].predict_proba([normalize(text)]).max())

    def predict(self, kind, text):
        model = self.models.get(kind)
        text = normalize(text)
        if model is None or not text:
            return None
        features = model.named_steps['features'].transform([text])
        if features.nnz == 0:
            return None
        category = str(model.named_steps['classifier'].predict(features)[0])
        if category not in get_args(Category) or not category.startswith(kind + '.'):
            raise ValueError('Invalid model category')
        return category

    @classmethod
    def load(cls, path):
        # joblib can execute code. The path is local operator configuration,
        # never an HTTP input; metadata validation is NOT a security sandbox.
        import joblib
        import sklearn

        artifact = joblib.load(path)
        expected = {'artifact_version': ARTIFACT_VERSION, 'preprocess_version': PREPROCESS_VERSION,
                    'policy_version': POLICY_VERSION, 'sklearn_version': sklearn.__version__}
        if not isinstance(artifact, dict) or any(artifact.get(k) != v for k, v in expected.items()):
            raise ValueError('Incompatible model artifact; retrain with this environment')
        models = artifact.get('models')
        if not isinstance(models, dict) or not models or set(models) - {'report', 'complaint'}:
            raise ValueError('Invalid model kinds')
        for kind, model in models.items():
            classes = set(model.classes_)
            allowed = {c for c in get_args(Category) if c.startswith(kind + '.')}
            if len(classes) < 2 or not classes <= allowed:
                raise ValueError('Invalid model classes')
        calibrated = artifact.get('calibrated_kinds', [])
        if not isinstance(calibrated, list) or not set(calibrated) <= set(models):
            raise ValueError('Invalid calibrated model kinds')
        return cls(models, calibrated)
