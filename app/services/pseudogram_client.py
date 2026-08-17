from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


class PseudoGramClientError(Exception):
    pass


class PseudoGramPermanentError(PseudoGramClientError):
    pass


class PseudoGramRetryableError(PseudoGramClientError):
    pass


class PseudoGramRateLimitError(PseudoGramRetryableError):
    def __init__(self, message: str, retry_after_seconds: int | None = None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


@dataclass
class PseudoGramClient:
    api_key: str
    base_url: str
    timeout: float = 10.0
    client: httpx.Client | None = None

    def _client_instance(self) -> httpx.Client:
        if self.client is not None:
            return self.client
        return httpx.Client(base_url=self.base_url, timeout=self.timeout)

    def _absolute_url(self, path: str) -> str:
        return f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"

    def send_dm(self, recipient_user_id: str, message: str, comment_id: str, idempotency_key: str) -> dict[str, Any]:
        payload = {
            "recipient_user_id": recipient_user_id,
            "message": message,
            "comment_id": comment_id,
        }

        client = self._client_instance()
        try:
            response = client.post(
                self._absolute_url("/v1/dm/send"),
                json=payload,
                headers={
                    "X-API-Key": self.api_key,
                    "Idempotency-Key": idempotency_key,
                },
            )
        finally:
            if self.client is None:
                client.close()

        if response.status_code == 202:
            return response.json()

        if response.status_code == 400:
            raise PseudoGramPermanentError((response.json() or {}).get("detail") or "bad request")

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            try:
                retry_after_seconds = int(retry_after) if retry_after is not None else None
            except ValueError:
                retry_after_seconds = None
            raise PseudoGramRateLimitError("rate limited", retry_after_seconds)

        if response.status_code == 500:
            raise PseudoGramRetryableError("internal_error")

        raise PseudoGramClientError(f"unexpected status code: {response.status_code}")

    def get_dm_status(self, dm_id: str) -> str:
        client = self._client_instance()
        try:
            response = client.get(self._absolute_url(f"/v1/dm/{dm_id}"), headers={"X-API-Key": self.api_key})
        finally:
            if self.client is None:
                client.close()

        if response.status_code != 200:
            raise PseudoGramClientError(f"status fetch failed: {response.status_code}")

        data = response.json()
        return data.get("status")
