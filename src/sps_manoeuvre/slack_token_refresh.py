"""Slack token resolution for SPS Manoeuvre.

Tokens (SLACK_USER_TOKEN / SLACK_COOKIE) are supplied by the user during
``sps-manoeuvre --setup`` and stored in .bob/mcp.json as environment variables.
This module simply validates that they are present at runtime.

Usage:
    from sps_manoeuvre.slack_token_refresh import refresh_slack_env
    refresh_slack_env()   # raises if tokens are missing
"""

from __future__ import annotations

import os
import warnings


_refreshed = False


def bootstrap() -> None:
    """No-op kept for backwards compatibility with --bootstrap CLI flag."""
    print("ℹ️  Token bootstrapping is no longer required.")
    print("   Run 'sps-manoeuvre --setup' to configure SLACK_USER_TOKEN and SLACK_COOKIE.")


def refresh_slack_env() -> None:
    """Verify SLACK_USER_TOKEN and SLACK_COOKIE are present in the environment.

    Tokens must be configured via ``sps-manoeuvre --setup``, which stores them
    in .bob/mcp.json so they are injected as environment variables at runtime.

    Falls back with a warning (non-fatal) if tokens are absent, so that
    callers that don't need Slack reading still work (e.g. webhook-only usage).
    """
    global _refreshed
    if _refreshed:
        return

    if os.environ.get("SLACK_USER_TOKEN") and os.environ.get("SLACK_COOKIE"):
        _refreshed = True
        return

    warnings.warn(
        "SLACK_USER_TOKEN or SLACK_COOKIE is not set.\n"
        "Run 'sps-manoeuvre --setup' to configure your Slack tokens.",
        stacklevel=2,
    )
