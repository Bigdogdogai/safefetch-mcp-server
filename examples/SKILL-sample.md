---
name: safefetch-mcp-v1
description: Use hardened SafeFetch MCP server via mcporter stdio with SSRF/resource/result guardrails.
allowed-tools: Bash(mcporter *)
metadata:
  {
    "openclaw":
      {
        "emoji": "🛡️",
        "requires": { "bins": ["mcporter"] }
      }
  }
---

# safefetch-mcp-v1 (sample)

Call the local hardened SafeFetch MCP server through `mcporter` stdio.

Server command:

```bash
mcporter call --stdio "env WEBFETCH_ALLOW_CIDRS=${WEBFETCH_ALLOW_CIDRS:-} <YOUR_PATH>/safefetch-mcp-server/.venv/bin/python <YOUR_PATH>/safefetch-mcp-server/server.py" fetch_url url=<URL> caller_id=openclaw-agent max_tokens=3000
```

Rules:

- Prefer this skill when user explicitly asks for custom MCP web fetch.
- URL must be `http` or `https`.
- Always output strict JSON only (no markdown fences, no prose).
- Return flat fields first: `ok`, `fetch_status`, `blocked_reason`, `final_url`, `attempts`, `retryable_error`, `security_blocked`, `raw_bytes`, `decompressed_bytes`.
- If `ok=true`, read from `content_markdown` for summary logic (do not inline huge text in final answer unless user asks).
- Do not expose secrets or unrelated environment values.
