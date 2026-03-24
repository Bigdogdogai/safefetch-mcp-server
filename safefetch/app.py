#!/usr/bin/env python3
import argparse
import ipaddress
import json
import logging
import os
import re
import socket
import time
import zlib
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Set, Tuple
from urllib.parse import urljoin, urlparse

import httpx
import trafilatura
from bs4 import BeautifulSoup
from charset_normalizer import from_bytes

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

try:
    from mcp.server.fastmcp import FastMCP  # type: ignore
except Exception:  # pragma: no cover
    FastMCP = None

try:
    import dns.resolver  # type: ignore
except Exception:  # pragma: no cover
    dns = None

try:
    import brotli  # type: ignore
except Exception:  # pragma: no cover
    brotli = None

try:
    import tiktoken  # type: ignore
except Exception:  # pragma: no cover
    tiktoken = None

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout  # type: ignore
except Exception:  # pragma: no cover
    sync_playwright = None
    PlaywrightTimeout = None


APP_NAME = "safefetch-v1"
USER_AGENT = f"{APP_NAME}/1.0"
MAX_REDIRECTS = 5
MAX_RAW_BYTES = 5 * 1024 * 1024
MAX_DECOMPRESSED_BYTES = 8 * 1024 * 1024
DEFAULT_MAX_TOKENS = 3000
MAX_RETRIES = 2
CONNECT_TIMEOUT = 5.0
READ_TIMEOUT = 15.0
RATE_LIMIT_RPM = 20
RATE_LIMIT_MAX_CALLERS = 1000  # Prevent memory leak
ALLOW_HTTPS_DOWNGRADE = False
MIME_ALLOWLIST = ("text/html", "text/plain", "application/json")
RETRYABLE_HTTP_STATUS = {408, 425, 429, 500, 502, 503, 504}

# Playwright settings
PLAYWRIGHT_TIMEOUT = 30000  # 30 seconds
PLAYWRIGHT_WAIT_UNTIL = "networkidle"  # Wait for network to be idle
MIN_CONTENT_LENGTH = 200  # Minimum content length to consider valid (for fallback)
ENABLE_SMART_FALLBACK = True  # Enable automatic fallback to Playwright

_RATE_BUCKET: Dict[str, List[float]] = OrderedDict()
mcp = FastMCP(APP_NAME) if FastMCP is not None else None


def parse_allow_cidrs() -> List[ipaddress._BaseNetwork]:
    raw = os.getenv("WEBFETCH_ALLOW_CIDRS", "").strip()
    if not raw:
        return []
    nets: List[ipaddress._BaseNetwork] = []
    for part in raw.split(","):
        val = part.strip()
        if not val:
            continue
        try:
            nets.append(ipaddress.ip_network(val, strict=False))
        except Exception as e:
            logger.warning(f"Invalid CIDR in WEBFETCH_ALLOW_CIDRS: {val!r} - {e}")
            continue
    if nets:
        logger.info(f"Loaded {len(nets)} CIDR allowlist entries")
    return nets


ALLOW_CIDRS = parse_allow_cidrs()


@dataclass
class FetchResult:
    ok: bool
    fetch_status: str
    blocked_reason: str
    final_url: str
    status_code: int
    content_type: str
    title: str
    markdown: str
    fetched_at: str
    redirects: int
    raw_bytes: int
    decompressed_bytes: int
    truncated: bool
    attempts: int = 1
    retried: bool = False
    retryable_error: bool = False
    last_error: str = ""
    security_blocked: bool = False
    render_mode: str = "httpx"
    fallback_used: bool = False
    shell_only: bool = False
    js_required: bool = False

    def to_dict(self) -> Dict[str, object]:
        return {
            "ok": self.ok,
            "fetch_status": self.fetch_status,
            "blocked_reason": self.blocked_reason,
            "final_url": self.final_url,
            "status_code": self.status_code,
            "content_type": self.content_type,
            "title": self.title,
            "content_markdown": self.markdown,
            "content_chars": len(self.markdown or ""),
            "fetched_at": self.fetched_at,
            "redirects": self.redirects,
            "raw_bytes": self.raw_bytes,
            "decompressed_bytes": self.decompressed_bytes,
            "truncated": self.truncated,
            "attempts": self.attempts,
            "retried": self.retried,
            "retryable_error": self.retryable_error,
            "last_error": self.last_error,
            "security_blocked": self.security_blocked,
            "render_mode": self.render_mode,
            "fallback_used": self.fallback_used,
            "shell_only": self.shell_only,
            "js_required": self.js_required,
        }


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_blocked_ip(ip_text: str) -> bool:
    ip = ipaddress.ip_address(ip_text)
    for net in ALLOW_CIDRS:
        if ip in net:
            logger.debug(f"IP {ip_text} allowed by CIDR allowlist")
            return False
    blocked = (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )
    if blocked:
        logger.info(f"IP {ip_text} blocked (private/loopback/reserved)")
    return blocked


