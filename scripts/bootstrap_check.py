"""Small self-check for launchers: ML libraries are required only when a trained model is configured.

Run as `python -m scripts.bootstrap_check`. This check has no side effects.
"""
from __future__ import annotations
import importlib
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def needs_ml(root: Path = ROOT) -> bool:
    """True when GRAND_MODEL_PATH points to an existing model artifact (it is never shipped in the repository)."""
    model = os.environ.get('GRAND_MODEL_PATH')
    return bool(model) and Path(model).is_file()


def missing(root: Path = ROOT) -> list[str]:
    modules = ['fastapi', 'uvicorn', 'pydantic', 'PIL', 'multipart', 'httpx']
    if needs_ml(root):
        modules += ['sklearn', 'joblib', 'numpy', 'scipy']
    missing = []
    for name in modules:
        try:
            importlib.import_module(name)
        except (ImportError, OSError):
            missing.append(name)
    return missing


def main() -> int:
    import sys
    if sys.version_info < (3, 12):
        print('Требуется Python 3.12 или новее.')
        return 2
    problems = missing()
    if problems:
        print('Не установлено: ' + ', '.join(problems))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
