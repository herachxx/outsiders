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


def predict_lines(lines: Iterable[str], service: TriageService, format: str = 'submission') -> Iterator[dict]:
    if format not in ('submission', 'internal'):
        raise ValueError('Unknown output format')
    for line in lines:
        try:
            payload = json.loads(line)
            if isinstance(payload, dict):
                payload = {k: v for k, v in payload.items() if k not in {
                    'ticket_id', 'created_at', 'lang', 'status', 'verdict', 'punishment',
                    'violation', 'category', 'priority'}}
            request = TriageRequest.model_validate(payload)
        except (json.JSONDecodeError, ValidationError, TypeError, ValueError):
            yield {"error": "invalid_input"}
            continue
        try:
            result = TriageResponse.model_validate(service.triage(request))
            yield to_submission(result) if format == 'submission' else result.model_dump()
        except ValidationError:
            yield {'error': 'invalid_output'}


def main() -> None:
    parser = argparse.ArgumentParser(description="Predict one JSON object for every JSONL row")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--rules", required=True)
    parser.add_argument('--model', help='Trusted local model.joblib from scripts.train (optional)')
    parser.add_argument('--format', choices=['submission', 'internal'], default='submission')
    args = parser.parse_args()
    classifier = CategoryClassifier.load(args.model) if args.model else None
    service = TriageService(RuleIndex.from_file(args.rules), classifier)
    opener = gzip.open if args.input.endswith(".gz") else open
    with opener(args.input, "rt", encoding="utf-8") as source, open(args.output, "w", encoding="utf-8") as target:
        for prediction in predict_lines(source, service, args.format):
            target.write(json.dumps(prediction, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
