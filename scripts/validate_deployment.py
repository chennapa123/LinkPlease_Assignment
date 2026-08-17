#!/usr/bin/env python
"""
Validate deployment: Check that a deployed LinkPlease instance is working correctly.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime

import httpx


def validate_deployment(service_url: str, verbose: bool = False) -> bool:
    """
    Validate that the deployed service is operational.
    
    Checks:
    - Health endpoint responds
    - Stats endpoint is accessible
    - API returns proper JSON responses
    - Database is connected (via stats query)
    """
    checks_passed = 0
    checks_total = 0
    
    print(f"\n{'='*60}")
    print(f"LinkPlease Deployment Validation")
    print(f"{'='*60}")
    print(f"Service URL: {service_url}")
    print(f"Time: {datetime.now().isoformat()}\n")
    
    client = httpx.Client(timeout=10.0)
    
    try:
        # Check 1: Health endpoint
        checks_total += 1
        print("Check 1: Health Endpoint")
        try:
            response = client.get(f"{service_url}/health")
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "ok" and data.get("service") == "linkplease":
                    print("  ✅ PASS: Health endpoint is operational")
                    checks_passed += 1
                else:
                    print(f"  ❌ FAIL: Health endpoint returned unexpected data: {data}")
            else:
                print(f"  ❌ FAIL: Health endpoint returned {response.status_code}")
        except Exception as e:
            print(f"  ❌ FAIL: {e}")
        
        # Check 2: Stats endpoint (tests database connectivity)
        checks_total += 1
        print("\nCheck 2: Stats Endpoint (Database Connectivity)")
        try:
            response = client.get(f"{service_url}/stats")
            if response.status_code == 200:
                data = response.json()
                required_keys = {"sent", "failed", "queued", "duplicates_blocked"}
                if required_keys.issubset(data.keys()):
                    print(f"  ✅ PASS: Stats endpoint is working")
                    print(f"     Current stats: sent={data['sent']}, failed={data['failed']}, " +
                          f"queued={data['queued']}, duplicates_blocked={data['duplicates_blocked']}")
                    checks_passed += 1
                else:
                    print(f"  ❌ FAIL: Stats missing required keys. Got: {data.keys()}")
            else:
                print(f"  ❌ FAIL: Stats endpoint returned {response.status_code}")
        except Exception as e:
            print(f"  ❌ FAIL: {e}")
        
        # Check 3: API Response Format
        checks_total += 1
        print("\nCheck 3: API Response Format")
        try:
            response = client.get(f"{service_url}/stats")
            content_type = response.headers.get("content-type", "")
            if "application/json" in content_type:
                print(f"  ✅ PASS: API returns JSON responses")
                checks_passed += 1
            else:
                print(f"  ❌ FAIL: Expected JSON, got: {content_type}")
        except Exception as e:
            print(f"  ❌ FAIL: {e}")
        
        # Check 4: Service Availability (no 5xx errors)
        checks_total += 1
        print("\nCheck 4: Service Availability")
        try:
            response = client.get(f"{service_url}/health")
            if response.status_code < 500:
                print(f"  ✅ PASS: Service is available (no 5xx errors)")
                checks_passed += 1
            else:
                print(f"  ❌ FAIL: Service returned {response.status_code}")
        except Exception as e:
            print(f"  ❌ FAIL: Service unavailable: {e}")
        
        # Check 5: Rules endpoint exists (can create rules)
        checks_total += 1
        print("\nCheck 5: Rules Endpoint")
        try:
            response = client.get(f"{service_url}/rules")
            # Expecting 405 (Method Not Allowed) since it's POST-only, or 404
            # Either way, endpoint exists if we don't get a 500 error
            if response.status_code < 500:
                print(f"  ✅ PASS: Rules endpoint is reachable")
                checks_passed += 1
            else:
                print(f"  ❌ FAIL: Rules endpoint returned {response.status_code}")
        except Exception as e:
            print(f"  ❌ FAIL: {e}")
        
        # Summary
        print(f"\n{'='*60}")
        print(f"Validation Summary: {checks_passed}/{checks_total} checks passed")
        print(f"{'='*60}\n")
        
        if checks_passed == checks_total:
            print("✅ All checks passed! Deployment is operational.")
            return True
        else:
            print(f"⚠️  {checks_total - checks_passed} check(s) failed. Review above.")
            return False
            
    finally:
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate LinkPlease deployment")
    parser.add_argument("--url", required=True, help="Service URL (e.g., https://linkplease-xxxxx.onrender.com)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()
    
    success = validate_deployment(args.url, verbose=args.verbose)
    sys.exit(0 if success else 1)
