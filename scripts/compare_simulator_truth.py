from __future__ import annotations

import json
from pathlib import Path


def compare_truth(expected: dict, actual: dict) -> dict:
    discrepancies = {key: {"expected": expected.get(key), "actual": actual.get(key)} for key in sorted(set(expected) | set(actual)) if expected.get(key) != actual.get(key)}
    return {
        "matches": not discrepancies,
        "discrepancies": discrepancies,
    }


if __name__ == "__main__":
    expected_path = Path("expected_truth.json")
    actual_path = Path("actual_truth.json")

    if not expected_path.exists() or not actual_path.exists():
        raise SystemExit("Both expected_truth.json and actual_truth.json are required.")

    expected = json.loads(expected_path.read_text())
    actual = json.loads(actual_path.read_text())
    result = compare_truth(expected, actual)
    print(json.dumps(result, indent=2, sort_keys=True))
