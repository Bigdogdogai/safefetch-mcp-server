# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog and this project follows Semantic Versioning.

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

