#!/usr/bin/env python3
"""SafeFetch 抓取工具 - 使用 curl + trafilatura"""

import subprocess
import trafilatura
import json
import ipaddress
from datetime import datetime
from urllib.parse import urlparse

def validate_url(url):
    """SSRF 基础检查 - 使用正确的 IP 范围检查"""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False, "invalid_scheme"
    if parsed.username or parsed.password:
        return False, "userinfo_not_allowed"
    if not parsed.hostname:
        return False, "missing_hostname"
    host = parsed.hostname.lower()

    # 检查 localhost
    if host in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
        return False, "localhost_blocked"

    # 尝试解析为 IP 地址并检查是否为私有/保留地址
    try:
        ip = ipaddress.ip_address(host)
        if (ip.is_private or ip.is_loopback or ip.is_link_local or
            ip.is_multicast or ip.is_reserved or ip.is_unspecified):
            return False, "private_ip_blocked"
    except ValueError:
        # 不是 IP 地址，是域名，继续
        pass

    return True, ""

def fetch_url(url, max_tokens=3000):
    """抓取 URL 并返回结构化结果

    警告：这是一个简化的测试工具，不应用于生产环境。
    它缺少完整的 DNS 验证和重定向安全检查。
    生产环境请使用 server.py。
    """

    # URL 验证
    ok, reason = validate_url(url)
    if not ok:
        return {
            "ok": False,
            "fetch_status": "blocked",
            "blocked_reason": reason,
            "final_url": url,
            "content_markdown": ""
        }

    start = datetime.now()
    try:
        # 使用 curl 抓取（注意：curl -L 会自动跟随重定向，但不会验证重定向目标）
        result = subprocess.run(
            ['curl', '-s', '-L', '--max-time', '15',
             '-A', 'Mozilla/5.0 (compatible; SafeFetch/1.0)',
             url],
            capture_output=True, timeout=20
        )

        fetch_time = (datetime.now() - start).total_seconds()

        if result.returncode != 0:
            stderr_msg = result.stderr.decode('utf-8', errors='replace')[:200] if result.stderr else "Unknown error"
            return {
                "ok": False,
                "fetch_status": "error",
                "blocked_reason": stderr_msg,
                "final_url": url,
                "content_markdown": ""
            }

        # 尝试解码响应
        try:
            html = result.stdout.decode('utf-8', errors='replace')
        except Exception as e:
            return {
                "ok": False,
                "fetch_status": "error",
                "blocked_reason": f"decode_error: {e}",
                "final_url": url,
                "content_markdown": ""
            }

        raw_bytes = len(result.stdout)

        # 提取正文
        text = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=True,
            deduplicate=True
        )

        # 截断
        if text and len(text) > max_tokens * 4:
            text = text[:max_tokens * 4] + "\n\n[内容已截断]"

        return {
            "ok": True,
            "fetch_status": "success",
            "final_url": url,
            "fetch_time_sec": round(fetch_time, 2),
            "raw_bytes": raw_bytes,
            "content_chars": len(text) if text else 0,
            "content_markdown": text or "[无内容]"
        }

    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "fetch_status": "timeout",
            "blocked_reason": "request_timeout",
            "final_url": url,
            "content_markdown": ""
        }
    except Exception as e:
        return {
            "ok": False,
            "fetch_status": "error",
            "blocked_reason": str(e),
            "final_url": url,
            "content_markdown": ""
        }

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        result = fetch_url(sys.argv[1])
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps({"error": "Usage: fetch_test.py <url>"}, ensure_ascii=False))