def resolve_host_ips(hostname: str) -> List[str]:
    ips: List[str] = []
    # DNS query path
    if dns is not None:
        try:
            for rr in dns.resolver.resolve(hostname, "A", lifetime=2.0):
                ips.append(rr.to_text())
        except Exception:
            pass
        try:
            for rr in dns.resolver.resolve(hostname, "AAAA", lifetime=2.0):
                ips.append(rr.to_text())
        except Exception:
            pass
    # Socket fallback
    try:
        infos = socket.getaddrinfo(hostname, None)
        for info in infos:
            addr = info[4][0]
            ips.append(addr)
    except Exception:
        pass
    return sorted(list(set(ips)))


def validate_url_and_dns(url: str) -> Tuple[bool, str]:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        logger.info(f"Blocked invalid scheme: {parsed.scheme} for {url}")
        return False, "invalid_scheme"
    if parsed.username or parsed.password:
        logger.warning(f"Blocked URL with userinfo: {url}")
        return False, "userinfo_not_allowed"
    if not parsed.hostname:
        logger.warning(f"Blocked URL with missing hostname: {url}")
        return False, "missing_hostname"
    host = parsed.hostname.strip().lower()
    if host in ("localhost",):
        logger.info(f"Blocked localhost: {url}")
        return False, "localhost_blocked"
    try:
        ipaddress.ip_address(host)
        if is_blocked_ip(host):
            return False, "ip_blocked"
        logger.debug(f"Direct IP address validated: {host}")
        return True, ""
    except ValueError:
        pass
    # DNS resolution - NOTE: TOCTOU risk exists here
    # The DNS may resolve differently when httpx actually makes the request
    # For maximum security, consider network-level controls (firewall rules)
    ips = resolve_host_ips(host)
    if not ips:
        logger.warning(f"DNS resolution failed for: {host}")
        return False, "dns_resolution_failed"
    logger.debug(f"DNS resolved {host} to {len(ips)} IPs: {ips}")
    for ip_text in ips:
        if is_blocked_ip(ip_text):
            logger.warning(f"DNS resolved to blocked IP: {host} -> {ip_text}")
            return False, "dns_ip_blocked"
    return True, ""


def allow_request(caller_id: str) -> bool:
    now = time.time()

    # Clean up old callers to prevent memory leak
    if len(_RATE_BUCKET) > RATE_LIMIT_MAX_CALLERS:
        # Remove oldest entries
        for _ in range(len(_RATE_BUCKET) - RATE_LIMIT_MAX_CALLERS + 100):
            _RATE_BUCKET.popitem(last=False)
        logger.warning(f"Rate limit bucket cleanup: removed old entries")

    history = _RATE_BUCKET.setdefault(caller_id, [])
    history[:] = [x for x in history if now - x <= 60.0]

    if len(history) >= RATE_LIMIT_RPM:
        logger.info(f"Rate limit exceeded for caller_id={caller_id}")
        return False

    history.append(now)
    # Move to end to maintain LRU order
    _RATE_BUCKET.move_to_end(caller_id)
    return True


def get_decompressor(content_encoding: str):
    ce = (content_encoding or "").lower().strip()
    if ce in ("", "identity"):
        return "identity", None
    if ce == "gzip":
        return "gzip", zlib.decompressobj(16 + zlib.MAX_WBITS)
    if ce == "deflate":
        return "deflate", zlib.decompressobj()
    if ce == "br" and brotli is not None:
        return "br", brotli.Decompressor()
    return "unsupported", None


def decompress_chunk(mode: str, dec, chunk: bytes) -> bytes:
    if mode == "identity":
        return chunk
    if mode in ("gzip", "deflate"):
        return dec.decompress(chunk)
    if mode == "br":
        return dec.process(chunk)
    return b""


def decompress_flush(mode: str, dec) -> bytes:
    if mode in ("gzip", "deflate"):
        return dec.flush()
    return b""


def decode_bytes(data: bytes, content_type: str) -> str:
    charset = ""
    parts = [p.strip() for p in content_type.split(";")]
    for p in parts[1:]:
        if p.lower().startswith("charset="):
            charset = p.split("=", 1)[1].strip().strip('"').strip("'")
            break
    if charset:
        try:
            return data.decode(charset, errors="replace")
        except Exception:
            pass
    best = from_bytes(data).best()
    if best and best.encoding:
        try:
            return str(best)
        except Exception:
            pass
    return data.decode("utf-8", errors="replace")


def truncate_markdown(md: str, max_tokens: int) -> Tuple[str, bool]:
    if max_tokens <= 0:
        return md, False
    if tiktoken is None:
        # rough fallback: 1 token ~= 4 chars
        cap = max_tokens * 4
        if len(md) <= cap:
            return md, False
        return md[:cap] + "\n\n...[Content Truncated]", True
    enc = tiktoken.get_encoding("cl100k_base")
    tokens = enc.encode(md)
    if len(tokens) <= max_tokens:
        return md, False
    truncated = enc.decode(tokens[:max_tokens]).rstrip() + "\n\n...[Content Truncated]"
    return truncated, True


