#!/usr/bin/env python
"""
Submit LinkPlease assignment results to PseudoGram endpoint.
"""
from __future__ import annotations

import argparse
import json
import sys

import httpx


DEFAULT_SUBMISSION_URL = "https://pseudogram-api.onrender.com/v1/submit"


def prepare_submission(
    email: str | None,
    api_key: str | None,
    github_repo: str,
    working_url: str,
    loom_url: str,
    parts_completed: str = "A+B+C",
    start_date: str = "2026-08-17",
) -> dict:
    """Prepare official submission payload."""
    payload = {
        "github_repo": github_repo,
        "working_url": working_url,
        "loom_url": loom_url,
        "parts_completed": parts_completed,
        "start_date": start_date,
    }
    if email:
        payload["email"] = email
    if api_key:
        payload["api_key"] = api_key

    return payload


def submit_assignment(
    submission_url: str,
    payload: dict,
    retry_count: int = 3,
) -> bool:

    print(f"\n{'='*70}")
    print("LinkPlease Assignment Submission")
    print(f"{'='*70}")
    print(f"Submission URL: {submission_url}")
    print(f"Working URL:    {payload.get('working_url')}")
    print(f"GitHub Repo:    {payload.get('github_repo')}\n")

    print("Submission Payload:")
    print(json.dumps(payload, indent=2))
    print()

    client = httpx.Client(timeout=30.0)

    for attempt in range(1, retry_count + 1):
        try:
            print(f"Attempt {attempt}/{retry_count}: Submitting...")

            response = client.post(
                submission_url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )

            print(f"Response Status: {response.status_code}")

            try:
                response_data = response.json()
                print(f"Response Body:")
                print(json.dumps(response_data, indent=2))
            except Exception:
                print(f"Response Body: {response.text}")

            if response.status_code in [200, 201, 202]:
                print("\n✅ Submission successful!")
                client.close()
                return True
            elif response.status_code in [400, 401, 403]:
                print("\n❌ Submission rejected (client error)")
                client.close()
                return False
            elif response.status_code >= 500:
                if attempt < retry_count:
                    print("⚠️  Server error, retrying in 5 seconds...")
                    import time

                    time.sleep(5)
                    continue
                else:
                    print(f"\n❌ Server error after {retry_count} attempts")
                    client.close()
                    return False
            else:
                print(f"\n⚠️  Unexpected status code: {response.status_code}")
                if attempt < retry_count:
                    print("Retrying...")
                    continue
                else:
                    client.close()
                    return False

        except Exception as e:
            print(f"❌ Error: {e}")
            if attempt < retry_count:
                print("Retrying in 5 seconds...")
                import time

                time.sleep(5)
                continue
            else:
                print(f"Failed after {retry_count} attempts")
                client.close()
                return False

    client.close()
    return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Submit LinkPlease assignment")
    parser.add_argument("--submission-url", default=DEFAULT_SUBMISSION_URL, help="PseudoGram submission endpoint URL")
    parser.add_argument("--email", help="Your email address")
    parser.add_argument("--api-key", help="Your PseudoGram API key (if email not provided)")
    parser.add_argument("--github-repo", required=True, help="Public GitHub repository URL")
    parser.add_argument("--working-url", required=True, help="Deployed base URL")
    parser.add_argument("--loom-url", required=True, help="3-minute Loom video URL")
    parser.add_argument("--parts-completed", default="A+B+C", help="Parts completed (A, A+B, or A+B+C)")
    parser.add_argument("--start-date", default="2026-08-17", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--retry", type=int, default=3, help="Number of retries")
    parser.add_argument("--dry-run", action="store_true", help="Prepare payload without submitting")
    args = parser.parse_args()

    if not args.email and not args.api_key:
        print("Error: Either --email or --api-key must be provided.")
        sys.exit(1)

    payload = prepare_submission(
        email=args.email,
        api_key=args.api_key,
        github_repo=args.github_repo,
        working_url=args.working_url,
        loom_url=args.loom_url,
        parts_completed=args.parts_completed,
        start_date=args.start_date,
    )

    if args.dry_run:
        print("\nDry run - payload prepared but not submitted:")
        print(json.dumps(payload, indent=2))
        sys.exit(0)

    success = submit_assignment(
        submission_url=args.submission_url,
        payload=payload,
        retry_count=args.retry,
    )

    print(f"\n{'='*70}\n")
    sys.exit(0 if success else 1)

