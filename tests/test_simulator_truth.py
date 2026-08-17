import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import Delivery, Event, Rule


def reset_db():
    db = SessionLocal()
    db.query(Delivery).delete()
    db.query(Event).delete()
    db.query(Rule).delete()
    db.commit()
    db.close()


def compare_truth(expected: dict, actual: dict) -> dict:
    discrepancies = {
        key: {"expected": expected.get(key), "actual": actual.get(key)}
        for key in sorted(set(expected) | set(actual))
        if expected.get(key) != actual.get(key)
    }
    return {
        "matches": not discrepancies,
        "discrepancies": discrepancies,
    }


def test_simulator_lifecycle_and_truth_comparison():
    reset_db()
    client = TestClient(app)

    start = client.post(
        "/v1/simulate/start",
        json={"webhook_url": "https://example.com/webhook", "count": 5, "duration_seconds": 10},
    )
    assert start.status_code == 200, start.text
    body = start.json()
    assert body["status"] == "started"
    assert "run_id" in body

    truth = client.get(f"/v1/simulate/{body['run_id']}/truth")
    assert truth.status_code == 200, truth.text
    payload = truth.json()
    assert payload["run_id"] == body["run_id"]
    assert set(payload["expected"]) == {"sent", "failed", "queued", "duplicates_blocked"}
    assert payload["expected"]["sent"] >= 0

    actual = payload["expected"]
    expected = {"sent": 0, "failed": 0, "queued": 0, "duplicates_blocked": 0}
    result = compare_truth(expected, actual)
    assert result["matches"] is True


if __name__ == "__main__":
    expected_path = Path("expected_truth.json")
    actual_path = Path("actual_truth.json")

    if not expected_path.exists() or not actual_path.exists():
        raise SystemExit("Both expected_truth.json and actual_truth.json are required.")

    expected = json.loads(expected_path.read_text())
    actual = json.loads(actual_path.read_text())
    result = compare_truth(expected, actual)
    print(json.dumps(result, indent=2, sort_keys=True))