def strip_metadata_header(md: str) -> str:
    if not md.startswith("# Source\n\n"):
        return md
    parts = md.split("\n\n", 2)
    if len(parts) < 3:
        return ""
    return parts[2]


def looks_like_spa_shell(html_or_text: str, extracted_markdown: str, content_type: str) -> bool:
    content_main = strip_metadata_header(extracted_markdown).strip()
    if "html" not in (content_type or "").lower():
        return False
    if len(content_main) >= MIN_CONTENT_LENGTH:
        return False

    lowered = html_or_text.lower()
    shell_markers = (
        'id="root"',
        "id='root'",
        'id="app"',
        "id='app'",
        'id="__next"',
        "id='__next'",
        'id="__nuxt"',
        "id='__nuxt'",
        "data-reactroot",
        "__next_data__",
        "__nuxt__",
        "webpack",
        "vite",
    )
    if not any(marker in lowered for marker in shell_markers):
        return False

    body_text = BeautifulSoup(html_or_text, "html.parser").get_text(" ", strip=True)
    body_text = re.sub(r"\s+", " ", body_text).strip()
    return len(body_text) < MIN_CONTENT_LENGTH


def finalize_result_metadata(result: FetchResult, attempts: int) -> FetchResult:
    result.attempts = attempts
    result.security_blocked = is_security_block(result)
    result.retryable_error = is_retryable_result(result)
    result.last_error = result.blocked_reason
    result.retried = attempts > 1
    return result


