from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.models import Delivery
from app.services.pseudogram_client import (
    PseudoGramPermanentError,
    PseudoGramRateLimitError,
    PseudoGramRetryableError,
)

settings = get_settings()


class DeliveryWorker:
    def __init__(self, client_stub: dict[str, Any] | None = None):
        self.client_stub = client_stub or {}

    @staticmethod
    def _normalize_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _get_client(self):
        if self.client_stub:
            return self.client_stub
        from app.services.pseudogram_client import PseudoGramClient

        return PseudoGramClient(
            api_key=settings.pseudogram_api_key,
            base_url=settings.pseudogram_base_url,
            timeout=10.0,
        )

    def _delivery_idempotency_key(self, delivery: Delivery) -> str:
        return f"delivery:{delivery.id}"

    def _schedule_retry(self, delivery: Delivery, *, retry_after_seconds: int | None = None) -> None:
        base_delay = retry_after_seconds if retry_after_seconds is not None else max(1, 2 ** max(delivery.attempts, 0))
        jitter = random.uniform(0.0, 1.0)
        delay_seconds = base_delay + jitter
        delivery.status = "queued"
        delivery.next_attempt_at = self._normalize_utc(datetime.now(timezone.utc) + timedelta(seconds=delay_seconds))

    def process_due_deliveries(self, limit: int = 10) -> int:
        db = SessionLocal()
        processed = 0
        try:
            rows = (
                db.execute(
                    select(Delivery)
                    .where(Delivery.status == "queued")
                    .where((Delivery.next_attempt_at.is_(None)) | (Delivery.next_attempt_at <= datetime.now(timezone.utc)))
                    .order_by(Delivery.created_at.asc())
                    .limit(limit)
                )
                .scalars()
                .all()
            )

            for delivery in rows:
                processed += 1
                delivery.status = "sending"
                delivery.attempts += 1
                db.add(delivery)
                db.commit()

                client = self._get_client()
                try:
                    result = client["send_dm"](
                        delivery.user_id,
                        delivery.message,
                        delivery.comment_id or "",
                        self._delivery_idempotency_key(delivery),
                    )
                    dm_id = result.get("dm_id") if isinstance(result, dict) else None
                    delivery.dm_id = dm_id
                    delivery.status = "accepted"
                    delivery.next_attempt_at = None
                    delivery.last_error = None
                    db.add(delivery)
                    db.commit()
                except PseudoGramPermanentError as exc:
                    delivery.status = "failed"
                    delivery.last_error = str(exc)
                    delivery.next_attempt_at = None
                    db.add(delivery)
                    db.commit()
                except PseudoGramRateLimitError as exc:
                    delivery.status = "queued"
                    delivery.last_error = str(exc)
                    retry_after = exc.retry_after_seconds
                    if retry_after is not None:
                        delivery.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=retry_after)
                    else:
                        self._schedule_retry(delivery)
                    db.add(delivery)
                    db.commit()
                except PseudoGramRetryableError as exc:
                    delivery.status = "queued"
                    delivery.last_error = str(exc)
                    self._schedule_retry(delivery)
                    db.add(delivery)
                    db.commit()
                except Exception as exc:
                    delivery.status = "queued"
                    delivery.last_error = str(exc)
                    self._schedule_retry(delivery)
                    db.add(delivery)
                    db.commit()
        finally:
            db.close()

        return processed
