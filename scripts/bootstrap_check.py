"""Small self-check for launchers: no heavy ML dependency unless local weights exist.

Run as `python -m scripts.bootstrap_check`. This check has no side effects.
"""
from __future__ import annotations
import importlib
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def needs_ml(root: Path = ROOT) -> bool:
    model = os.environ.get('GRAND_TEAM_MODELS')
    base = Path(model) if model else root / 'private' / 'models'
    return (base / 'category_model.cbm').is_file() and (base / 'classifier_meta.joblib').is_file()

def missing(root: Path = ROOT) -> list[str]:
    modules = ['fastapi','uvicorn','pydantic','PIL','multipart','httpx']
    if needs_ml(root):
        modules += ['catboost','sklearn','joblib','numpy','scipy']
    missing = []
    for name in modules:
        try:importlib.import_module(name)
        except (ImportError, OSError):missing.append(name)
    if needs_ml(root) and 'sklearn' not in missing:
        # Serialized TF-IDF artifacts were fitted on this exact sklearn build.
        import sklearn
        if sklearn.__version__ != '1.9.1':
            missing.append('scikit-learn==1.9.1 (обязательно для сохранённых весов)')
    return missing

def main() -> int:
    import sys
    if sys.version_info < (3,12):
        print('Требуется Python 3.12 или новее.');return 2
    problems=missing()
    if problems:
        print('Не установлено: ' + ', '.join(problems))
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
