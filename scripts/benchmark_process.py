"""Fresh-process batch wall time and OS peak resident memory; private outputs only."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
from itertools import islice
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

from scripts.sample_for_labeling import private_path


def peak_rss_bytes():
    if sys.platform == 'win32':
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in ('PeakWorkingSetSize', 'WorkingSetSize',
                'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
                'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage')]
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        psapi = ctypes.WinDLL('psapi', use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        return counters.PeakWorkingSetSize
    import resource
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak if sys.platform == 'darwin' else peak * 1024


def worker(args):
    from app.batch import predict_lines
    from app.core import TriageService
    from app.rules import RuleIndex
    from app.classifier import CategoryClassifier
    service = TriageService(RuleIndex.from_file(args.rules), CategoryClassifier.load(args.model) if args.model else None)
    opener = gzip.open if args.input.endswith('.gz') else open
    errors, count = Counter(), 0
    digest = hashlib.sha256()
    with opener(args.input, 'rt', encoding='utf-8') as source, Path(args.predictions).open('x', encoding='utf-8') as target:
        def lines():
            for line in islice(source, args.limit):
                digest.update(line.encode('utf-8'))
                yield line
        for result in predict_lines(lines(), service):
            target.write(json.dumps(result, ensure_ascii=False, allow_nan=False) + '\n')
            count += 1
            if result.get('error'):
                errors[result['error']] += 1
    return {'requests': count, 'errors': dict(errors), 'peak_rss_bytes': peak_rss_bytes(),
            'input_sha256': digest.hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('input', 'rules', 'output', 'predictions'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--limit', type=int, default=1000)
    parser.add_argument('--model')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    report_path, predictions = private_path(args.output), private_path(args.predictions)
    if args.limit < 1 or report_path == predictions or report_path.exists() or predictions.exists():
        parser.error('Positive limit and distinct, new private outputs required')
    for target in (report_path, predictions):
        target.parent.mkdir(parents=True, exist_ok=True)
    if args.worker:
        print(json.dumps(worker(args)))
        return
    started = time.perf_counter()
    child = subprocess.run([sys.executable, '-m', 'scripts.benchmark_process', *sys.argv[1:], '--worker'],
                           capture_output=True, text=True)
    elapsed = time.perf_counter() - started
    if child.returncode:
        parser.exit(1, 'Benchmark worker failed; partial predictions may remain. Report not created.\n')
    report = json.loads(child.stdout)
    report.update({'elapsed_s': elapsed, 'timestamp_utc': datetime.now(timezone.utc).isoformat(),
                   'python': platform.python_version(), 'platform': platform.platform(),
                   'backend': 'local-classifier-template' if args.model else 'heuristic-template',
                   'scope': 'fresh Python worker startup, imports, rules/model load, input read, inference and prediction file write; no HTTP',
                   'memory_scope': 'OS peak resident memory of worker only; excludes parent, GPU and other processes',
                   'quality_proven': False, 'rules_sha256': hashlib.sha256(Path(args.rules).read_bytes()).hexdigest()})
    root = Path(__file__).resolve().parents[1]
    report['code_hashes'] = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
                           for path in sorted((root / 'app').rglob('*')) if path.suffix in ('.py', '.json')}
    if args.model:
        report['model_sha256'] = hashlib.sha256(Path(args.model).read_bytes()).hexdigest()
    with report_path.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps({key: report[key] for key in ('requests', 'elapsed_s', 'peak_rss_bytes', 'errors')}))


if __name__ == '__main__':
    main()
