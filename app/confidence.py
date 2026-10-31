"""Empirical category confidence: smoothed accuracy of the decision source per category.

The table (templates/confidence.json) holds aggregates only, fitted by scripts/fit_confidence.py
on labeled train rows. It is not a calibrated model probability and says nothing about the draft.
"""
import json
from functools import lru_cache
from importlib.resources import files


@lru_cache(maxsize=1)
def table():
    return json.loads(files('app').joinpath('templates', 'confidence.json').read_text(encoding='utf-8'))['table']


def lookup(source: str, category: str) -> float:
    cell = table().get(f'{source}|{category}')
    return float(cell['confidence']) if cell else 0.0
