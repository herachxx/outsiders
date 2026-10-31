import json
import subprocess
import sys


def test_process_benchmark_counts_failures_and_reports_peak_without_text(tmp_path):
    source, rules = tmp_path / 'input.jsonl', tmp_path / 'rules.json'
    source.write_text(json.dumps({'kind': 'report', 'messages': [{'role': 'player', 'text': 'PRIVATE вопрос'}]}) + '\ninvalid\n', encoding='utf-8')
    rules.write_text(json.dumps({'rules': []}), encoding='utf-8')
    report, predictions = tmp_path / 'report.json', tmp_path / 'predictions.jsonl'
    command = [sys.executable, '-m', 'scripts.benchmark_process', '--input', str(source), '--rules', str(rules),
               '--output', str(report), '--predictions', str(predictions)]
    subprocess.run(command, check=True, capture_output=True)
    result = json.loads(report.read_text(encoding='utf-8'))
    assert result['requests'] == 2
    assert result['errors'] == {'invalid_input': 1}
    assert result['peak_rss_bytes'] > 0
    assert result['elapsed_s'] > 0
    assert 'PRIVATE' not in str(result)
    assert len(predictions.read_text(encoding='utf-8').splitlines()) == 2
    assert subprocess.run(command, capture_output=True).returncode != 0
