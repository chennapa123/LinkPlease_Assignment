#!/usr/bin/env python
"""
Compare actual deployed stats against expected values to validate correctness.
"""
from __future__ import annotations

import argparse
import sys

import httpx


def compare_truth(
    service_url: str,
    expected_sent: int | None = None,
    expected_failed: int | None = None,
    expected_queued: int | None = None,
    expected_duplicates: int | None = None,
) -> bool:
    """
    Compare actual stats from deployed service against expected values.
    """
    print(f"\n{'='*70}")
    print(f"Truth Comparison")
    print(f"{'='*70}")
    print(f"Service URL: {service_url}\n")
    
    # Fetch actual stats
    client = httpx.Client(timeout=10.0)
    try:
        response = client.get(f"{service_url}/stats")
        if response.status_code != 200:
            print(f"❌ Failed to fetch stats: HTTP {response.status_code}")
            return False
        
        actual = response.json()
    except Exception as e:
        print(f"❌ Error fetching stats: {e}")
        return False
    finally:
        client.close()
    
    print(f"Actual Stats (from {service_url}/stats):")
    print(f"  sent: {actual['sent']}")
    print(f"  failed: {actual['failed']}")
    print(f"  queued: {actual['queued']}")
    print(f"  duplicates_blocked: {actual['duplicates_blocked']}")
    print()
    
    # Compare each metric
    all_match = True
    results = []
    
    if expected_sent is not None:
        match = actual["sent"] == expected_sent
        status = "✅" if match else "❌"
        results.append((status, f"sent: {actual['sent']} (expected {expected_sent})"))
        all_match = all_match and match
    
    if expected_failed is not None:
        match = actual["failed"] == expected_failed
        status = "✅" if match else "❌"
        results.append((status, f"failed: {actual['failed']} (expected {expected_failed})"))
        all_match = all_match and match
    
    if expected_queued is not None:
        match = actual["queued"] == expected_queued
        status = "✅" if match else "❌"
        results.append((status, f"queued: {actual['queued']} (expected {expected_queued})"))
        all_match = all_match and match
    
    if expected_duplicates is not None:
        match = actual["duplicates_blocked"] == expected_duplicates
        status = "✅" if match else "❌"
        results.append((status, f"duplicates_blocked: {actual['duplicates_blocked']} (expected {expected_duplicates})"))
        all_match = all_match and match
    
    # If no expectations provided, just report
    if not results:
        print("No expectations provided. Current stats shown above.")
        print("Use --expected-sent, --expected-failed, --expected-queued, --expected-duplicates to specify expectations.")
        return True
    
    # Print results
    print("Comparison Results:")
    for status, message in results:
        print(f"  {status} {message}")
    
    print(f"\n{'='*70}")
    if all_match:
        print("✅ All metrics match expectations!")
    else:
        print("❌ Some metrics do not match expectations.")
    print(f"{'='*70}\n")
    
    return all_match


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compare deployed stats against expected values")
    parser.add_argument("--url", required=True, help="Service URL (e.g., https://linkplease-xxxxx.onrender.com)")
    parser.add_argument("--deployed-url", dest="url", help="Alias for --url")
    parser.add_argument("--expected-sent", type=int, help="Expected number of sent deliveries")
    parser.add_argument("--expected-failed", type=int, help="Expected number of failed deliveries")
    parser.add_argument("--expected-queued", type=int, help="Expected number of queued deliveries")
    parser.add_argument("--expected-duplicates", type=int, help="Expected number of duplicates blocked")
    args = parser.parse_args()
    
    success = compare_truth(
        service_url=args.url,
        expected_sent=args.expected_sent,
        expected_failed=args.expected_failed,
        expected_queued=args.expected_queued,
        expected_duplicates=args.expected_duplicates,
    )
    
    sys.exit(0 if success else 1)
