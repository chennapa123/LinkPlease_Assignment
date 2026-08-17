from datetime import datetime, timezone

from app.database import SessionLocal
from app.models import Delivery, Rule
from app.main import handle_comment_deleted


def reset_db():
    db = SessionLocal()
    db.query(Delivery).delete()
    db.query(Rule).delete()
    db.commit()
    db.close()


def test_comment_deleted_cancels_queued_delivery_only():
    reset_db()
    db = SessionLocal()
    rule = Rule(keyword="PRICE", normalized_keyword="price", dm_message="Price list")
    db.add(rule)
    db.commit()
    db.refresh(rule)

    queued = Delivery(
        rule_id=rule.id,
        user_id="usr_del_1",
        comment_id="cmt_del_1",
        message="Price list",
        status="queued",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    accepted = Delivery(
        rule_id=rule.id,
        user_id="usr_del_2",
        comment_id="cmt_del_2",
        message="Price list",
        status="accepted",
        dm_id="dm_del_2",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add_all([queued, accepted])
    db.commit()
    db.refresh(queued)
    db.refresh(accepted)
    db.close()

    handle_comment_deleted("cmt_del_1")
    handle_comment_deleted("cmt_del_2")

    db = SessionLocal()
    queued_after = db.query(Delivery).filter(Delivery.id == queued.id).one()
    accepted_after = db.query(Delivery).filter(Delivery.id == accepted.id).one()
    assert queued_after.status == "cancelled"
    assert accepted_after.status == "accepted"
    db.close()
