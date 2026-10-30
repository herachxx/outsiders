"""Deterministic drafts from reviewed inputs; never echo untrusted ticket text."""
import json
from functools import lru_cache
from importlib.resources import files


@lru_cache(maxsize=1)
def templates():
    return json.loads(files('app').joinpath('templates', 'drafts.json').read_text(encoding='utf-8'))


def build_draft(request, category, lang, has_evidence, cited):
    actual_lang = lang if lang in templates() else 'en'
    phrases = templates()[actual_lang]
    if category == 'complaint.admin':
        key = 'admin'
    elif category.startswith('complaint.') or category == 'report.complaint':
        key = 'complaint'
    else:
        key = category.removeprefix('report.')
    parts = [phrases.get(key, phrases['other'])]
    if key in ('complaint', 'admin'):
        parts.append(phrases['evidence_present' if has_evidence else 'evidence_missing'])
        if not request.reported_nick and not request.reported_hash:
            parts.append(phrases['target_missing'])
    if request.region is None or not request.region.strip():
        parts.append(phrases['server_missing'])
    if cited:
        refs = ', '.join(dict.fromkeys(f"{c['section_id']}/{c['ref']}" for c in cited))
        parts.append(phrases['rules'].replace('{refs}', refs))
    return {'lang': actual_lang, 'text': ' '.join(parts), 'cited': cited}
