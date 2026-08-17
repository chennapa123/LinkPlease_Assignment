from datetime import datetime, timedelta, timezone

from app.database import SessionLocal
from app.models import Delivery, Rule
from app.services.delivery_worker import DeliveryWorker
from app.services.pseudogram_client import PseudoGramRetryableError


def reset_db():
    db = SessionLocal()
    db.query(Delivery).delete()
    db.query(Rule).delete()
    db.commit()
    db.close()


def test_worker_marks_accepted_when_upstream_202_is_returned():
    reset_db()
    db = SessionLocal()
    rule = Rule(keyword="PRICE", normalized_keyword="price", dm_message="Price list")
    db.add(rule)
    db.commit()
    db.refresh(rule)

    delivery = Delivery(
        rule_id=rule.id,
        user_id="usr_worker_1",
        comment_id="cmt_worker_1",
        message="Price list",
        status="queued",
        attempts=0,
        next_attempt_at=datetime.now(timezone.utc),
    )
    db.add(delivery)
    db.commit()
    db.refresh(delivery)
    db.close()

    worker = DeliveryWorker(client_stub={"send_dm": lambda *args, **kwargs: {"dm_id": "dm_123", "status": "queued"}})
    processed = worker.process_due_deliveries(limit=10)

    assert processed == 1
    db = SessionLocal()
    updated = db.query(Delivery).filter(Delivery.id == delivery.id).one()
    assert updated.status == "accepted"
    assert updated.dm_id == "dm_123"
    assert updated.attempts == 1
    db.close()


def test_worker_requeues_and_backs_off_on_retryable_error():
    reset_db()
    db = SessionLocal()
    rule = Rule(keyword="PRICE", normalized_keyword="price", dm_message="Price list")
    db.add(rule)
    db.commit()
    db.refresh(rule)

    delivery = Delivery(
        rule_id=rule.id,
        user_id="usr_worker_2",
        comment_id="cmt_worker_2",
        message="Price list",
        status="queued",
        attempts=0,
        next_attempt_at=datetime.now(timezone.utc),
    )
    db.add(delivery)
    db.commit()
    db.refresh(delivery)
    db.close()

    def boom(*args, **kwargs):
        raise PseudoGramRetryableError("internal_error")

    worker = DeliveryWorker(client_stub={"send_dm": boom})
    processed = worker.process_due_deliveries(limit=10)

    assert processed == 1
    db = SessionLocal()
    updated = db.query(Delivery).filter(Delivery.id == delivery.id).one()
    assert updated.status == "queued"
    assert updated.attempts == 1
    assert updated.next_attempt_at is not None
    candidate = updated.next_attempt_at
    if candidate.tzinfo is None:
        candidate = candidate.replace(tzinfo=timezone.utc)
    assert candidate > datetime.now(timezone.utc)
    db.close()
