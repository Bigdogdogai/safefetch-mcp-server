#!/usr/bin/env python3
import unittest
from unittest.mock import patch

import safefetch.app as server


class FakeRequest:
    def __init__(self, url):
        self.url = url


class FakeRoute:
    def __init__(self):
        self.aborted = False
        self.continued = False

    def abort(self):
        self.aborted = True

    def continue_(self):
        self.continued = True


class FakeResponse:
    def __init__(self, status=200, content_type="text/html; charset=utf-8"):
        self.status = status
        self._content_type = content_type

    def header_value(self, name):
        if name.lower() == "content-type":
            return self._content_type
        return None


class FakePage:
    def __init__(self, final_url, response, html="<html><title>Example</title><body>Hello</body></html>"):
        self.url = final_url
        self._response = response
        self._html = html

    def goto(self, _url, timeout, wait_until):
        self.timeout = timeout
        self.wait_until = wait_until
        return self._response

    def content(self):
        return self._html

    def title(self):
        return "Example"


class FakeContext:
    def __init__(self, page, request_urls=None):
        self._page = page
        self._request_urls = request_urls or []
        self._route_handler = None

    def route(self, _pattern, handler):
        self._route_handler = handler

    def new_page(self):
        if self._route_handler is not None:
            for url in self._request_urls:
                self._route_handler(FakeRoute(), FakeRequest(url))
        return self._page


class FakeBrowser:
    def __init__(self, context):
        self._context = context
        self.closed = False

    def new_context(self, **_kwargs):
        return self._context

    def close(self):
        self.closed = True


class FakeChromium:
    def __init__(self, browser):
        self._browser = browser

    def launch(self, headless=True):
        self.headless = headless
        return self._browser


class FakePlaywright:
    def __init__(self, browser):
        self.chromium = FakeChromium(browser)


class FakePlaywrightManager:
    def __init__(self, browser):
        self._playwright = FakePlaywright(browser)

    def __enter__(self):
        return self._playwright

    def __exit__(self, exc_type, exc, tb):
        return False


class FetchCoreTests(unittest.TestCase):
    def make_result(self, **overrides):
        base = server.FetchResult(
            ok=True,
            fetch_status="ok",
            blocked_reason="",
            final_url="https://example.com",
            status_code=200,
            content_type="text/html",
            title="Example",
            markdown="short",
            fetched_at=server.now_utc(),
            redirects=0,
            raw_bytes=10,
            decompressed_bytes=10,
            truncated=False,
        )
        for key, value in overrides.items():
            setattr(base, key, value)
        return base

    def test_fallback_result_keeps_metadata_consistent(self):
        primary = self.make_result(markdown="short")
        fallback = self.make_result(markdown="x" * 400, render_mode="playwright")

        with patch.object(server, "sync_playwright", object()), \
             patch.object(server, "fetch_once", return_value=primary), \
             patch.object(server, "fetch_with_playwright", return_value=fallback):
            result = server.fetch_core("https://example.com", enable_fallback=True)

        self.assertTrue(result.ok)
        self.assertEqual(result.attempts, 1)
        self.assertFalse(result.retried)
        self.assertFalse(result.retryable_error)
        self.assertFalse(result.security_blocked)
        self.assertEqual(result.last_error, "")
        self.assertTrue(result.fallback_used)
        self.assertEqual(result.render_mode, "playwright")

    def test_security_block_marker_detects_playwright_request_blocks(self):
        result = self.make_result(
            ok=False,
            fetch_status="blocked",
            blocked_reason="playwright_request_dns_ip_blocked",
        )
        self.assertTrue(server.is_security_block(result))

    def test_playwright_blocks_disallowed_subrequests(self):
        page = FakePage("https://example.com", FakeResponse())
        context = FakeContext(page, request_urls=["http://127.0.0.1/internal"])
        browser = FakeBrowser(context)

        def fake_sync_playwright():
            return FakePlaywrightManager(browser)

        def fake_validate(url):
            if "127.0.0.1" in url:
                return False, "ip_blocked"
            return True, ""

        with patch.object(server, "sync_playwright", fake_sync_playwright), \
             patch.object(server, "validate_url_and_dns", side_effect=fake_validate):
            result = server.fetch_with_playwright("https://example.com")

        self.assertFalse(result.ok)
        self.assertEqual(result.fetch_status, "blocked")
        self.assertEqual(result.blocked_reason, "playwright_request_ip_blocked")

    def test_playwright_treats_http_errors_as_failures(self):
        page = FakePage("https://example.com/missing", FakeResponse(status=404))
        context = FakeContext(page)
        browser = FakeBrowser(context)

        def fake_sync_playwright():
            return FakePlaywrightManager(browser)

        with patch.object(server, "sync_playwright", fake_sync_playwright), \
             patch.object(server, "validate_url_and_dns", return_value=(True, "")):
            result = server.fetch_with_playwright("https://example.com/missing")

        self.assertFalse(result.ok)
        self.assertEqual(result.fetch_status, "http_error")
        self.assertEqual(result.blocked_reason, "http_404")
        self.assertEqual(result.status_code, 404)

    def test_detects_spa_shell_from_root_div_and_short_content(self):
        html = "<html><head><title>App</title></head><body><div id='root'></div><script src='/assets/app.js'></script></body></html>"
        self.assertTrue(server.looks_like_spa_shell(html, "", "text/html; charset=utf-8"))

    def test_shell_only_httpx_result_triggers_playwright_fallback(self):
        primary = self.make_result(
            markdown="# Source\n\n- Title: App\n- URL: https://example.com\n- Fetched At: now\n- Content-Type: text/html\n\nApp",
            shell_only=True,
            js_required=True,
        )
        fallback = self.make_result(markdown="x" * 400, render_mode="playwright")

        with patch.object(server, "sync_playwright", object()), \
             patch.object(server, "fetch_once", return_value=primary), \
             patch.object(server, "fetch_with_playwright", return_value=fallback):
            result = server.fetch_core("https://example.com", enable_fallback=True)

        self.assertTrue(result.ok)
        self.assertTrue(result.fallback_used)
        self.assertEqual(result.render_mode, "playwright")

    def test_offline_self_test_passes_without_network(self):
        self.assertEqual(server.run_offline_self_test(), 0)


if __name__ == "__main__":
    unittest.main()
