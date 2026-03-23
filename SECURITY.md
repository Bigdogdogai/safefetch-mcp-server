# Security Policy

## Supported Versions

This project is currently maintained on the latest release branch.

| Version | Supported |
| ------- | --------- |
| latest  | yes       |

## Reporting a Vulnerability

If you discover a security issue, please report it privately.

- Preferred contact: use GitHub private vulnerability reporting (Security Advisory) if enabled
- Fallback contact: open a GitHub Issue with minimal details and request private follow-up
- Include: affected version, reproduction steps, expected behavior, actual behavior, and logs (if safe)
- Do not post exploit details in public issues before a fix is available

## Response Targets

- Initial response: within 72 hours
- Triage decision: within 7 days
- Patch or mitigation target: within 30 days for high-severity issues

## Scope

Security-sensitive areas include:

- SSRF controls (scheme, DNS/IP checks, redirect hop validation)
- Resource guardrails (raw/decompressed size limits)
- Output contract integrity (stable JSON fields and error semantics)
- Dependency vulnerabilities

## Disclosure Process

1. Receive private report
2. Reproduce and assess severity
3. Prepare patch and tests
4. Release fix and publish advisory notes

