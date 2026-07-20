"""Slack integration — read channels, search threads, and post webhook alerts.

Authentication for reading: uses a Slack user token (xoxc-) + session cookie (d=...)
extracted from your browser session. No Slack app registration required.

Authentication for posting: uses an incoming webhook URL (SLACK_WEBHOOK_URL).

Environment variables required:
  SLACK_USER_TOKEN   — your xoxc- token from browser DevTools
  SLACK_COOKIE       — your d= cookie value from browser DevTools
  SLACK_WEBHOOK_URL  — incoming webhook URL for posting alerts
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

import httpx
from typing import Literal

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from .config import (
    ANNOUNCEMENT_CHANNEL_IDS,
    ANNOUNCEMENT_CHANNELS,
    TROUBLESHOOTING_CHANNELS,
    load_processed_timestamps,
    mark_processed,
)
from .slack_token_refresh import refresh_slack_env


@dataclass
class SlackMessage:
    channel: str
    channel_type: Literal["announcement", "troubleshooting"]
    ts: str
    text: str
    permalink: str
    username: str
    thread_replies: list[str] = field(default_factory=list)


def _get_client() -> WebClient:
    refresh_slack_env()
    token = os.environ.get("SLACK_USER_TOKEN")
    if not token:
        raise RuntimeError(
            "SLACK_USER_TOKEN environment variable is not set.\n"
            "See SLACK-SETUP.md for how to extract your user token from the browser."
        )
    cookie = os.environ.get("SLACK_COOKIE", "")
    headers = {"Cookie": f"d={cookie}"} if cookie else {}
    return WebClient(token=token, headers=headers, timeout=10)


def _resolve_channel_id(channel_name: str) -> str | None:
    """Look up a channel ID from the hardcoded registry (conversations.list is blocked on enterprise Slack)."""
    return ANNOUNCEMENT_CHANNEL_IDS.get(channel_name)


def fetch_announcement_messages(limit: int = 20) -> list[SlackMessage]:
    """
    Fetch the most recent *unprocessed* messages from the three announcement channels.
    Marks fetched messages as processed so they won't be returned again on the next call.
    """
    client = _get_client()
    processed = load_processed_timestamps()
    results: list[SlackMessage] = []

    for channel_name in ANNOUNCEMENT_CHANNELS:
        channel_id = _resolve_channel_id(channel_name)
        if channel_id is None:
            continue
        try:
            history = client.conversations_history(channel=channel_id, limit=limit)
        except SlackApiError:
            continue

        for msg in history.get("messages", []):
            ts = msg.get("ts", "")
            if ts in processed or not msg.get("text"):
                continue

            try:
                pl = client.chat_getPermalink(channel=channel_id, message_ts=ts)
                permalink = pl.get("permalink", "")
            except SlackApiError:
                permalink = ""

            username = ""
            if user_id := msg.get("user"):
                try:
                    ui = client.users_info(user=user_id)
                    username = ui["user"].get("real_name") or ui["user"].get("name", "")
                except SlackApiError:
                    pass

            results.append(
                SlackMessage(
                    channel=channel_name,
                    channel_type="announcement",
                    ts=ts,
                    text=msg["text"],
                    permalink=permalink,
                    username=username,
                )
            )

    new_ts = [m.ts for m in results]
    if new_ts:
        mark_processed(new_ts)

    return results


def search_troubleshooting(query: str, max_results: int = 10) -> list[SlackMessage]:
    """
    Search the five troubleshooting channels for threads matching *query*.
    Uses Slack search.messages API with your user token — read-only, no write access needed.
    Returns messages with their thread replies so Bob can synthesise a solution.
    """
    client = _get_client()

    channel_filter = " ".join(f"in:{ch}" for ch in TROUBLESHOOTING_CHANNELS)
    full_query = f"{channel_filter} {query}"

    try:
        resp = client.search_messages(query=full_query, count=max_results, sort="score")
    except SlackApiError as exc:
        raise RuntimeError(f"Slack search failed: {exc.response['error']}") from exc

    matches = resp.get("messages", {}).get("matches", [])
    results: list[SlackMessage] = []

    for match in matches:
        channel_name = match.get("channel", {}).get("name", "")
        channel_id = match.get("channel", {}).get("id", "")
        ts = match.get("ts", "")
        text = match.get("text", "")
        permalink = match.get("permalink", "")
        username = match.get("username", "")

        thread_replies: list[str] = []
        if channel_id and ts:
            try:
                tr = client.conversations_replies(channel=channel_id, ts=ts)
                thread_replies = [
                    r.get("text", "")
                    for r in tr.get("messages", [])[1:]
                    if r.get("text")
                ]
            except SlackApiError:
                pass

        results.append(
            SlackMessage(
                channel=channel_name,
                channel_type="troubleshooting",
                ts=ts,
                text=text,
                permalink=permalink,
                username=username,
                thread_replies=thread_replies,
            )
        )

    return results


# ---------------------------------------------------------------------------
# Webhook posting (outbound — no user token needed, uses SLACK_WEBHOOK_URL)
# ---------------------------------------------------------------------------

def post_webhook_alert(
    repo: str,
    summary: str,
    suggested_change: str,
    change_description: str,
    pr_url: str | None,
    announcement_permalink: str,
) -> None:
    """Post a repo-change alert via an incoming webhook URL."""
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
                    {"type": "mrkdwn", "text": f"<{announcement_permalink}|View original announcement>"}
                ],
            },
        ],
    }

    resp = httpx.post(webhook_url, content=json.dumps(payload), headers={"Content-Type": "application/json"})
    resp.raise_for_status()
