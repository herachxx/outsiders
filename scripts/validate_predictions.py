"""Independent check of a predictions file against the case PDF contract, rules.json and taxonomy.json.

    python -m scripts.validate_predictions --input tickets.jsonl --predictions pred.jsonl --rules rules.json --taxonomy taxonomy.json

Exit code 1 and a count per problem type when anything is wrong; the report never prints ticket text.
"""
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import re
import sys

KEYS = {'lang', 'category', 'priority', 'is_spam_or_duplicate', 'extracted', 'draft_reply', 'needs_human', 'confidence', 'reasons'}
EXTRACTED = {'nickname', 'rule_refs', 'has_evidence', 'server'}
LANGS = {'ru', 'kk', 'uz', 'en', 'es', 'pt', 'lat', 'und'}
ALWAYS_HUMAN = {'report.account', 'report.payment', 'complaint.admin'}
PROMISE = re.compile(r'разбан|верн[её]м|возмест|компенсир|получит (?:мут|бан|наказание)|будет (?:наказан|забанен)|unban|refund', re.I)


def read_rows(path):
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path, 'rt', encoding='utf-8') as stream:
        text = stream.read()
    if text.lstrip('﻿ \t\r\n').startswith('['):
        return json.loads(text)
    return [json.loads(line) if line.strip() else None for line in text.splitlines()]


def validate(inputs, predictions, refs, categories, priorities):
    problems = Counter()
    if len(inputs) != len(predictions):
        problems['row_count_mismatch'] += 1
    for source, row in zip(inputs, predictions):
        if not isinstance(row, dict) or 'error' in row:
            problems['error_row'] += 1
            continue
        if set(row) != KEYS:
            problems['wrong_top_level_keys'] += 1
            continue
        if row['category'] not in categories: problems['unknown_category'] += 1
        if row['priority'] not in priorities: problems['unknown_priority'] += 1
        if row['lang'] not in LANGS: problems['unknown_lang'] += 1
        if isinstance(source, dict) and source.get('kind') and row['category'].split('.')[0] != source['kind']:
            problems['category_kind_mismatch'] += 1
        if not isinstance(row['is_spam_or_duplicate'], bool) or not isinstance(row['needs_human'], bool):
            problems['non_boolean_flag'] += 1
        if not isinstance(row['confidence'], (int, float)) or isinstance(row['confidence'], bool) or not 0 <= row['confidence'] <= 1:
            problems['confidence_out_of_range'] += 1
        if not isinstance(row['reasons'], list): problems['reasons_not_list'] += 1
        extracted = row['extracted']
        if not isinstance(extracted, dict) or set(extracted) != EXTRACTED: problems['extracted_keys'] += 1
        draft = row['draft_reply']
        if not isinstance(draft, dict) or set(draft) != {'lang', 'text', 'cited'}:
            problems['draft_keys'] += 1
            continue
        if not str(draft['text']).strip(): problems['empty_draft'] += 1
        for ref in draft['cited'] if isinstance(draft['cited'], list) else []:
            if str(ref) not in refs: problems['hallucinated_citation'] += 1
        if row['category'] in ALWAYS_HUMAN and not row['needs_human']: problems['sensitive_not_human'] += 1
        if row['category'] in ('report.account', 'report.payment') and row['priority'] != 'p0': problems['sensitive_not_p0'] += 1
        if row['needs_human'] and not row['reasons']: problems['human_without_reason'] += 1
        if PROMISE.search(str(draft['text'])): problems['promise_in_draft'] += 1
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True)
    parser.add_argument('--predictions', required=True)
    parser.add_argument('--rules', required=True)
    parser.add_argument('--taxonomy', required=True)
    args = parser.parse_args()
    rules = json.loads(Path(args.rules).read_text(encoding='utf-8'))
    taxonomy = json.loads(Path(args.taxonomy).read_text(encoding='utf-8'))
    refs = {str(point['ref']) for section in rules['rules'] for point in section.get('points', [])}
    problems = validate(read_rows(args.input), read_rows(args.predictions), refs,
                        {c['code'] for c in taxonomy['categories']}, {p['code'] for p in taxonomy['priorities']})
    print(json.dumps({'ok': not problems, 'problems': dict(problems)}, ensure_ascii=False))
    sys.exit(1 if problems else 0)


if __name__ == '__main__':
    main()
