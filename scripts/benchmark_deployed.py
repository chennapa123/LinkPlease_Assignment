#!/usr/bin/env python
"""
Benchmark a deployed LinkPlease instance to measure performance.
"""
from __future__ import annotations

import argparse
import json
import sys
import time

import httpx


def benchmark_endpoint(
    client: httpx.Client,
    method: str,
    url: str,
    iterations: int = 10,
    payload: dict | None = None,
    headers: dict | None = None,
) -> dict:
    """
    Benchmark a single endpoint.
    
    Returns dict with timing statistics.
    """
    times = []
    errors = 0
    
    for _ in range(iterations):
        try:
            start = time.time()
            if method == "GET":
                response = client.get(url, headers=headers)
            elif method == "POST":
                response = client.post(url, json=payload, headers=headers)
            else:
                raise ValueError(f"Unsupported method: {method}")
            elapsed = time.time() - start
            
            if response.status_code < 500:  # Don't count server errors in timing
                times.append(elapsed)
            else:
                errors += 1
        except Exception:
            errors += 1
    
    if not times:
        return {
            "method": method,
            "url": url,
            "errors": errors,
            "iterations": iterations,
        }
    
    times.sort()
    return {
        "method": method,
        "url": url,
        "iterations": iterations,
        "errors": errors,
        "min_ms": round(min(times) * 1000, 2),
        "avg_ms": round((sum(times) / len(times)) * 1000, 2),
        "median_ms": round(times[len(times) // 2] * 1000, 2),
        "p95_ms": round(times[int(len(times) * 0.95)] * 1000, 2),
        "max_ms": round(max(times) * 1000, 2),
        "throughput_per_sec": round(len(times) / sum(times), 2),
    }


def run_benchmark(service_url: str, iterations: int = 10) -> dict:
    """
    Run comprehensive benchmark of deployed service.
    """
    print(f"\n{'='*70}")
    print(f"LinkPlease Deployment Benchmark")
    print(f"{'='*70}")
    print(f"Service URL: {service_url}")
    print(f"Iterations per endpoint: {iterations}\n")
    
    results = {
        "service_url": service_url,
        "iterations": iterations,
        "endpoints": [],
    }
    
    client = httpx.Client(timeout=30.0)
    
    try:
        # Benchmark GET /health
        print(f"Benchmarking GET /health ({iterations} iterations)...")
        result = benchmark_endpoint(
            client,
            "GET",
            f"{service_url}/health",
            iterations=iterations,
        )
        results["endpoints"].append(result)
        if "avg_ms" in result:
            print(f"  Average: {result['avg_ms']}ms (min: {result['min_ms']}ms, max: {result['max_ms']}ms)")
        else:
            print(f"  All {result['errors']} iterations failed")
        
        # Benchmark GET /stats
        print(f"\nBenchmarking GET /stats ({iterations} iterations)...")
        result = benchmark_endpoint(
            client,
            "GET",
            f"{service_url}/stats",
            iterations=iterations,
        )
        results["endpoints"].append(result)
        if "avg_ms" in result:
            print(f"  Average: {result['avg_ms']}ms (min: {result['min_ms']}ms, max: {result['max_ms']}ms)")
        else:
            print(f"  All {result['errors']} iterations failed")
        
        # Benchmark POST /rules
        print(f"\nBenchmarking POST /rules ({iterations} iterations)...")
        payload = {
            "keyword": "TEST",
            "dm_message": "This is a test rule",
        }
        result = benchmark_endpoint(
            client,
            "POST",
            f"{service_url}/rules",
            iterations=iterations,
            payload=payload,
        )
        results["endpoints"].append(result)
        if "avg_ms" in result:
            print(f"  Average: {result['avg_ms']}ms (min: {result['min_ms']}ms, max: {result['max_ms']}ms)")
        else:
            print(f"  All {result['errors']} iterations failed")
        
        # Summary statistics
        print(f"\n{'='*70}")
        print(f"Benchmark Summary")
        print(f"{'='*70}\n")
        
        for endpoint_result in results["endpoints"]:
            method = endpoint_result["method"]
            url_path = endpoint_result["url"].replace(service_url, "")
            
            print(f"{method} {url_path}")
            if "avg_ms" in endpoint_result:
                print(f"  Min: {endpoint_result['min_ms']}ms")
                print(f"  Avg: {endpoint_result['avg_ms']}ms")
                print(f"  Median: {endpoint_result['median_ms']}ms")
                print(f"  P95: {endpoint_result['p95_ms']}ms")
                print(f"  Max: {endpoint_result['max_ms']}ms")
                print(f"  Throughput: {endpoint_result['throughput_per_sec']} req/s")
            else:
                print(f"  ❌ All iterations failed ({endpoint_result['errors']} errors)")
            print()
        
        # Overall assessment
        print(f"{'='*70}")
        successful = [e for e in results["endpoints"] if "avg_ms" in e]
        if len(successful) == len(results["endpoints"]):
            avg_latencies = [e.get("avg_ms", 0) for e in results["endpoints"]]
            overall_avg = sum(avg_latencies) / len(avg_latencies)
            if overall_avg < 100:
                print(f"✅ Performance is excellent (avg latency: {overall_avg:.1f}ms)")
            elif overall_avg < 300:
                print(f"✅ Performance is good (avg latency: {overall_avg:.1f}ms)")
            elif overall_avg < 1000:
                print(f"⚠️  Performance is acceptable (avg latency: {overall_avg:.1f}ms)")
            else:
                print(f"❌ Performance is poor (avg latency: {overall_avg:.1f}ms)")
        else:
            print(f"❌ Some endpoints failed")
        print(f"{'='*70}\n")
        
    finally:
        client.close()
    
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Benchmark a deployed LinkPlease instance")
    parser.add_argument("--url", required=True, help="Service URL (e.g., https://linkplease-xxxxx.onrender.com)")
    parser.add_argument("--iterations", type=int, default=10, help="Number of iterations per endpoint")
    args = parser.parse_args()
    
    results = run_benchmark(args.url, iterations=args.iterations)
    
    # Save results to file
    results_file = "benchmark_results.json"
    with open(results_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Results saved to {results_file}")
    
    # Exit with success if all endpoints were benchmarked
    successful = [e for e in results["endpoints"] if "avg_ms" in e]
    sys.exit(0 if len(successful) == len(results["endpoints"]) else 1)
