#!/usr/bin/env python3
"""
Test script to demonstrate Playwright support and smart fallback.
"""
import json
from server import fetch_core

# Test URLs
test_urls = [
    ("https://example.com", "Static HTML site"),
    ("https://httpbin.org/html", "Simple HTML test"),
]

print("=" * 80)
print("SafeFetch Playwright Support Test")
print("=" * 80)

for url, description in test_urls:
    print(f"\n\n{'='*80}")
    print(f"Testing: {description}")
    print(f"URL: {url}")
    print(f"{'='*80}\n")

    # Test 1: Default (httpx with smart fallback)
    print("Test 1: Default mode (httpx + smart fallback)")
    print("-" * 80)
    result = fetch_core(url, max_tokens=500, use_playwright=False, enable_fallback=True)
    print(f"Status: {result.fetch_status}")
    print(f"Content length: {len(result.markdown)} chars")
    print(f"Method: {'Playwright (fallback)' if 'Playwright' in result.markdown else 'httpx'}")

    # Test 2: Force Playwright
    print("\n\nTest 2: Force Playwright mode")
    print("-" * 80)
    result_pw = fetch_core(url, max_tokens=500, use_playwright=True, enable_fallback=False)
    print(f"Status: {result_pw.fetch_status}")
    print(f"Content length: {len(result_pw.markdown)} chars")

    # Test 3: Disable fallback
    print("\n\nTest 3: httpx only (no fallback)")
    print("-" * 80)
    result_no_fb = fetch_core(url, max_tokens=500, use_playwright=False, enable_fallback=False)
    print(f"Status: {result_no_fb.fetch_status}")
    print(f"Content length: {len(result_no_fb.markdown)} chars")

print("\n\n" + "=" * 80)
print("Test completed!")
print("=" * 80)
