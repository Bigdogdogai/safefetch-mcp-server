# Release Notes

## v1.1.0

This release turns SafeFetch into a more publishable MCP package with clearer render semantics, safer Playwright behavior, and a cleaner release workflow.

### Highlights

- Added packaged entrypoint: `python -m safefetch`
- Kept `server.py` as a compatibility entrypoint for existing integrations
- Added explicit render interpretation fields:
  - `render_mode`
  - `fallback_used`
  - `shell_only`
  - `js_required`
- Improved smart fallback for pure SPA shell pages
- Hardened Playwright mode:
  - request-level URL validation for subresources
  - HTTP error responses are no longer treated as successful fetches
  - MIME and content-size checks now apply there as well
- Split self-test into:
  - offline self-test: `python -m safefetch --self-test`
  - network self-test: `python -m safefetch --self-test-network`
- Added GitHub Actions CI for syntax checks, offline self-test, and unit tests

### Upgrade Notes

- Preferred stdio command now uses:
  - `.venv/bin/python -m safefetch`
- Existing `server.py` invocations still work
- Bootstrap now runs offline self-tests by default instead of external network checks

### Recommended Post-Release Checks

1. Rebuild the virtual environment with Python 3.10 or 3.11.
2. Run `python -m safefetch --self-test`.
3. If your network allows it, run `python -m safefetch --self-test-network`.
4. Verify one SSR page and one known SPA page through your MCP client.
