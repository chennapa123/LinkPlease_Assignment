from datetime import datetime, timezone

from app.database import SessionLocal
from app.models import Delivery, Rule
from app.services.reconciliation_service import ReconciliationService


def reset_db():
    db = SessionLocal()
    db.query(Delivery).delete()
    db.query(Rule).delete()
    db.commit()
    db.close()


def test_reconciliation_marks_accepted_as_delivered():
    reset_db()
    db = SessionLocal()
    rule = Rule(keyword="PRICE", normalized_keyword="price", dm_message="Price list")
    db.add(rule)
    db.commit()
    db.refresh(rule)

    delivery = Delivery(
        rule_id=rule.id,
        user_id="usr_r1",
        comment_id="cmt_r1",
        message="Price list",
        status="accepted",
        dm_id="dm_r1",
        attempts=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(delivery)
    db.commit()
    db.refresh(delivery)
    db.close()

    service = ReconciliationService(client_stub={"get_dm_status": lambda dm_id: "delivered"})
    count = service.reconcile_due(limit=10)

    assert count == 1
    db = SessionLocal()
    updated = db.query(Delivery).filter(Delivery.id == delivery.id).one()
    assert updated.status == "delivered"
    db.close()


def test_reconciliation_requeues_failed_status_when_retry_attempts_remain():
    reset_db()
    db = SessionLocal()
    rule = Rule(keyword="PRICE", normalized_keyword="price", dm_message="Price list")
    db.add(rule)
    db.commit()
    db.refresh(rule)

    delivery = Delivery(
        rule_id=rule.id,
        user_id="usr_r2",
        comment_id="cmt_r2",
        message="Price list",
        status="accepted",
        dm_id="dm_r2",
        attempts=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(delivery)
    db.commit()
    db.refresh(delivery)
    db.close()

    service = ReconciliationService(client_stub={"get_dm_status": lambda dm_id: "failed"})
    count = service.reconcile_due(limit=10)

    assert count == 1
    db = SessionLocal()
    updated = db.query(Delivery).filter(Delivery.id == delivery.id).one()
    assert updated.status == "queued"
    assert updated.attempts == 2
    db.close()
