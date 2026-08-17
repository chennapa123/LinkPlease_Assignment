import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.database import SessionLocal
from app.main import app
from app.models import Event

client = TestClient(app)


def reset_events():
    db = SessionLocal()
    db.query(Event).delete()
    db.commit()
    db.close()


def build_valid_signature(payload: dict, api_key: str) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    digest = hmac.new(api_key.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def test_render_postgres_url_is_normalized_for_sqlalchemy():
    settings = Settings(database_url="postgresql://linkplease_user:pass@dpg-abc.postgres.render.com:5432/linkplease")
    assert settings.database_url == "postgresql+psycopg://linkplease_user:pass@dpg-abc.postgres.render.com:5432/linkplease"


def test_valid_webhook_is_accepted_and_persisted():
    reset_events()
    settings = get_settings()
    settings.pseudogram_api_key = "test-secret"

    payload = {
        "event_id": "evt_123",
        "event_type": "comment.created",
        "data": {"comment_id": "cmt_1", "post_id": "post_1", "text": "PRICE please", "from": {"user_id": "usr_1"}},
    }
    signature = build_valid_signature(payload, settings.pseudogram_api_key)

    response = client.post("/webhook", content=json.dumps(payload, separators=(",", ":")).encode("utf-8"), headers={"X-PseudoGram-Signature": signature})

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"

    db = SessionLocal()
    saved = db.query(Event).filter(Event.event_id == "evt_123").first()
    db.close()
    assert saved is not None


def test_forged_webhook_signature_is_rejected():
    reset_events()
    settings = get_settings()
    settings.pseudogram_api_key = "test-secret"

    payload = {"event_id": "evt_456", "event_type": "comment.created", "data": {"comment_id": "c1", "text": "PRICE", "from": {"user_id": "usr_2"}}}
    response = client.post(
        "/webhook",
        content=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers={"X-PseudoGram-Signature": "sha256=invalid"},
    )

    assert response.status_code == 401


def test_duplicate_event_id_is_not_double_stored():
    reset_events()
    settings = get_settings()
    settings.pseudogram_api_key = "test-secret"

    payload = {"event_id": "evt_dup", "event_type": "comment.created", "data": {"comment_id": "c1", "text": "PRICE", "from": {"user_id": "usr_2"}}}
    signature = build_valid_signature(payload, settings.pseudogram_api_key)

    first = client.post("/webhook", content=json.dumps(payload, separators=(",", ":")).encode("utf-8"), headers={"X-PseudoGram-Signature": signature})
    second = client.post("/webhook", content=json.dumps(payload, separators=(",", ":")).encode("utf-8"), headers={"X-PseudoGram-Signature": signature})

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate"

    db = SessionLocal()
    count = db.query(Event).filter(Event.event_id == "evt_dup").count()
    db.close()
    assert count == 1
