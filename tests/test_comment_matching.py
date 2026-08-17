import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from app.config import get_settings
from app.database import SessionLocal
from app.main import app
from app.models import Delivery, Event, Rule

client = TestClient(app)


def reset_db():
    db = SessionLocal()
    db.query(Delivery).delete()
    db.query(Event).delete()
    db.query(Rule).delete()
    db.commit()
    db.close()


def valid_signature(payload: dict, api_key: str) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    digest = hmac.new(api_key.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def create_rule(keyword: str = "PRICE", message: str = "Here is the price list."):
    return client.post("/rules", json={"keyword": keyword, "dm_message": message})


def test_exact_keyword_match_creates_delivery():
    reset_db()
    settings = get_settings()
    settings.pseudogram_api_key = "test-secret"

    create_rule()
    payload = {
        "event_id": "evt_1",
        "event_type": "comment.created",
        "data": {
            "comment_id": "cmt_1",
            "text": "PRICE please 🙏",
            "from": {"user_id": "usr_1"},
        },
    }

    response = client.post(
        "/webhook",
        content=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers={"X-PseudoGram-Signature": valid_signature(payload, settings.pseudogram_api_key)},
    )

    assert response.status_code == 200
    db = SessionLocal()
    count = db.query(Delivery).count()
    row = db.query(Delivery).first()
    db.close()
    assert count == 1
    assert row.user_id == "usr_1"
    assert row.rule_id == 1


def test_case_insensitive_and_substring_match():
    reset_db()
    settings = get_settings()
    settings.pseudogram_api_key = "test-secret"
    create_rule(keyword="price")

    payload = {
        "event_id": "evt_2",
        "event_type": "comment.created",
        "data": {
            "comment_id": "cmt_2",
            "text": "I need the PRICE list for this product",
            "from": {"user_id": "usr_2"},
        },
    }

    response = client.post(
        "/webhook",
        content=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers={"X-PseudoGram-Signature": valid_signature(payload, settings.pseudogram_api_key)},
    )

    assert response.status_code == 200
    db = SessionLocal()
    try:
        assert db.query(Delivery).count() == 1
    finally:
        db.close()


def test_same_user_same_rule_only_creates_one_delivery():
    reset_db()
    settings = get_settings()
    settings.pseudogram_api_key = "test-secret"
    create_rule(keyword="PRICE")

    for i in range(2):
        payload = {
            "event_id": f"evt_same_{i}",
            "event_type": "comment.created",
            "data": {
                "comment_id": f"cmt_same_{i}",
                "text": "PRICE please",
                "from": {"user_id": "usr_3"},
            },
        }
        client.post(
            "/webhook",
            content=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers={"X-PseudoGram-Signature": valid_signature(payload, settings.pseudogram_api_key)},
        )

    db = SessionLocal()
    try:
        assert db.query(Delivery).count() == 1
        assert db.query(Delivery).first().user_id == "usr_3"
    finally:
        db.close()


def test_two_rules_same_user_creates_two_deliveries():
    reset_db()
    settings = get_settings()
    settings.pseudogram_api_key = "test-secret"
    create_rule(keyword="PRICE")
    create_rule(keyword="BUDGET")

    payload = {
        "event_id": "evt_multi",
        "event_type": "comment.created",
        "data": {
            "comment_id": "cmt_multi",
            "text": "Can I get the price and budget details?",
            "from": {"user_id": "usr_4"},
        },
    }

    response = client.post(
        "/webhook",
        content=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers={"X-PseudoGram-Signature": valid_signature(payload, settings.pseudogram_api_key)},
    )

    assert response.status_code == 200
    db = SessionLocal()
    try:
        assert db.query(Delivery).count() == 2
    finally:
        db.close()
