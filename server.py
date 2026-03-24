#!/usr/bin/env python3
"""Compatibility entrypoint for the SafeFetch MCP server."""

from safefetch.app import *  # noqa: F401,F403


if __name__ == "__main__":
    raise SystemExit(main())
