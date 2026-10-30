"""JSONL prediction with one output row per input row."""

import argparse
import gzip
import json
from collections.abc import Iterable, Iterator

from pydantic import ValidationError

from .core import TriageService
from .rules import RuleIndex


def predict_lines(lines: Iterable[str], service: TriageService) -> Iterator[dict]:
    for line in lines:
        try:
            payload = json.loads(line)
            yield service.triage(payload)
        except (json.JSONDecodeError, ValidationError, TypeError, ValueError):
            yield {"error": "invalid_input"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Predict one JSON object for every JSONL row")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--rules", required=True)
    args = parser.parse_args()
    service = TriageService(RuleIndex.from_file(args.rules))
    opener = gzip.open if args.input.endswith(".gz") else open
    with opener(args.input, "rt", encoding="utf-8") as source, open(args.output, "w", encoding="utf-8") as target:
        for prediction in predict_lines(source, service):
            target.write(json.dumps(prediction, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