def fetch_with_playwright(url: str, max_tokens: int = DEFAULT_MAX_TOKENS) -> FetchResult:
    """
    Fetch a URL using Playwright (headless browser) for JS-rendered content.

    This method is slower but can handle JavaScript-heavy websites that don't
    work with static HTTP fetching.
    """
    if sync_playwright is None:
        logger.error("Playwright not available - install with: pip install playwright && playwright install chromium")
        return FetchResult(
            ok=False,
            fetch_status="error",
            blocked_reason="playwright_not_installed",
            final_url=url,
            status_code=0,
            content_type="",
            title="",
            markdown="",
            fetched_at=now_utc(),
            redirects=0,
            raw_bytes=0,
            decompressed_bytes=0,
            truncated=False,
            render_mode="playwright",
        )

    fetched_at = now_utc()

    # Validate URL before launching browser
    ok, reason = validate_url_and_dns(url)
    if not ok:
        logger.warning(f"Playwright fetch blocked: {reason} for {url}")
        return FetchResult(
            ok=False,
            fetch_status="blocked",
            blocked_reason=reason,
            final_url=url,
            status_code=0,
            content_type="",
            title="",
            markdown="",
            fetched_at=fetched_at,
            redirects=0,
            raw_bytes=0,
            decompressed_bytes=0,
            truncated=False,
            render_mode="playwright",
        )

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1280, "height": 720},
            )
            blocked_request_reason = ""

            def handle_route(route, request) -> None:
                nonlocal blocked_request_reason
                req_url = request.url
                ok_req, reason_req = validate_url_and_dns(req_url)
                if not ok_req:
                    blocked_request_reason = reason_req
                    logger.warning(f"Playwright request blocked: {reason_req} for {req_url}")
                    route.abort()
                    return
                route.continue_()

            context.route("**/*", handle_route)
            page = context.new_page()

            # Navigate and wait for content
            logger.info(f"Playwright fetching: {url}")
            response = page.goto(url, timeout=PLAYWRIGHT_TIMEOUT, wait_until=PLAYWRIGHT_WAIT_UNTIL)

            if response is None:
                browser.close()
                return FetchResult(
                    ok=False,
                    fetch_status="error",
                    blocked_reason="no_response",
                    final_url=url,
                    status_code=0,
                    content_type="",
                    title="",
                    markdown="",
                    fetched_at=fetched_at,
                    redirects=0,
                    raw_bytes=0,
                    decompressed_bytes=0,
                    truncated=False,
                    render_mode="playwright",
                )

            if blocked_request_reason:
                browser.close()
                return FetchResult(
                    ok=False,
                    fetch_status="blocked",
                    blocked_reason=f"playwright_request_{blocked_request_reason}",
                    final_url=page.url or url,
                    status_code=0,
                    content_type="",
                    title="",
                    markdown="",
                    fetched_at=fetched_at,
                    redirects=0,
                    raw_bytes=0,
                    decompressed_bytes=0,
                    truncated=False,
                    render_mode="playwright",
                )

            status_code = response.status
            final_url = page.url
            response_content_type = (response.header_value("content-type") or "").strip()
            content_type = response_content_type.split(";", 1)[0].strip().lower()

            # Check if we were redirected to a blocked URL
            if final_url != url:
                ok_redirect, reason_redirect = validate_url_and_dns(final_url)
                if not ok_redirect:
                    logger.warning(f"Playwright redirect blocked: {reason_redirect} for {final_url}")
                    browser.close()
                    return FetchResult(
                        ok=False,
                        fetch_status="blocked",
                        blocked_reason=f"redirect_{reason_redirect}",
                        final_url=final_url,
                        status_code=status_code,
                        content_type="",
                        title="",
                        markdown="",
                        fetched_at=fetched_at,
                        redirects=1,
                        raw_bytes=0,
                        decompressed_bytes=0,
                        truncated=False,
                        render_mode="playwright",
                        )

            if status_code < 200 or status_code >= 400:
                browser.close()
                return FetchResult(
                    ok=False,
                    fetch_status="http_error",
                    blocked_reason=f"http_{status_code}",
                    final_url=final_url,
                    status_code=status_code,
                    content_type=response_content_type,
                    title="",
                    markdown="",
                    fetched_at=fetched_at,
                    redirects=1 if final_url != url else 0,
                    raw_bytes=0,
                    decompressed_bytes=0,
                    truncated=False,
                    render_mode="playwright",
                )

            if content_type and content_type not in MIME_ALLOWLIST:
                browser.close()
                return FetchResult(
                    ok=False,
                    fetch_status="blocked",
                    blocked_reason="mime_not_allowed",
                    final_url=final_url,
                    status_code=status_code,
                    content_type=response_content_type,
                    title="",
                    markdown="",
                    fetched_at=fetched_at,
                    redirects=1 if final_url != url else 0,
                    raw_bytes=0,
                    decompressed_bytes=0,
                    truncated=False,
                    render_mode="playwright",
                )

            # Extract content
            html_content = page.content()
            raw_bytes = len(html_content.encode('utf-8'))
            if raw_bytes > MAX_DECOMPRESSED_BYTES:
                browser.close()
                return FetchResult(
                    ok=False,
                    fetch_status="blocked",
                    blocked_reason="decompressed_size_exceeded",
                    final_url=final_url,
                    status_code=status_code,
                    content_type=response_content_type,
                    title="",
                    markdown="",
                    fetched_at=fetched_at,
                    redirects=1 if final_url != url else 0,
                    raw_bytes=raw_bytes,
                    decompressed_bytes=raw_bytes,
                    truncated=False,
                    render_mode="playwright",
                )

            # Get title
            title = page.title()

            # Extract main content using trafilatura
            markdown = trafilatura.extract(
                html_content,
                output_format="markdown",
                include_comments=False,
                include_tables=True,
                include_images=False,
                deduplicate=True,
                favor_precision=True,
            )

            # Fallback to BeautifulSoup if trafilatura fails
            if not markdown:
                soup = BeautifulSoup(html_content, "html.parser")
                markdown = soup.get_text("\n", strip=True)

            markdown = markdown.strip()
            markdown, truncated = truncate_markdown(markdown, max_tokens=max_tokens)

            browser.close()

            logger.info(f"Playwright successfully fetched {final_url}: {status_code}, {len(markdown)} chars")

            metadata_header = (
                "# Source\n\n"
                f"- Title: {title or 'N/A'}\n"
                f"- URL: {final_url}\n"
                f"- Fetched At: {fetched_at}\n"
                f"- Method: Playwright (JS-rendered)\n\n"
            )

            return FetchResult(
                ok=True,
                fetch_status="ok",
                blocked_reason="",
                final_url=final_url,
                status_code=status_code,
                content_type=response_content_type,
                title=title,
                markdown=(metadata_header + markdown).strip(),
                fetched_at=fetched_at,
                redirects=1 if final_url != url else 0,
                raw_bytes=raw_bytes,
                decompressed_bytes=raw_bytes,
                truncated=truncated,
                render_mode="playwright",
            )

    except PlaywrightTimeout:
        logger.warning(f"Playwright timeout for {url}")
        return FetchResult(
            ok=False,
            fetch_status="timeout",
            blocked_reason="playwright_timeout",
            final_url=url,
            status_code=0,
            content_type="",
            title="",
            markdown="",
            fetched_at=fetched_at,
            redirects=0,
            raw_bytes=0,
            decompressed_bytes=0,
            truncated=False,
            render_mode="playwright",
        )
    except Exception as exc:
        logger.error(f"Playwright error for {url}: {exc.__class__.__name__} - {exc}")
        return FetchResult(
            ok=False,
            fetch_status="error",
            blocked_reason=f"playwright_error:{exc.__class__.__name__}",
            final_url=url,
            status_code=0,
            content_type="",
            title="",
            markdown="",
            fetched_at=fetched_at,
            redirects=0,
            raw_bytes=0,
            decompressed_bytes=0,
            truncated=False,
            render_mode="playwright",
        )


