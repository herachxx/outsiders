"""Local closed-loop pipeline benchmark; no network or production access."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import statistics
import time

from app.batch import predict_lines
from scripts.sample_for_labeling import private_path


def percentile(values, fraction=.95):
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)]


def measure(lines, service, workers):
    def run(line):
        start = time.perf_counter()
        error, human, fallback = None, False, False
        try:
            result = next(predict_lines([line], service))
            json.dumps(result, ensure_ascii=False, allow_nan=False)
            error = result.get('error')
            human = result.get('needs_human', False)
            fallback = any(r.startswith('safety_') for r in result.get('reasons', []))
        except Exception:
            # Count failed requests without logging ticket text or exception payloads.
            error = 'pipeline_exception'
        return time.perf_counter() - start, error, human, fallback

    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(run, lines))
    elapsed = time.perf_counter() - start
    durations = [r[0] for r in results]
    from collections import Counter
    errors = dict(Counter(r[1] for r in results if r[1]))
    return {'requests': len(results), 'workers': workers, 'elapsed_s': elapsed,
            'throughput_per_s': len(results) / elapsed,
            'mean_s': statistics.mean(durations), 'p50_s': percentile(durations, .5),
            'p95_s': percentile(durations), 'max_s': max(durations),
            'errors': errors, 'error_rate': sum(errors.values()) / len(results),
            'needs_human': sum(r[2] for r in results), 'safety_fallbacks': sum(r[3] for r in results),
            'latency_limit_met': percentile(durations) <= 5,
            'all_requests_succeeded': not errors}


def benchmark(lines, factory, parallelism=(1, 5, 20)):
    if not lines or any(n < 1 for n in parallelism):
        raise ValueError('Nonempty input and positive parallelism required')
    start = time.perf_counter()
    service = factory()
    initialization = time.perf_counter() - start
    first = measure(lines[:1], service, 1)
    warm = [measure(lines, service, n) for n in parallelism]
    return {'timestamp_utc': datetime.now(timezone.utc).isoformat(),
            'scope': 'local pipeline, JSON parse through output serialization; excludes HTTP/network and executor queue wait',
            'timing_components': 'classification, retrieval, generation and safety are included together, not individually profiled',
            'cold': {'service_initialization_s': initialization, 'first_request': first,
                     'note': 'Fresh service in current process; Python imports and OS disk caches are not reset'},
            'warm': warm, 'input_sha256': hashlib.sha256(''.join(lines).encode()).hexdigest(),
            'environment': {'python': platform.python_version(), 'platform': platform.platform(),
                            'processor': platform.processor(), 'logical_cpus': os.cpu_count()},
            'cost': {'mode': 'local', 'external_inference_usd_per_request': 0,
                     'note': 'No external model calls; excludes hardware, electricity and human review'},
            'quality_proven': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('input', 'rules', 'output'): parser.add_argument('--' + name, required=True)
    parser.add_argument('--model')
    parser.add_argument('--limit', type=int, default=1000)
    args = parser.parse_args()
    target = private_path(args.output)
    if target.exists(): parser.exit(2, 'Output already exists.\n')
    if args.limit < 1: parser.exit(2, 'Positive limit required.\n')
    import gzip
    from itertools import islice
    opener = gzip.open if args.input.endswith('.gz') else open
    with opener(args.input, 'rt', encoding='utf-8') as stream:
        lines = list(islice(stream, args.limit))
    from app.core import TriageService
    from app.rules import RuleIndex
    from app.classifier import CategoryClassifier
    def factory():
        return TriageService(RuleIndex.from_file(args.rules), CategoryClassifier.load(args.model) if args.model else None)
    report = benchmark(lines, factory)
    report['backend'] = 'local-classifier-template' if args.model else 'heuristic-template'
    root = Path(__file__).resolve().parents[1]
    report['code_hashes'] = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in sorted((root / 'app').rglob('*')) if p.suffix in ('.py', '.json')}
    report['rules_sha256'] = hashlib.sha256(Path(args.rules).read_bytes()).hexdigest()
    if args.model: report['model_sha256'] = hashlib.sha256(Path(args.model).read_bytes()).hexdigest()
    report['language_model_enabled'] = bool(os.environ.get('GRAND_LANGUAGE_MODEL_PATH'))
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps({'requests': len(lines), 'warm': report['warm']}))


if __name__ == '__main__':
    main()
