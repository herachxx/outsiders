"""JSONL prediction with one output row per input row."""

import argparse
import gzip
import json
import os
import sys
from collections.abc import Iterable, Iterator

from pydantic import ValidationError

from .core import TriageService
from .rules import RuleIndex
from .schemas import TriageRequest, TriageResponse
from .submission import to_submission
from .classifier import CategoryClassifier


HISTORY_AUTO_MAX_BYTES = 200 * 1024 * 1024
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
    from datetime import datetime, timezone
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
            if ts.tzinfo is None:
                # The export has no timezone; only differences matter, so treat all stamps as UTC.
                ts = ts.replace(tzinfo=timezone.utc)
            if not isinstance(raw['ticket_id'], str) or not raw['ticket_id']:
                raise ValueError('Missing identity')
            request = TriageRequest.model_validate(coerce_ticket(raw))
            ordered.append((ts.timestamp(), index, raw['ticket_id'], request))
        except (ValueError, KeyError, TypeError):
            outputs[index]['reasons'].append('history_metadata_missing_or_invalid')
    store = History()
    try:
        for timestamp, index, ticket_id, request in sorted(ordered, key=lambda item: (item[0], item[1])):
            try:
                annotate_history(outputs[index], request, store, ticket_id, timestamp)
            except ValueError:
                # A reused ticket id must not cost the ticket its result; keep the triage and flag the conflict.
                outputs[index]['reasons'].append('history_identity_conflict')
        yield from outputs
    finally:
        store.close()


def is_json_array(path, opener) -> bool:
    """True when the first non-blank character of the file is '[' (a JSON array of tickets)."""
    with opener(path, "rt", encoding="utf-8") as stream:
        for chunk in iter(lambda: stream.read(4096), ""):
            stripped = chunk.lstrip("\ufeff \t\r\n")
            if stripped:
                return stripped[0] == "["
    return False


def array_to_lines(stream):
    """Turn a JSON array of tickets into one JSON line per element, keeping order and count."""
    try:
        items = json.load(stream)
    except json.JSONDecodeError:
        return iter(["{"])   # one invalid_input row for a file that cannot be parsed at all
    if not isinstance(items, list):
        return iter([json.dumps(items)])
    return iter(json.dumps(item, ensure_ascii=False) for item in items)


def find_rules(explicit=None):
    """Explicit path (must exist), else GRAND_RULES_PATH, else a rules.json next to the working directory."""
    if explicit:
        return explicit
    candidates = [os.environ.get("GRAND_RULES_PATH"), "rules.json", "data/rules.json", "handout/rules.json",
                  "../handout/rules.json", "../rules.json"]
    return next((c for c in candidates if c and os.path.isfile(c)), None)


def main() -> None:
    parser = argparse.ArgumentParser(description="Predict one JSON object for every JSONL row")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--rules", help="rules.json; default: GRAND_RULES_PATH, then ./rules.json, ./data/rules.json, ./handout/rules.json")
    parser.add_argument('--model', help='Trusted local model.joblib from scripts.train (optional)')
    parser.add_argument('--format', choices=['submission', 'internal'], default='submission')
    parser.add_argument('--input-format', choices=['auto', 'json', 'jsonl'], default='auto',
                        help='auto: a file starting with [ is a JSON array of tickets, otherwise one ticket per line')
    parser.add_argument('--output-format', choices=['auto', 'json', 'jsonl'], default='auto',
                        help='auto: a JSON array in gives a JSON array out, lines in give lines out')
    parser.add_argument('--history', action=argparse.BooleanOptionalAction, default=None,
                        help='Chronological duplicate detection (buffers the input in memory); default: on for inputs under 200 MB')
    args = parser.parse_args()
    classifier = CategoryClassifier.load(args.model) if args.model else None
    rules_path = find_rules(args.rules)
    if rules_path is None:
        print("warning: rules.json not found, drafts will have no rule citations", file=sys.stderr)
    service = TriageService(RuleIndex.from_file(rules_path) if rules_path else RuleIndex([]), classifier)
    opener = gzip.open if args.input.endswith(".gz") else open
    out_opener = gzip.open if args.output.endswith(".gz") else open  # compressed output saves ~10x disk on large runs
    mode = "wt" if args.output.endswith(".gz") else "w"
    as_array = is_json_array(args.input, opener) if args.input_format == "auto" else args.input_format == "json"
    as_array_out = as_array if args.output_format == "auto" else args.output_format == "json"
    with opener(args.input, "rt", encoding="utf-8") as source:
        lines = array_to_lines(source) if as_array else source
        use_history = args.history if args.history is not None else os.path.getsize(args.input) < HISTORY_AUTO_MAX_BYTES
        with out_opener(args.output, mode, encoding="utf-8") as target:
            if as_array_out:
                results = list(predict_lines(lines, service, args.format, use_history))
                target.write(json.dumps(results, ensure_ascii=False, indent=1) + "\n")
            else:
                for prediction in predict_lines(lines, service, args.format, use_history):
                    target.write(json.dumps(prediction, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
