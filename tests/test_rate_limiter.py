import time

from app.services.rate_limiter import SlidingWindowRateLimiter


def test_rate_limiter_allows_up_to_ten_requests_in_window():
    limiter = SlidingWindowRateLimiter(limit=10, window_seconds=60)
    now = time.time()

    for _ in range(10):
        assert limiter.allow(now) is True

    assert limiter.allow(now) is False


def test_rate_limiter_releases_old_requests_after_window():
    limiter = SlidingWindowRateLimiter(limit=10, window_seconds=1)
    now = time.time()

    for _ in range(10):
        assert limiter.allow(now) is True

    assert limiter.allow(now + 1.1) is True
