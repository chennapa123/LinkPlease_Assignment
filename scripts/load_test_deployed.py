#!/usr/bin/env python
"""
Load test a deployed LinkPlease instance by sending simulated webhook events.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import random
import string
import sys
import time
from datetime import datetime

import httpx


def generate_event_id() -> str:
    """Generate a unique event ID."""
    return f"evt_{random.randint(100000, 999999)}"


def generate_comment_id() -> str:
    """Generate a unique comment ID."""
    return f"cmt_{random.randint(100000, 999999)}"


def generate_user_id() -> str:
    """Generate a random user ID."""
    return f"user_{''.join(random.choices(string.ascii_lowercase + string.digits, k=8))}"


def sign_payload(payload: dict, api_key: str) -> str:
    """Generate HMAC-SHA256 signature for payload."""
    raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    expected = hmac.new(
        api_key.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return f"sha256={expected}"


def create_comment_event(keyword: str, user_id: str | None = None, comment_id: str | None = None) -> dict:
    """Create a comment.created webhook event."""
    if not user_id:
        user_id = generate_user_id()
    if not comment_id:
        comment_id = generate_comment_id()
    
    comments = [
        f"I have a question about {keyword}",
        f"How do I find out about {keyword}?",
        f"Do you offer {keyword} options?",
        f"{keyword} is important to me",
        f"Tell me more about {keyword}",
    ]
    
    return {
        "event_id": generate_event_id(),
        "event_type": "comment.created",
        "data": {
            "comment_id": comment_id,
            "text": random.choice(comments),
            "from": {"user_id": user_id},
        },
    }


def send_webhook(service_url: str, event: dict, api_key: str) -> tuple[int, float]:
    """
    Send a webhook event to the deployed service.
    
    Returns: (status_code, response_time)
    """
    signature = sign_payload(event, api_key)
    
    client = httpx.Client(timeout=30.0)
    try:
        start = time.time()
        response = client.post(
            f"{service_url}/webhook",
            json=event,
            headers={"X-PseudoGram-Signature": signature},
        )
        elapsed = time.time() - start
        return response.status_code, elapsed
    finally:
        client.close()


def run_load_test(
    service_url: str,
    api_key: str,
    webhook_count: int = 100,
    duration_seconds: int = 30,
    keywords: list[str] | None = None,
) -> dict:
    """
    Run load test by sending webhook events to the deployed service.
    """
    if not keywords:
        keywords = ["PRICE", "BUDGET", "HELP"]
    
    print(f"\n{'='*70}")
    print(f"LinkPlease Load Test")
    print(f"{'='*70}")
    print(f"Service URL: {service_url}")
    print(f"Total Webhooks: {webhook_count}")
    print(f"Duration: {duration_seconds} seconds")
    print(f"Keywords: {', '.join(keywords)}")
    print(f"Start Time: {datetime.now().isoformat()}\n")
    
    results = {
        "total_sent": 0,
        "successful": 0,
        "failed": 0,
        "status_codes": {},
        "response_times": [],
        "errors": [],
    }
    
    interval = duration_seconds / webhook_count
    start_time = time.time()
    
    for i in range(webhook_count):
        keyword = random.choice(keywords)
        event = create_comment_event(keyword)
        
        try:
            status_code, response_time = send_webhook(service_url, event, api_key)
            results["total_sent"] += 1
            results["response_times"].append(response_time)
            
            if status_code == 200:
                results["successful"] += 1
            else:
                results["failed"] += 1
            
            results["status_codes"][status_code] = results["status_codes"].get(status_code, 0) + 1
            
            # Progress
            if (i + 1) % 10 == 0:
                elapsed = time.time() - start_time
                rate = (i + 1) / elapsed
                print(f"  [{i+1}/{webhook_count}] ({rate:.1f} req/s) Status {status_code}, {response_time*1000:.1f}ms")
            
            # Sleep to spread requests over duration
            time.sleep(interval)
            
        except Exception as e:
            results["failed"] += 1
            results["errors"].append(str(e))
            print(f"  ERROR on webhook {i+1}: {e}")
    
    # Calculate statistics
    total_time = time.time() - start_time
    if results["response_times"]:
        results["response_times"].sort()
        results["stats"] = {
            "total_time_seconds": round(total_time, 2),
            "throughput_per_second": round(webhook_count / total_time, 2),
            "avg_response_time_ms": round((sum(results["response_times"]) / len(results["response_times"])) * 1000, 2),
            "min_response_time_ms": round(min(results["response_times"]) * 1000, 2),
            "max_response_time_ms": round(max(results["response_times"]) * 1000, 2),
            "p50_response_time_ms": round(results["response_times"][len(results["response_times"]) // 2] * 1000, 2),
            "p95_response_time_ms": round(results["response_times"][int(len(results["response_times"]) * 0.95)] * 1000, 2),
            "p99_response_time_ms": round(results["response_times"][int(len(results["response_times"]) * 0.99)] * 1000, 2),
        }
    
    # Print summary
    print(f"\n{'='*70}")
    print(f"Load Test Results")
    print(f"{'='*70}")
    print(f"Total Sent: {results['total_sent']}")
    print(f"Successful (2xx): {results['successful']}")
    print(f"Failed: {results['failed']}")
    print(f"Success Rate: {(results['successful']/results['total_sent']*100):.1f}%")
    
    if results["status_codes"]:
        print(f"\nStatus Code Distribution:")
        for code in sorted(results["status_codes"].keys()):
            count = results["status_codes"][code]
            pct = (count / results["total_sent"]) * 100
            print(f"  {code}: {count} ({pct:.1f}%)")
    
    if "stats" in results:
        print(f"\nResponse Time Metrics:")
        print(f"  Throughput: {results['stats']['throughput_per_second']} req/s")
        print(f"  Min: {results['stats']['min_response_time_ms']:.1f}ms")
        print(f"  Avg: {results['stats']['avg_response_time_ms']:.1f}ms")
        print(f"  P50: {results['stats']['p50_response_time_ms']:.1f}ms")
        print(f"  P95: {results['stats']['p95_response_time_ms']:.1f}ms")
        print(f"  P99: {results['stats']['p99_response_time_ms']:.1f}ms")
        print(f"  Max: {results['stats']['max_response_time_ms']:.1f}ms")
    
    print(f"\nEnd Time: {datetime.now().isoformat()}")
    print(f"{'='*70}\n")
    
    # Check stats after load test
    print("Checking deployed stats after load test...")
    time.sleep(2)  # Give service time to process
    
    client = httpx.Client(timeout=10.0)
    try:
        response = client.get(f"{service_url}/stats")
        if response.status_code == 200:
            stats = response.json()
            print(f"Deployed Service Stats:")
            print(f"  Sent: {stats['sent']}")
            print(f"  Failed: {stats['failed']}")
            print(f"  Queued: {stats['queued']}")
            print(f"  Duplicates Blocked: {stats['duplicates_blocked']}")
            results["deployed_stats"] = stats
    except Exception as e:
        print(f"  Could not fetch stats: {e}")
    finally:
        client.close()
    
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load test a deployed LinkPlease instance")
    parser.add_argument("--url", required=True, help="Service URL")
    parser.add_argument("--api-key", required=True, help="PseudoGram API key for signing")
    parser.add_argument("--webhook-count", type=int, default=100, help="Number of webhooks to send")
    parser.add_argument("--duration-seconds", type=int, default=30, help="Duration over which to spread requests")
    parser.add_argument("--keywords", nargs="+", default=["PRICE", "BUDGET", "HELP"], help="Keywords to use in test")
    args = parser.parse_args()
    
    results = run_load_test(
        service_url=args.url,
        api_key=args.api_key,
        webhook_count=args.webhook_count,
        duration_seconds=args.duration_seconds,
        keywords=args.keywords,
    )
    
    # Exit with success if all webhooks were sent
    sys.exit(0 if results["total_sent"] == args.webhook_count else 1)
