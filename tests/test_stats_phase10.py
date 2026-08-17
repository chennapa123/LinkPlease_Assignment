from app.database import SessionLocal
from app.main import get_stats
from app.models import Delivery


def reset_db():
    db = SessionLocal()
    db.query(Delivery).delete()
    db.commit()
    db.close()


def test_stats_are_database_backed_and_restart_safe():
    reset_db()
    db = SessionLocal()
    db.add_all(
        [
            Delivery(rule_id=1, user_id="u1", comment_id="c1", message="m1", status="delivered"),
            Delivery(rule_id=1, user_id="u2", comment_id="c2", message="m2", status="delivered"),
            Delivery(rule_id=1, user_id="u3", comment_id="c3", message="m3", status="failed"),
            Delivery(rule_id=1, user_id="u4", comment_id="c4", message="m4", status="queued"),
            Delivery(rule_id=1, user_id="u5", comment_id="c5", message="m5", status="accepted"),
            Delivery(rule_id=1, user_id="u6", comment_id="c6", message="m6", status="cancelled"),
        ]
    )
    db.commit()
    db.close()

    stats = get_stats()
    assert stats == {"sent": 2, "failed": 1, "queued": 2, "duplicates_blocked": 0}
