import threading
import time
from collections import deque


class SlidingWindowRateLimiter:
    def __init__(self, limit: int, window_seconds: int):
        self.limit = limit
        self.window_seconds = window_seconds
        self._lock = threading.Lock()
        self._timestamps: deque[float] = deque()

    def allow(self, now: float | None = None) -> bool:
        if now is None:
            now = time.time()

        cutoff = now - self.window_seconds
        with self._lock:
            while self._timestamps and self._timestamps[0] <= cutoff:
                self._timestamps.popleft()

            if len(self._timestamps) >= self.limit:
                return False

            self._timestamps.append(now)
            return True
