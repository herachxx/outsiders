import json
import pytest
from app.core import TriageService
from app.rules import RuleIndex
from scripts.benchmark import benchmark, percentile


def test_percentile_keeps_slowest_failures():
    assert percentile([1] * 18 + [10, 100]) == 10


def test_benchmark_counts_errors_and_does_not_publish_text():
    line = json.dumps({'kind': 'report', 'messages': [{'role': 'player', 'text': 'PRIVATE текст'}]})
    result = benchmark([line, 'invalid'], lambda: TriageService(RuleIndex([])), (1, 2))
    assert 'PRIVATE' not in str(result)
    for run in result['warm']:
        assert run['requests'] == 2
        assert run['errors'] == {'invalid_input': 1}
        assert run['error_rate'] == .5
        assert not run['all_requests_succeeded']
    assert result['cost']['external_inference_usd_per_request'] == 0
    with pytest.raises(ValueError): benchmark([], lambda: None)
