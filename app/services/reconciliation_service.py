from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.models import Delivery

settings = get_settings()


class ReconciliationService:
    def __init__(self, client_stub: dict | None = None):
        self.client_stub = client_stub or {}

    def _get_client(self):
        if self.client_stub:
            return self.client_stub
        from app.services.pseudogram_client import PseudoGramClient

        return PseudoGramClient(
            api_key=settings.pseudogram_api_key,
            base_url=settings.pseudogram_base_url,
            timeout=10.0,
        )

    def reconcile_due(self, limit: int = 10) -> int:
        db = SessionLocal()
        processed = 0
        try:
            rows = (
                db.execute(
                    select(Delivery)
                    .where(Delivery.status == "accepted")
                    .where(Delivery.dm_id.is_not(None))
                    .order_by(Delivery.updated_at.asc())
                    .limit(limit)
                )
                .scalars()
                .all()
            )

            client = self._get_client()
            for delivery in rows:
                processed += 1
                status = client["get_dm_status"](delivery.dm_id)
                if status == "delivered":
                    delivery.status = "delivered"
                    delivery.next_attempt_at = None
                elif status == "failed":
                    if delivery.attempts < settings.max_retry_attempts:
                        delivery.status = "queued"
                        delivery.attempts += 1
                        delivery.next_attempt_at = datetime.now(timezone.utc)
                    else:
                        delivery.status = "failed"
                        delivery.next_attempt_at = None
                elif status == "queued":
                    delivery.status = "accepted"
                else:
                    delivery.status = "accepted"
                delivery.updated_at = datetime.now(timezone.utc)
                db.add(delivery)
                db.commit()
        finally:
            db.close()

        return processed
