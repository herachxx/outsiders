"""JSONL prediction with one output row per input row."""

import argparse
import gzip
import json
from collections.abc import Iterable, Iterator

from pydantic import ValidationError

from .core import TriageService
from .rules import RuleIndex
from .schemas import TriageRequest, TriageResponse
from .submission import to_submission
from .classifier import CategoryClassifier


TEXT_FIELDS = ('region', 'server_lang', 'rule_refs_raw', 'reporter_hash', 'reported_hash', 'reported_nick')
ROLES = ('player', 'reported_player', 'admin')


def _count(value) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def coerce_ticket(raw) -> dict:
    """Best-effort clean-up of a batch record; the strict HTTP contract is unchanged.

    Unknown fields (including exported outcomes) are dropped, numbers are coerced, over-long text and message
    lists are cut and a missing player message becomes an empty one, so odd records still get a safe result.
    Records without a valid kind or message list remain errors.
    """
    if not isinstance(raw, dict) or raw.get('kind') not in ('complaint', 'report') or not isinstance(raw.get('messages'), list):
        raise ValueError('Unusable ticket')
    messages = []
    for message in raw['messages']:
        if not isinstance(message, dict) or message.get('role') not in ROLES:
            continue
        text = message.get('text')
        ts = message.get('ts')
        messages.append({'role': message['role'], 'text': text[:20000] if isinstance(text, str) else '',
                         'ts': ts if isinstance(ts, str) else None, 'attachments': _count(message.get('attachments'))})
    players = [m for m in messages if m['role'] == 'player']
    messages = messages[:100]
    if not players:
        messages = [{'role': 'player', 'text': '', 'ts': None, 'attachments': 0}] + messages[:99]
    elif not any(m['role'] == 'player' for m in messages):
        messages[-1] = players[0]
    ticket = {'kind': raw['kind'], 'messages': messages, 'images_count': _count(raw.get('images_count'))}
    for field in TEXT_FIELDS:
        if isinstance(raw.get(field), str):
            ticket[field] = raw[field]
    return ticket


def _predict_lines(lines: Iterable[str], service: TriageService, format: str = 'submission') -> Iterator[dict]:
    if format not in ('submission', 'internal'):
        raise ValueError('Unknown output format')
    for line in lines:
        try:
            request = TriageRequest.model_validate(coerce_ticket(json.loads(line)))
        except (json.JSONDecodeError, ValidationError, TypeError, ValueError):
            yield {"error": "invalid_input"}
            continue
        try:
            result = TriageResponse.model_validate(service.triage(request))
            yield to_submission(result) if format == 'submission' else result.model_dump()
        except ValidationError:
            yield {'error': 'invalid_output'}


def predict_lines(lines, service, format='submission', history=False):
    if not history:
        yield from _predict_lines(lines, service, format)
        return
    from datetime import datetime
    from .history import History
    from .dedupe import annotate_history
    source = list(lines)
    outputs = list(_predict_lines(source, service, format))
    ordered = []
    for index, line in enumerate(source):
        if 'error' in outputs[index]:
            continue
        try:
            raw = json.loads(line)
            ts = datetime.fromisoformat(raw['created_at'].replace('Z', '+00:00'))
            if ts.tzinfo is None or not isinstance(raw['ticket_id'], str) or not raw['ticket_id']:
                raise ValueError('Missing timezone or identity')
            allowed = {k: v for k, v in raw.items() if k in TriageRequest.model_fields}
            request = TriageRequest.model_validate(allowed)
            ordered.append((ts.timestamp(), index, raw['ticket_id'], request))
        except (ValueError, KeyError, TypeError):
            outputs[index]['reasons'].append('history_metadata_missing_or_invalid')
    store = History()
    try:
        for timestamp, index, ticket_id, request in sorted(ordered, key=lambda item: (item[0], item[1])):
            try:
                annotate_history(outputs[index], request, store, ticket_id, timestamp)
            except ValueError:
                outputs[index] = {'error': 'history_identity_conflict'}
        yield from outputs
    finally:
        store.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Predict one JSON object for every JSONL row")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--rules", required=True)
    parser.add_argument('--model', help='Trusted local model.joblib from scripts.train (optional)')
    parser.add_argument('--format', choices=['submission', 'internal'], default='submission')
    parser.add_argument('--history', action='store_true', help='Chronological exact duplicate detection; buffers input')
    args = parser.parse_args()
    classifier = CategoryClassifier.load(args.model) if args.model else None
    service = TriageService(RuleIndex.from_file(args.rules), classifier)
    opener = gzip.open if args.input.endswith(".gz") else open
    out_opener = gzip.open if args.output.endswith(".gz") else open  # compressed output saves ~10x disk on large runs
    mode = "wt" if args.output.endswith(".gz") else "w"
    with opener(args.input, "rt", encoding="utf-8") as source, out_opener(args.output, mode, encoding="utf-8") as target:
        for prediction in predict_lines(source, service, args.format, args.history):
            target.write(json.dumps(prediction, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
