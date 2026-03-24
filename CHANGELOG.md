# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog and this project follows Semantic Versioning.

## [Unreleased]

### Added
- **Package Layout**: Added `safefetch/` package with `python -m safefetch` entrypoint
- **CI Workflow**: GitHub Actions now runs syntax checks, offline self-test, and unit tests on Python 3.10 and 3.11
- **Playwright Support**: Optional headless browser support for JS-rendered websites
  - New parameter `use_playwright`: Force use of Playwright (headless browser)
  - New parameter `enable_fallback`: Enable smart fallback to Playwright when content is insufficient
- **Smart Fallback Mechanism**: Automatically switches to Playwright when httpx returns content shorter than 200 chars
- **SPA Shell Detection**: `httpx` responses that look like empty client-side shells now set:
  - `shell_only`
  - `js_required`
  - `render_mode`
  - `fallback_used`
- **Performance Optimization**: Configurable timeout and wait strategies for Playwright
  - Playwright timeout: 30 seconds
  - Waits for `networkidle` state before extracting content
  - Minimum content length for fallback trigger: 200 characters

### Changed
- `server.py` is now a compatibility entrypoint that forwards to the packaged implementation
- Bootstrap and start scripts now use `python -m safefetch`
- Self-test is split into offline and network modes so local verification does not depend on external DNS/network access
- Updated `fetch_url()` MCP tool to accept `use_playwright` and `enable_fallback` parameters
- Enhanced `fetch_core()` with smart fallback logic
- Added `fetch_with_playwright()` function for browser-based fetching
- Playwright now enforces request-level URL validation for subresources
- Playwright now treats `4xx/5xx` responses as failures instead of successful fetches
- Documentation now clearly distinguishes SSR/SSG support from pure SPA limitations

### Technical Details
- Smart fallback can be disabled globally via `ENABLE_SMART_FALLBACK` constant
- Playwright validates URLs and redirects with same security checks as httpx
- Browser-based fetching includes redirect validation to prevent SSRF bypass
- Automatic fallback now also triggers on explicit shell-only detection, not only short content length

## [1.0.0] - 2026-03-23

### Added

- Initial open-source release for `SafeFetch MCP Server`
- Hardened SSRF protection:
  - URL scheme and host validation
  - DNS/IP resolution checks
  - Redirect hop re-validation
  - HTTPS downgrade blocking
  - localhost and local network blocking (including IPv6 local/link-local)
- Resource protection:
  - Raw response size cap
  - Decompressed size cap
  - MIME allowlist and encoding guard
- Agent-friendly output contract:
  - Stable flat JSON fields
  - Retry observability fields (`attempts`, `retried`, `retryable_error`, `last_error`, `security_blocked`)
- Token-aware markdown truncation support
- MCP tool endpoint (`fetch_url`) and local self-test mode
- Example skill template under `examples/SKILL-sample.md`
