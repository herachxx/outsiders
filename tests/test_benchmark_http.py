import json
import pytest

from scripts.benchmark_http import measure_http, require_loopback


@pytest.mark.parametrize('url', ['https://example.com', 'http://example.com', 'http://127.0.0.1:8000/other', 'http://localhost:8000?x=1'])
def test_http_benchmark_rejects_nonlocal_or_wrong_endpoint(url):
    with pytest.raises(ValueError):
        require_loopback(url)


def test_http_benchmark_counts_http_errors_without_payload(monkeypatch):
    import scripts.benchmark_http as module

    def fail(request, timeout):
        from urllib.error import HTTPError
        raise HTTPError(request.full_url, 503, 'PRIVATE text', None, None)

    monkeypatch.setattr(module, 'urlopen', fail)
    payload = json.dumps({'text': 'PRIVATE text'}).encode()
    result = measure_http([payload] * 3, require_loopback('http://127.0.0.1:8000'), 2)
    assert result['errors'] == {'http_503': 3}
    assert result['requests'] == 3
    assert not result['latency_limit_met']
    assert 'PRIVATE' not in str(result)
