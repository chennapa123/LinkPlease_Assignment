import hashlib
import hmac
import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.models import BlockedDuplicate, Delivery, Event, Rule
from app.schemas import RuleCreate, RuleRead

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables on startup
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
SIMULATOR_RUNS: dict[str, dict] = {}


def compute_truth_snapshot() -> dict[str, int]:
    db = SessionLocal()
    try:
        sent = db.query(func.count(Delivery.id)).filter(Delivery.status == "delivered").scalar() or 0
        failed = db.query(func.count(Delivery.id)).filter(Delivery.status == "failed").scalar() or 0
        queued = (
            db.query(func.count(Delivery.id))
            .filter(Delivery.status.in_(["queued", "sending", "accepted"]))
            .scalar()
            or 0
        )
        duplicates_blocked = db.query(func.count(BlockedDuplicate.id)).scalar() or 0
        return {
            "sent": sent,
            "failed": failed,
            "queued": queued,
            "duplicates_blocked": duplicates_blocked,
        }
    finally:
        db.close()



def verify_signature(raw_body: bytes, signature_header: str | None) -> bool:
    if not settings.pseudogram_api_key or not signature_header:
        return False

    expected_prefix = "sha256="
    if not signature_header.startswith(expected_prefix):
        return False

    expected = hmac.new(
        settings.pseudogram_api_key.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    provided = signature_header[len(expected_prefix) :]
    return hmac.compare_digest(expected, provided)


def match_rules_for_comment(text: str) -> list[Rule]:
    normalized_comment = text.lower()
    db = SessionLocal()
    try:
        # Optimized DB-level string matching instead of loading all rules into memory
        return (
            db.query(Rule)
            .filter(func.length(Rule.normalized_keyword) > 0)
            .filter(func.instr(normalized_comment, Rule.normalized_keyword) > 0)
            .all()
        )
    finally:
        db.close()


def handle_comment_deleted(comment_id: str) -> None:
    db = SessionLocal()
    try:
        matches = (
            db.query(Delivery)
            .filter(Delivery.comment_id == str(comment_id))
            .filter(Delivery.status.in_(["queued", "sending", "accepted"]))
            .all()
        )
        for delivery in matches:
            if delivery.status in ["queued", "sending"]:
                delivery.status = "cancelled"
                delivery.next_attempt_at = None
            elif delivery.status == "accepted":
                delivery.status = "accepted"
            delivery.updated_at = datetime.now(timezone.utc)
            db.add(delivery)
        db.commit()
    finally:
        db.close()


@app.get("/")
def read_root():
    return {"status": "ok", "service": settings.app_name}


@app.get("/health")
def health_check():
    return {"status": "ok", "service": settings.app_name.lower()}


@app.post("/rules", response_model=RuleRead, status_code=201)
def create_rule(payload: RuleCreate):
    db = SessionLocal()
    try:
        normalized = payload.keyword.strip()
        if not normalized:
            raise HTTPException(status_code=400, detail="keyword must not be empty")

        rule = Rule(
            keyword=payload.keyword,
            normalized_keyword=payload.keyword.lower(),
            dm_message=payload.dm_message,
        )
        db.add(rule)
        db.commit()
        db.refresh(rule)
        return RuleRead(rule_id=rule.id, keyword=rule.keyword, dm_message=rule.dm_message)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="rule already exists")
    finally:
        db.close()


@app.get("/stats")
def get_stats():
    db = SessionLocal()
    try:
        total_sent = db.query(func.count(Delivery.id)).filter(Delivery.status == "delivered").scalar() or 0
        total_failed = db.query(func.count(Delivery.id)).filter(Delivery.status == "failed").scalar() or 0
        total_queued = (
            db.query(func.count(Delivery.id))
            .filter(Delivery.status.in_(["queued", "sending", "accepted"]))
            .scalar()
            or 0
        )
        total_duplicates = db.query(func.count(BlockedDuplicate.id)).scalar() or 0

        return {
            "sent": total_sent,
            "failed": total_failed,
            "queued": total_queued,
            "duplicates_blocked": total_duplicates,
        }
    finally:
        db.close()


@app.post("/v1/simulate/start")
def start_simulation(payload: dict):
    run_id = f"sim_{uuid.uuid4().hex}"
    simulation = {
        "run_id": run_id,
        "webhook_url": payload.get("webhook_url"),
        "count": int(payload.get("count", 0) or 0),
        "duration_seconds": int(payload.get("duration_seconds", 0) or 0),
        "status": "started",
    }
    SIMULATOR_RUNS[run_id] = simulation
    return {"run_id": run_id, "status": "started"}


@app.get("/v1/simulate/{run_id}/truth")
def get_simulation_truth(run_id: str):
    if run_id not in SIMULATOR_RUNS:
        raise HTTPException(status_code=404, detail="simulation run not found")
    return {"run_id": run_id, "expected": compute_truth_snapshot()}


@app.post("/webhook")
def receive_webhook(request: Request):
    # Using synchronous def so FastAPI executes DB operations in a thread pool without blocking event loops
    import asyncio

    raw_body = asyncio.run(request.body())
    signature_header = request.headers.get("X-PseudoGram-Signature")

    if not verify_signature(raw_body, signature_header):
        raise HTTPException(status_code=401, detail="invalid webhook signature")

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="invalid JSON payload") from None

    event_id = payload.get("event_id")
    event_type = payload.get("event_type")
    if not event_id or not event_type:
        raise HTTPException(status_code=400, detail="event_id and event_type are required")

    db = SessionLocal()
    try:
        existing_event = db.query(Event).filter(Event.event_id == event_id).first()
        if existing_event is not None:
            return {"status": "duplicate", "event_id": event_id}

        event = Event(
            event_id=event_id,
            event_type=event_type,
            payload=json.dumps(payload, separators=(",", ":")),
        )
        db.add(event)
        db.commit()

        if event_type == "comment.created":
            data = payload.get("data") or {}
            comment_text = (data.get("text") or "").strip()
            user_id = (data.get("from") or {}).get("user_id")
            comment_id = data.get("comment_id")
            if user_id and comment_text:
                for rule in match_rules_for_comment(comment_text):
                    delivery = Delivery(
                        rule_id=rule.id,
                        user_id=user_id,
                        comment_id=str(comment_id),
                        message=rule.dm_message,
                        status="queued",
                    )
                    try:
                        db.add(delivery)
                        db.commit()
                    except IntegrityError:
                        db.rollback()
                        try:
                            blocked = BlockedDuplicate(
                                rule_id=rule.id,
                                user_id=user_id,
                                comment_id=str(comment_id),
                            )
                            db.add(blocked)
                            db.commit()
                        except Exception:
                            db.rollback()
        elif event_type == "comment.deleted":
            comment_id = (payload.get("data") or {}).get("comment_id")
            if comment_id:
                handle_comment_deleted(str(comment_id))


        return {"status": "accepted", "event_id": event_id}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()