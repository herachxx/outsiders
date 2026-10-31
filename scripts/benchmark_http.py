"""Measure the local HTTP boundary with bounded concurrent requests."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from scripts.benchmark import percentile
from scripts.sample_for_labeling import private_path


def require_loopback(url):
    parsed = urlsplit(url)
    if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost') or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Only plain HTTP loopback URLs are allowed')
    if parsed.path not in ('', '/triage'):
        raise ValueError('URL must point to the local service root or /triage')
    return f'{parsed.scheme}://{parsed.netloc}/triage?format=internal'


def measure_http(payloads, url, workers, timeout=10):
    def run(payload):
        started = time.perf_counter()
        try:
            request = Request(url, data=payload, headers={'Content-Type': 'application/json'}, method='POST')
            with urlopen(request, timeout=timeout) as response:
                body = json.load(response)
                error = None if response.status == 200 and 'category' in body else 'invalid_response'
        except HTTPError as exc:
            error = f'http_{exc.code}'
        except (URLError, TimeoutError, OSError):
            error = 'transport_error'
        except (ValueError, UnicodeError):
            error = 'invalid_response'
        return time.perf_counter() - started, error

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(run, payloads))
    elapsed = time.perf_counter() - started
    durations = [duration for duration, _ in results]
    errors = dict(Counter(error for _, error in results if error))
    return {'requests': len(results), 'workers': workers, 'elapsed_s': elapsed,
            'throughput_per_s': len(results) / elapsed, 'mean_s': statistics.mean(durations),
            'p50_s': percentile(durations, .5), 'p95_s': percentile(durations),
            'max_s': max(durations), 'errors': errors,
            'error_rate': sum(errors.values()) / len(results),
            'latency_limit_met': percentile(durations) <= 5 and not errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8000')
    parser.add_argument('--output', required=True)
    parser.add_argument('--requests', type=int, default=1000)
    parser.add_argument('--workers', type=int, nargs='+', default=[1, 5, 20])
    args = parser.parse_args()
    url = require_loopback(args.url)
    if args.requests < 1 or any(worker < 1 for worker in args.workers):
        parser.error('Requests and workers must be positive')
    target = private_path(args.output)
    if target.exists():
        parser.error('Output already exists')
    payload = json.dumps({'kind': 'report', 'messages': [{'role': 'player', 'text': 'Как восстановить доступ к аккаунту?'}]}, ensure_ascii=False).encode('utf-8')
    runs = [measure_http([payload] * args.requests, url, workers) for workers in args.workers]
    report = {'timestamp_utc': datetime.now(timezone.utc).isoformat(),
              'scope': 'local loopback HTTP, client request through full response; includes server queue wait, excludes client executor queue wait',
              'input': 'one synthetic account question repeated; no real tickets',
              'warm': runs, 'quality_proven': False,
              'cost': {'external_inference_usd_per_request': 0, 'note': 'Only valid for the local heuristic/template server without external model calls'}}
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps({'warm': runs}, ensure_ascii=False))


if __name__ == '__main__':
    main()
