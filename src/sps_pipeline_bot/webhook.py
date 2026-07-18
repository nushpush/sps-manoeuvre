"""Webhook integration — post alerts via the existing notification Slack app.

The existing notification app accepts incoming webhook calls, so no new
Slack app registration is needed for sending alerts.

Environment variables required:
  SLACK_WEBHOOK_URL  — the incoming webhook URL from your existing notification app
"""

from __future__ import annotations

import json
import os

import httpx


def post_webhook_alert(
    repo: str,
    summary: str,
    suggested_change: str,
    change_description: str,
    pr_url: str | None,
    announcement_permalink: str,
) -> None:
    """Post a repo-change alert via the existing notification app's webhook."""
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        raise RuntimeError(
            "SLACK_WEBHOOK_URL environment variable is not set.\n"
            "Set it to the incoming webhook URL from your existing notification app."
        )

    pr_line = f"<{pr_url}|View PR>" if pr_url else "PR not yet created — use `create-pr` to raise one"

    payload = {
        "text": f"SPS Pipeline change required in `{repo}`",
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "🔧 SPS Pipeline Change Required"},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Repository:*\n`{repo}`"},
                    {"type": "mrkdwn", "text": f"*Change:*\n{summary}"},
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*What to do:* {suggested_change}\n\n"
                        f"*Applied change:* {change_description}\n\n"
                        f"*PR:* {pr_line}"
                    ),
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"<{announcement_permalink}|View original announcement>",
                    }
                ],
            },
        ],
    }

    resp = httpx.post(webhook_url, content=json.dumps(payload), headers={"Content-Type": "application/json"})
    resp.raise_for_status()
