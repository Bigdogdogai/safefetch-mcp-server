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
- Clear render boundary: SSR/SSG works over `httpx`, pure SPA usually needs Playwright
- OpenClaw ready: skill templates + `mcporter` examples
- Beginner-friendly: one-command bootstrap scripts

## Render Model Boundary

SafeFetch has two fetch modes:

- `httpx` mode: fast and safer by default; best for SSR, SSG, and traditional server-rendered sites
- `Playwright` mode: slower headless browser mode for JavaScript-rendered pages and pure SPA sites

What this means in practice:

- `react.dev`-style SSR/SSG pages usually work in `httpx` mode because the HTML already contains article text
- pure React/Vue SPA pages often return only an app shell such as `<div id="root"></div>` in `httpx` mode
- when SafeFetch detects a shell-only HTML response, it marks `shell_only=true`, `js_required=true`
- if `enable_fallback=true` and Playwright is available, SafeFetch automatically retries with Playwright

## Prerequisites

Before installation, make sure these dependencies exist on your machine:

- Python `>= 3.10` (recommended: `3.11`)
- `mcporter` available in your `PATH`
- OpenClaw with local agent/skills support

Quick checks:

```bash
python3 --version
which mcporter
mcporter --help
openclaw --version
```

If `mcporter` is missing, install it first (example options):

```bash
pip install mcporter
# or
uv pip install mcporter
```

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

### 3) Offline self-test (recommended)

```bash
source .venv/bin/activate
python -m safefetch --self-test
```

### 4) Network self-test (optional)

```bash
source .venv/bin/activate
python -m safefetch --self-test-network
```

If your network resolves public domains into restricted ranges, use:

```bash
WEBFETCH_ALLOW_CIDRS=198.18.0.0/15 python -m safefetch --self-test-network
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
mcporter call --stdio "env WEBFETCH_ALLOW_CIDRS=${WEBFETCH_ALLOW_CIDRS:-} <YOUR_PATH>/safefetch-mcp-server/.venv/bin/python -m safefetch" fetch_url url=https://example.com caller_id=openclaw-agent max_tokens=3000
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
- `render_mode`
- `fallback_used`
- `shell_only`
- `js_required`

### Render Interpretation Fields

- `render_mode`: `httpx` or `playwright`
- `fallback_used`: `true` when the final successful result came from automatic Playwright fallback
- `shell_only`: `true` when the fetched HTML looks like a client-side SPA shell instead of real page content
- `js_required`: `true` when JavaScript rendering is likely required to get meaningful page content

## Environment Variable

- `WEBFETCH_ALLOW_CIDRS` (optional): comma-separated CIDR allowlist for special network environments.

## Troubleshooting

### Skill does not load in OpenClaw

Most common cause: `mcporter` is not installed or not in `PATH`.

```bash
which mcporter
```

If empty, install `mcporter`, then restart OpenClaw and run:

```bash
openclaw skills list
```

### DNS/IP gets blocked unexpectedly

In some network environments, public domains may resolve into restricted ranges.
Use an allowlist CIDR for those environments:

```bash
WEBFETCH_ALLOW_CIDRS=198.18.0.0/15 python -m safefetch --self-test-network
```

### Fetch succeeds but page content is empty or extremely short

Most common cause: the target is a pure SPA site and `httpx` only received the client shell.

Check these fields in the JSON response:

- `render_mode`
- `fallback_used`
- `shell_only`
- `js_required`

Typical interpretation:

- `render_mode=httpx`, `shell_only=false`: regular static/SSR/SSG fetch
- `render_mode=httpx`, `shell_only=true`, `js_required=true`: HTML shell only; use Playwright
- `render_mode=playwright`, `fallback_used=true`: automatic browser fallback was used successfully

### Python command not found inside bootstrap script

Create the venv manually and rerun:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

## Project Files

```text
safefetch-mcp-server/
  server.py            # compatibility entrypoint
  safefetch/           # package implementation
  requirements.txt
  bootstrap.sh
  start-mcp.sh
  test_server.py
  RELEASE.md
  examples/
```

## Release Workflow

- Offline verification: `python -m safefetch --self-test`
- Optional network verification: `python -m safefetch --self-test-network`
- Unit tests: `python -m unittest test_server.py`
- Release notes template: `RELEASE.md`

## Security

This project is intended for defensive, local-agent web fetching use cases.  
Do not disable SSRF and resource guardrails in production.  
For vulnerability reporting, see `SECURITY.md`.

## License

- Open source: `GNU AGPL v3.0` (`LICENSE`)
- Commercial terms: `COMMERCIAL.md`
