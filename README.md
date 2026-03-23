# SafeFetch MCP Server

Secure web fetch for local AI agents.  
A security-focused web fetch service for local AI agents.

> **License**: AGPL-3.0 (dual-license model, see `COMMERCIAL.md`)  
> **Feedback**: GitHub `Issues` / `Pull Requests`

## Why SafeFetch

Think of it as a "digital security guard" for AI web access. It focuses on three things:

- **Block internal targets**: default SSRF guardrails (scheme checks, DNS/IP validation, per-hop redirect validation)
- **Prevent resource blow-ups**: raw/decompressed size limits to stop oversized payloads and decompression bombs
- **Improve troubleshooting**: stable JSON contract for automatic agent decisions and retry control

In one line: safer, more stable, and more controllable web fetching for AI agents.

## Highlights

- SSRF defenses: scheme guard, DNS/IP checks, redirect re-validation
- Resource guardrails: raw/decompressed byte limits + MIME allowlist
- Stable output: flat JSON contract for automation
- OpenClaw ready: skill templates + `mcporter` examples
- Beginner-friendly: one-command bootstrap scripts

## Quick Start

> `~/` and `<YOUR_PATH>` both represent your local clone path. Replace them with your actual location.

### 1) Install

```bash
cd ~/safefetch-mcp-server
bash bootstrap.sh
```

### 2) Start

```bash
bash start-mcp.sh
```

### 3) Self-test (optional)

```bash
source .venv/bin/activate
python server.py --self-test
```

If your network resolves public domains into restricted ranges, use:

```bash
WEBFETCH_ALLOW_CIDRS=198.18.0.0/15 python server.py --self-test
```

## OpenClaw Integration

1. Merge `examples/openclaw.skills-entry.sample.json` into `~/.openclaw/openclaw.json` (`skills.entries`).
2. Copy skill file:

```bash
mkdir -p ~/.openclaw/skills/safefetch-mcp-v1
cp ~/safefetch-mcp-server/examples/SKILL.local.md ~/.openclaw/skills/safefetch-mcp-v1/SKILL.md
```

3. Hello world:

```bash
openclaw agent --local --message "Use safefetch-mcp-v1 to fetch https://httpbin.org/get. Output strict JSON only (no markdown code fences) with fields: ok, fetch_status, blocked_reason, final_url, attempts, retryable_error, security_blocked, title."
```

## `mcporter` Direct Call

```bash
mcporter call --stdio "env WEBFETCH_ALLOW_CIDRS=${WEBFETCH_ALLOW_CIDRS:-} <YOUR_PATH>/safefetch-mcp-server/.venv/bin/python <YOUR_PATH>/safefetch-mcp-server/server.py" fetch_url url=https://example.com caller_id=openclaw-agent max_tokens=3000
```

## JSON Response Contract

These fields form a stable JSON response contract for agent status checks, retry decisions, and troubleshooting:

- `ok`
- `fetch_status`
- `blocked_reason`
- `final_url`
- `status_code`
- `content_type`
- `title`
- `content_markdown`
- `content_chars`
- `redirects`
- `raw_bytes`
- `decompressed_bytes`
- `attempts`
- `retried`
- `retryable_error`
- `last_error`
- `security_blocked`

## Environment Variable

- `WEBFETCH_ALLOW_CIDRS` (optional): comma-separated CIDR allowlist for special network environments.

## Project Files

```text
safefetch-mcp-server/
  server.py
  requirements.txt
  bootstrap.sh
  start-mcp.sh
  examples/
```

## Security

This project is intended for defensive, local-agent web fetching use cases.  
Do not disable SSRF and resource guardrails in production.  
For vulnerability reporting, see `SECURITY.md`.

## License

- Open source: `GNU AGPL v3.0` (`LICENSE`)
- Commercial terms: `COMMERCIAL.md`
