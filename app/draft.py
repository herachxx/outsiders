"""Deterministic drafts from reviewed inputs; never echo untrusted ticket text."""
import json
from functools import lru_cache
from importlib.resources import files


@lru_cache(maxsize=1)
def templates():
    return json.loads(files('app').joinpath('templates', 'drafts.json').read_text(encoding='utf-8'))


SPECIFIC_COMPLAINTS = ('insult', 'cheat', 'dm', 'scam', 'rmt_ads', 'invalid')


def draft_language(request, lang):
    """Reply in the detected language; for unknown text use the server language, else Russian (the main audience)."""
    if lang in templates():
        return lang
    hint = (getattr(request, 'server_lang', None) or '').strip().casefold()
    return hint if hint in templates() else 'ru'


def build_draft(request, category, lang, has_evidence, cited):
    actual_lang = draft_language(request, lang)
    phrases = templates()[actual_lang]
    if category == 'complaint.admin':
        key = 'admin'
    elif category.startswith('complaint.') or category == 'report.complaint':
        key = category.removeprefix('complaint.')
        if key not in SPECIFIC_COMPLAINTS:
            key = 'complaint'
    else:
        key = category.removeprefix('report.')
    is_complaint = key in SPECIFIC_COMPLAINTS or key in ('complaint', 'admin')
    parts = [phrases['greeting_complaint' if is_complaint else 'greeting_report'],
             phrases.get(key, phrases['other'])]
    if key in SPECIFIC_COMPLAINTS:
        parts.append(phrases['review'])
    if is_complaint:
        parts.append(phrases['evidence_present' if has_evidence else 'evidence_missing'])
        if not request.reported_nick and not request.reported_hash:
            parts.append(phrases['target_missing'])
    # Dataset region codes locate the audience, not an individual game server.
    # The current UI also uses this field for an explicitly entered server.
    region = (request.region or '').strip().casefold()
    if not region or region in {'cis', 'uz', 'kz'}:
        parts.append(phrases['server_missing'])
    if cited:
        refs = ', '.join(dict.fromkeys(f"{c['section_id']}/{c['ref']}" for c in cited))
        parts.append(phrases['rules'].replace('{refs}', refs))
    if is_complaint:
        parts.append(phrases['closing'])
    return {'lang': actual_lang, 'text': ' '.join(parts), 'cited': cited}
