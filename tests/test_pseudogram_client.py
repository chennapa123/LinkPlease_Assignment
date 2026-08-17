import httpx
import pytest

from app.services.pseudogram_client import PseudoGramClient, PseudoGramRateLimitError, PseudoGramRetryableError


class DummyResponse:
    def __init__(self, status_code, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}

    def json(self):
        return self._payload


def make_client(response_builder):
    transport = httpx.MockTransport(lambda request: response_builder(request))
    return PseudoGramClient(
        api_key="secret",
        base_url="https://example.test",
        timeout=5,
        client=httpx.Client(transport=transport),
    )


def test_send_dm_accepts_202_and_uses_idempotency_key():
    def response_builder(request):
        assert request.headers["X-API-Key"] == "secret"
        assert request.headers["Idempotency-Key"] == "delivery:test-123"
        assert request.url == "https://example.test/v1/dm/send"
        return httpx.Response(202, json={"dm_id": "dm_abc", "status": "queued"})

    client = make_client(response_builder)
    result = client.send_dm("usr_1", "hello", "cmt_1", "delivery:test-123")

    assert result == {"dm_id": "dm_abc", "status": "queued"}


def test_send_dm_raises_on_permanent_400():
    def response_builder(request):
        return httpx.Response(400, json={"error": "invalid_request", "detail": "bad payload"})

    client = make_client(response_builder)

    with pytest.raises(Exception):
        client.send_dm("usr_1", "hello", "cmt_1", "delivery:test-123")


def test_send_dm_raises_rate_limit_error_and_exposes_retry_after():
    def response_builder(request):
        return httpx.Response(429, json={"error": "rate_limited"}, headers={"Retry-After": "7"})

    client = make_client(response_builder)

    with pytest.raises(PseudoGramRateLimitError) as exc_info:
        client.send_dm("usr_1", "hello", "cmt_1", "delivery:test-123")

    assert exc_info.value.retry_after_seconds == 7


def test_send_dm_raises_retryable_error_for_500():
    def response_builder(request):
        return httpx.Response(500, json={"error": "internal_error"})

    client = make_client(response_builder)

    with pytest.raises(PseudoGramRetryableError):
        client.send_dm("usr_1", "hello", "cmt_1", "delivery:test-123")


def test_send_dm_handles_http_timeout():
    def response_builder(request):
        raise httpx.TimeoutException("timed out")

    client = make_client(response_builder)

    with pytest.raises(httpx.TimeoutException):
        client.send_dm("usr_1", "hello", "cmt_1", "delivery:test-123")


def test_get_dm_status_reads_status_field():
    def response_builder(request):
        assert request.url == "https://example.test/v1/dm/dm_123"
        return httpx.Response(200, json={"status": "delivered"})

    client = make_client(response_builder)
    assert client.get_dm_status("dm_123") == "delivered"
