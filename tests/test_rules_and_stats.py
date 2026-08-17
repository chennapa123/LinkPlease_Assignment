from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import Delivery, Rule

client = TestClient(app)


def reset_db():
    db = SessionLocal()
    db.query(Delivery).delete()
    db.query(Rule).delete()
    db.commit()
    db.close()


def test_create_rule():
    reset_db()
    payload = {"keyword": "PRICE", "dm_message": "Here is the price list."}

    response = client.post("/rules", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["keyword"] == "PRICE"
    assert data["dm_message"] == "Here is the price list."
    assert "rule_id" in data


def test_stats_empty():
    reset_db()
    response = client.get("/stats")

    assert response.status_code == 200
    assert response.json() == {
        "sent": 0,
        "failed": 0,
        "queued": 0,
        "duplicates_blocked": 0,
    }


def test_stats_counts_by_delivery_status():
    reset_db()
    db = SessionLocal()
    rule = Rule(keyword="PRICE", normalized_keyword="price", dm_message="Price list")
    db.add(rule)
    db.flush()

    db.add_all(
        [
            Delivery(rule_id=rule.id, user_id="u1", comment_id="c1", message="m1", status="delivered"),
            Delivery(rule_id=rule.id, user_id="u2", comment_id="c2", message="m2", status="failed"),
            Delivery(rule_id=rule.id, user_id="u3", comment_id="c3", message="m3", status="queued"),
            Delivery(rule_id=rule.id, user_id="u4", comment_id="c4", message="m4", status="sending"),
            Delivery(rule_id=rule.id, user_id="u5", comment_id="c5", message="m5", status="accepted"),
        ]
    )
    db.commit()
    db.close()

    response = client.get("/stats")

    assert response.status_code == 200
    assert response.json() == {
        "sent": 1,
        "failed": 1,
        "queued": 3,
        "duplicates_blocked": 0,
    }