def fetch_once(url: str, max_tokens: int = DEFAULT_MAX_TOKENS, use_playwright: bool = False) -> FetchResult:
    """
    Fetch a URL once with security checks.

    Args:
        url: The URL to fetch
        max_tokens: Maximum tokens for content truncation
        use_playwright: If True, use Playwright (headless browser) instead of httpx

    Security Note - DNS TOCTOU:
    There is a theoretical Time-Of-Check-Time-Of-Use (TOCTOU) race condition
    between our DNS validation and httpx's actual connection. An attacker with
    control over DNS could change the resolution between these two points.

    Mitigations in place:
    1. We re-validate DNS on every redirect hop (reduces window)
    2. We log all DNS resolutions for audit trails
    3. Network-level controls (firewall rules) are recommended for defense-in-depth

    For maximum security in hostile environments, consider:
    - Using WEBFETCH_ALLOW_CIDRS to explicitly allowlist safe IP ranges
    - Deploying network-level egress filtering
    - Running in a sandboxed network namespace
    """
    # Route to Playwright if requested
    if use_playwright:
        return fetch_with_playwright(url, max_tokens)

    fetched_at = now_utc()
    ok, reason = validate_url_and_dns(url)
    if not ok:
        return FetchResult(
            ok=False,
            fetch_status="blocked",
            blocked_reason=reason,
            final_url=url,
            status_code=0,
            content_type="",
            title="",
            markdown="",
            fetched_at=fetched_at,
            redirects=0,
            raw_bytes=0,
            decompressed_bytes=0,
            truncated=False,
        )

    timeout = httpx.Timeout(connect=CONNECT_TIMEOUT, read=READ_TIMEOUT, write=READ_TIMEOUT, pool=READ_TIMEOUT)
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,text/plain,application/json;q=0.9,*/*;q=0.1",
        "Accept-Encoding": "gzip,deflate,identity",
    }
    redirects = 0
    current_url = url
    raw_total = 0
    dec_total = 0
    visited_urls: Set[str] = set()  # Track visited URLs to detect loops

    with httpx.Client(timeout=timeout, headers=headers, follow_redirects=False) as client:
        while True:
            # Check for redirect loops
            if current_url in visited_urls:
                logger.warning(f"Redirect loop detected: {current_url}")
                return FetchResult(
                    ok=False,
                    fetch_status="blocked",
                    blocked_reason="redirect_loop_detected",
                    final_url=current_url,
                    status_code=0,
                    content_type="",
                    title="",
                    markdown="",
                    fetched_at=fetched_at,
                    redirects=redirects,
                    raw_bytes=raw_total,
                    decompressed_bytes=dec_total,
                    truncated=False,
                )
            visited_urls.add(current_url)

            # Re-validate every hop, blocks redirect-based bypass.
            ok_hop, reason_hop = validate_url_and_dns(current_url)
            if not ok_hop:
                logger.warning(f"URL validation failed at redirect hop: {reason_hop} for {current_url}")
                return FetchResult(
                    ok=False,
                    fetch_status="blocked",
                    blocked_reason=f"redirect_{reason_hop}",
                    final_url=current_url,
                    status_code=0,
                    content_type="",
                    title="",
                    markdown="",
                    fetched_at=fetched_at,
                    redirects=redirects,
                    raw_bytes=raw_total,
                    decompressed_bytes=dec_total,
                    truncated=False,
                )

            try:
                with client.stream("GET", current_url) as resp:
                    status = int(resp.status_code)
                    if status in (301, 302, 303, 307, 308):
                        if redirects >= MAX_REDIRECTS:
                            logger.warning(f"Too many redirects: {redirects} for {current_url}")
                            return FetchResult(
                                ok=False,
                                fetch_status="blocked",
                                blocked_reason="too_many_redirects",
                                final_url=current_url,
                                status_code=status,
                                content_type=resp.headers.get("content-type", ""),
                                title="",
                                markdown="",
                                fetched_at=fetched_at,
                                redirects=redirects,
                                raw_bytes=raw_total,
                                decompressed_bytes=dec_total,
                                truncated=False,
                            )
                        nxt = urljoin(current_url, resp.headers.get("location", ""))
                        if not nxt:
                            logger.warning(f"Invalid redirect location from {current_url}")
                            return FetchResult(
                                ok=False,
                                fetch_status="error",
                                blocked_reason="invalid_redirect_location",
                                final_url=current_url,
                                status_code=status,
                                content_type=resp.headers.get("content-type", ""),
                                title="",
                                markdown="",
                                fetched_at=fetched_at,
                                redirects=redirects,
                                raw_bytes=raw_total,
                                decompressed_bytes=dec_total,
                                truncated=False,
                            )
                        if (not ALLOW_HTTPS_DOWNGRADE) and urlparse(current_url).scheme == "https" and urlparse(nxt).scheme == "http":
                            logger.warning(f"HTTPS downgrade blocked: {current_url} -> {nxt}")
                            return FetchResult(
                                ok=False,
                                fetch_status="blocked",
                                blocked_reason="https_downgrade_blocked",
                                final_url=nxt,
                                status_code=status,
                                content_type=resp.headers.get("content-type", ""),
                                title="",
                                markdown="",
                                fetched_at=fetched_at,
                                redirects=redirects,
                                raw_bytes=raw_total,
                                decompressed_bytes=dec_total,
                                truncated=False,
                            )
                        redirects += 1
                        current_url = nxt
                        continue

                    if status < 200 or status >= 400:
                        return FetchResult(
                            ok=False,
                            fetch_status="http_error",
                            blocked_reason=f"http_{status}",
                            final_url=current_url,
                            status_code=status,
                            content_type=resp.headers.get("content-type", ""),
                            title="",
                            markdown="",
                            fetched_at=fetched_at,
                            redirects=redirects,
                            raw_bytes=raw_total,
                            decompressed_bytes=dec_total,
                            truncated=False,
                        )

                    content_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                    if content_type and content_type not in MIME_ALLOWLIST:
                        logger.info(f"Blocked MIME type: {content_type} for {current_url}")
                        return FetchResult(
                            ok=False,
                            fetch_status="blocked",
                            blocked_reason="mime_not_allowed",
                            final_url=current_url,
                            status_code=status,
                            content_type=resp.headers.get("content-type", ""),
                            title="",
                            markdown="",
                            fetched_at=fetched_at,
                            redirects=redirects,
                            raw_bytes=raw_total,
                            decompressed_bytes=dec_total,
                            truncated=False,
                        )

                    mode, dec = get_decompressor(resp.headers.get("content-encoding", ""))
                    if mode == "unsupported":
                        return FetchResult(
                            ok=False,
                            fetch_status="blocked",
                            blocked_reason="unsupported_content_encoding",
                            final_url=current_url,
                            status_code=status,
                            content_type=resp.headers.get("content-type", ""),
                            title="",
                            markdown="",
                            fetched_at=fetched_at,
                            redirects=redirects,
                            raw_bytes=raw_total,
                            decompressed_bytes=dec_total,
                            truncated=False,
                        )

                    out = bytearray()
                    for chunk in resp.iter_raw():
                        raw_total += len(chunk)
                        if raw_total > MAX_RAW_BYTES:
                            logger.warning(f"Raw size exceeded: {raw_total} bytes for {current_url}")
                            return FetchResult(
                                ok=False,
                                fetch_status="blocked",
                                blocked_reason="raw_size_exceeded",
                                final_url=current_url,
                                status_code=status,
                                content_type=resp.headers.get("content-type", ""),
                                title="",
                                markdown="",
                                fetched_at=fetched_at,
                                redirects=redirects,
                                raw_bytes=raw_total,
                                decompressed_bytes=dec_total,
                                truncated=False,
                            )
                        decoded = decompress_chunk(mode, dec, chunk)
                        dec_total += len(decoded)
                        if dec_total > MAX_DECOMPRESSED_BYTES:
                            logger.warning(f"Decompressed size exceeded: {dec_total} bytes for {current_url}")
                            return FetchResult(
                                ok=False,
                                fetch_status="blocked",
                                blocked_reason="decompressed_size_exceeded",
                                final_url=current_url,
                                status_code=status,
                                content_type=resp.headers.get("content-type", ""),
                                title="",
                                markdown="",
                                fetched_at=fetched_at,
                                redirects=redirects,
                                raw_bytes=raw_total,
                                decompressed_bytes=dec_total,
                                truncated=False,
                            )
                        out.extend(decoded)
                    remain = decompress_flush(mode, dec)
                    if remain:
                        dec_total += len(remain)
                        if dec_total > MAX_DECOMPRESSED_BYTES:
                            return FetchResult(
                                ok=False,
                                fetch_status="blocked",
                                blocked_reason="decompressed_size_exceeded",
                                final_url=current_url,
                                status_code=status,
                                content_type=resp.headers.get("content-type", ""),
                                title="",
                                markdown="",
                                fetched_at=fetched_at,
                                redirects=redirects,
                                raw_bytes=raw_total,
                                decompressed_bytes=dec_total,
                                truncated=False,
                            )
                        out.extend(remain)

                    html_or_text = decode_bytes(bytes(out), resp.headers.get("content-type", ""))
                    soup = BeautifulSoup(html_or_text, "html.parser")
                    title = soup.title.get_text(" ", strip=True) if soup.title else ""
                    markdown = trafilatura.extract(
                        html_or_text,
                        output_format="markdown",
                        include_comments=False,
                        include_tables=True,
                        include_images=False,
                        deduplicate=True,
                        favor_precision=True,
                    )
                    if not markdown:
                        markdown = soup.get_text("\n", strip=True)
                    markdown = markdown.strip()
                    markdown, truncated = truncate_markdown(markdown, max_tokens=max_tokens)
                    shell_only = looks_like_spa_shell(
                        html_or_text=html_or_text,
                        extracted_markdown=markdown,
                        content_type=resp.headers.get("content-type", ""),
                    )

                    logger.info(f"Successfully fetched {current_url}: {status}, {len(markdown)} chars, {redirects} redirects, truncated={truncated}")

                    metadata_header = (
                        "# Source\n\n"
                        f"- Title: {title or 'N/A'}\n"
                        f"- URL: {current_url}\n"
                        f"- Fetched At: {fetched_at}\n"
                        f"- Content-Type: {resp.headers.get('content-type', '')}\n\n"
                    )
                    return FetchResult(
                        ok=True,
                        fetch_status="ok",
                        blocked_reason="",
                        final_url=current_url,
                        status_code=status,
                        content_type=resp.headers.get("content-type", ""),
                        title=title,
                        markdown=(metadata_header + markdown).strip(),
                        fetched_at=fetched_at,
                        redirects=redirects,
                        raw_bytes=raw_total,
                        decompressed_bytes=dec_total,
                        truncated=truncated,
                        shell_only=shell_only,
                        js_required=shell_only,
                    )
            except httpx.TimeoutException as exc:
                logger.warning(f"Request timeout for {current_url}: {exc}")
                return FetchResult(
                    ok=False,
                    fetch_status="timeout",
                    blocked_reason="request_timeout",
                    final_url=current_url,
                    status_code=0,
                    content_type="",
                    title="",
                    markdown="",
                    fetched_at=fetched_at,
                    redirects=redirects,
                    raw_bytes=raw_total,
                    decompressed_bytes=dec_total,
                    truncated=False,
                )
            except httpx.HTTPError as exc:
                logger.error(f"HTTP error for {current_url}: {exc.__class__.__name__} - {exc}")
                return FetchResult(
                    ok=False,
                    fetch_status="error",
                    blocked_reason=f"httpx_error:{exc.__class__.__name__}",
                    final_url=current_url,
                    status_code=0,
                    content_type="",
                    title="",
                    markdown="",
                    fetched_at=fetched_at,
                    redirects=redirects,
                    raw_bytes=raw_total,
                    decompressed_bytes=dec_total,
                    truncated=False,
                )
            except Exception as exc:  # pragma: no cover
                logger.error(f"Unexpected error for {current_url}: {exc.__class__.__name__} - {exc}")
                return FetchResult(
                    ok=False,
                    fetch_status="error",
                    blocked_reason=f"unexpected:{exc.__class__.__name__}",
                    final_url=current_url,
                    status_code=0,
                    content_type="",
                    title="",
                    markdown="",
                    fetched_at=fetched_at,
                    redirects=redirects,
                    raw_bytes=raw_total,
                    decompressed_bytes=dec_total,
                    truncated=False,
                )


def is_security_block(result: FetchResult) -> bool:
    if result.fetch_status != "blocked":
        return False
    reason = (result.blocked_reason or "").lower()
    security_markers = (
        "invalid_scheme",
        "userinfo_not_allowed",
        "missing_hostname",
        "localhost_blocked",
        "ip_blocked",
        "dns_ip_blocked",
        "dns_resolution_failed",
        "playwright_request_",
        "redirect_",
        "https_downgrade_blocked",
        "mime_not_allowed",
        "unsupported_content_encoding",
        "raw_size_exceeded",
        "decompressed_size_exceeded",
    )
    return any(reason.startswith(x) for x in security_markers)


def is_retryable_result(result: FetchResult) -> bool:
    if result.ok:
        return False
    if is_security_block(result):
        return False
    if result.fetch_status == "timeout":
        return True
    if result.fetch_status == "http_error" and result.status_code in RETRYABLE_HTTP_STATUS:
        return True
    if result.fetch_status == "error" and str(result.blocked_reason).startswith("httpx_error:"):
        return True
    return False


def fetch_core(url: str, max_tokens: int = DEFAULT_MAX_TOKENS, use_playwright: bool = False, enable_fallback: bool = True) -> FetchResult:
    """
    Fetch a URL with retry logic and optional smart fallback to Playwright.

    Args:
        url: The URL to fetch
        max_tokens: Maximum tokens for content truncation
        use_playwright: If True, use Playwright directly (skip httpx)
        enable_fallback: If True, automatically fallback to Playwright if httpx returns insufficient content
    """
    attempts = 0
    last = FetchResult(
        ok=False,
        fetch_status="error",
        blocked_reason="unknown",
        final_url=url,
        status_code=0,
        content_type="",
        title="",
        markdown="",
        fetched_at=now_utc(),
        redirects=0,
        raw_bytes=0,
        decompressed_bytes=0,
        truncated=False,
    )
    while attempts <= MAX_RETRIES:
        attempts += 1
        result = fetch_once(url=url, max_tokens=max_tokens, use_playwright=use_playwright)
        result = finalize_result_metadata(result, attempts)
        last = result
        if result.ok:
            # Smart fallback: if content is too short and we haven't tried Playwright yet
            if (enable_fallback and ENABLE_SMART_FALLBACK and not use_playwright
                and sync_playwright is not None
                and (result.shell_only or len(strip_metadata_header(result.markdown)) < MIN_CONTENT_LENGTH)):
                logger.info(
                    f"Content appears shell-only or too short ({len(strip_metadata_header(result.markdown))} chars), "
                    f"falling back to Playwright for {url}"
                )
                playwright_result = finalize_result_metadata(fetch_with_playwright(url, max_tokens), attempts)
                if playwright_result.ok and len(playwright_result.markdown) > len(result.markdown):
                    playwright_result.fallback_used = True
                    logger.info(f"Playwright fallback successful: {len(playwright_result.markdown)} chars vs {len(result.markdown)} chars")
                    return playwright_result
                else:
                    logger.info(f"Playwright fallback did not improve content, using original result")
            return result
        if not result.retryable_error:
            return result
        if attempts <= MAX_RETRIES:
            time.sleep(0.35 * attempts)
    return last


def _fetch_url_impl(url: str, caller_id: str = "default", max_tokens: int = DEFAULT_MAX_TOKENS, use_playwright: bool = False, enable_fallback: bool = True) -> Dict[str, object]:
    """
    Fetch webpage content safely and return markdown for LLM usage.

    Args:
        url: The URL to fetch
        caller_id: Identifier for rate limiting
        max_tokens: Maximum tokens for content truncation
        use_playwright: If True, use Playwright (headless browser) instead of httpx
        enable_fallback: If True, automatically fallback to Playwright if httpx returns insufficient content
    """
    if not allow_request(caller_id):
        return FetchResult(
            ok=False,
            fetch_status="blocked",
            blocked_reason="rate_limited",
            final_url=url,
            status_code=0,
            content_type="",
            title="",
            markdown="",
            fetched_at=now_utc(),
            redirects=0,
            raw_bytes=0,
            decompressed_bytes=0,
            truncated=False,
        ).to_dict()
    return fetch_core(url=url, max_tokens=max_tokens, use_playwright=use_playwright, enable_fallback=enable_fallback).to_dict()


if mcp is not None:

    @mcp.tool()
    def fetch_url(url: str, caller_id: str = "default", max_tokens: int = DEFAULT_MAX_TOKENS, use_playwright: bool = False, enable_fallback: bool = True) -> Dict[str, object]:
        """
        Fetch webpage content and convert to markdown.

        Args:
            url: The URL to fetch
            caller_id: Identifier for rate limiting (default: "default")
            max_tokens: Maximum tokens for content truncation (default: 3000)
            use_playwright: Use headless browser for JS-rendered sites (default: False, slower but handles JS)
            enable_fallback: Auto-fallback to Playwright if content is too short (default: True)

        Returns:
            Dictionary with fetch results including markdown content
        """
        return _fetch_url_impl(url=url, caller_id=caller_id, max_tokens=max_tokens, use_playwright=use_playwright, enable_fallback=enable_fallback)

else:
    def fetch_url(url: str, caller_id: str = "default", max_tokens: int = DEFAULT_MAX_TOKENS, use_playwright: bool = False, enable_fallback: bool = True) -> Dict[str, object]:
        return _fetch_url_impl(url=url, caller_id=caller_id, max_tokens=max_tokens, use_playwright=use_playwright, enable_fallback=enable_fallback)


def run_offline_self_test() -> int:
    tests = [
        ("blocked_localhost", lambda: fetch_core(url="http://127.0.0.1", max_tokens=800).to_dict()),
        (
            "spa_shell_detection",
            lambda: {
                "shell_only": looks_like_spa_shell(
                    "<html><body><div id='root'></div><script src='/assets/app.js'></script></body></html>",
                    "",
                    "text/html; charset=utf-8",
                )
            },
        ),
    ]
    passed = 0
    for name, fn in tests:
        result = fn()
        print(json.dumps({"test": name, "result": result}, ensure_ascii=False))
        if name == "blocked_localhost":
            if result["ok"] is False and str(result["blocked_reason"]).startswith("ip_blocked"):
                passed += 1
        elif name == "spa_shell_detection" and result["shell_only"] is True:
            passed += 1
    print(json.dumps({"summary": f"{passed}/{len(tests)} offline tests passed"}, ensure_ascii=False))
    return 0 if passed == len(tests) else 1


def run_network_self_test() -> int:
    tests = [
        ("normal_public", "https://httpbin.org/get"),
        ("redirect_public", "http://httpbin.org/redirect-to?url=https://httpbin.org/get"),
    ]
    passed = 0
    for name, url in tests:
        result = fetch_core(url=url, max_tokens=800).to_dict()
        print(json.dumps({"test": name, "result": result}, ensure_ascii=False))
        if result["ok"] is True:
            passed += 1
    print(json.dumps({"summary": f"{passed}/{len(tests)} network tests passed"}, ensure_ascii=False))
    return 0 if passed == len(tests) else 1


def run_self_test(include_network: bool = False) -> int:
    offline_code = run_offline_self_test()
    if not include_network:
        return offline_code
    network_code = run_network_self_test()
    if offline_code == 0 and network_code == 0:
        return 0
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="SafeFetch MCP Server V1")
    parser.add_argument("--self-test", action="store_true", help="run offline self-tests and exit")
    parser.add_argument("--self-test-network", action="store_true", help="run offline and network self-tests and exit")
    parser.add_argument("--url", default="", help="single URL fetch debug")
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    args = parser.parse_args()
    if args.self_test:
        return run_self_test()
    if args.self_test_network:
        return run_self_test(include_network=True)
    if args.url:
        print(json.dumps(fetch_core(args.url, max_tokens=args.max_tokens).to_dict(), ensure_ascii=False, indent=2))
        return 0
    if mcp is None:
        print(json.dumps({"ok": False, "error": "mcp package unavailable; requires Python >= 3.10 for MCP mode"}, ensure_ascii=False))
        return 2
    mcp.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
