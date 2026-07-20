"""Pipeline failure monitor.

Polls #cics-sps-notifications for failed pipeline runs, automatically searches
the troubleshooting channels for a fix, and posts the answer to the output channel.

Triggered by: python3 -m sps_pipeline_bot --monitor

Flow (runs in a loop every POLL_INTERVAL seconds):
  1. Fetch recent messages from #cics-sps-notifications
  2. Identify failure notifications (red colour #f2446f, text contains "failed")
  3. Extract pipeline name and run details
  4. Search troubleshooting channels for matching threads
  5. Post findings to the output channel via webhook
  6. Mark the notification as processed to avoid re-processing
"""

from __future__ import annotations

import json
import os
import time

import httpx
from slack_sdk.errors import SlackApiError

from .config import (
    PIPELINE_FAILURE_COLOUR,
    PIPELINE_NOTIFICATIONS_CHANNEL,
    PIPELINE_NOTIFICATIONS_CHANNEL_ID,
    load_processed_timestamps,
    mark_processed,
)
from .ibmcloud_client import FailedStep, get_failed_steps
from .slack_client import _get_client, search_troubleshooting
from .slack_token_refresh import refresh_slack_env

POLL_INTERVAL = 300  # seconds between polls (5 minutes)


# ---------------------------------------------------------------------------
# Message parsing
# ---------------------------------------------------------------------------

def _extract_blocks_text(msg: dict) -> str:
    """Extract all text from Block Kit attachment blocks."""
    texts = []
    for attachment in msg.get("attachments", []):
        for block in attachment.get("blocks", []):
            t = block.get("text", {})
            if isinstance(t, dict):
                texts.append(t.get("text", ""))
            elif isinstance(t, str):
                texts.append(t)
    return "\n".join(texts)


def _is_failure(msg: dict) -> bool:
    """Return True if this notification message represents a pipeline failure."""
    # Check attachment colour (red = failure)
    for attachment in msg.get("attachments", []):
        if attachment.get("color") == PIPELINE_FAILURE_COLOUR:
            return True
    # Fallback: check text content
    text = _extract_blocks_text(msg).lower()
    return "has failed" in text or "pipeline failed" in text


def _extract_pipeline_info(msg: dict) -> dict:
    """Extract pipeline name, run number, and link from a notification message."""
    import re

    link = ""
    pipeline_text = ""

    # Walk blocks individually — the section block with "pipeline run" is what we want
    for attachment in msg.get("attachments", []):
        for block in attachment.get("blocks", []):
            t = block.get("text", {})
            raw = t.get("text", "") if isinstance(t, dict) else str(t)

            # Pick up the pipeline run line (not the header)
            if "pipeline run" in raw.lower():
                pipeline_text = raw

            # Pick up the link
            link_match = re.search(r"<(https://[^|>]+)\|", raw)
            if link_match:
                link = link_match.group(1)

    # Clean the pipeline text
    clean_text = re.sub(r"<https?://[^>]+>", "", pipeline_text).strip()
    clean_text = re.sub(r"\*Link:\*.*", "", clean_text).strip()

    # Extract pipeline name: "cics-explorer-ce-explorer55 pipeline run #2781 has failed !"
    name_match = re.match(r"^([\w\-]+)\s+pipeline run", clean_text)
    pipeline_name = name_match.group(1) if name_match else "unknown pipeline"

    return {
        "pipeline_name": pipeline_name,
        "text": clean_text,
        "link": link,
    }


# ---------------------------------------------------------------------------
# Webhook posting
# ---------------------------------------------------------------------------

def _post_failure_analysis(
    info: dict,
    search_results: list,
    root_cause: FailedStep | None = None,
) -> None:
    """Post the failure + troubleshooting results to the output webhook channel."""
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        print(f"[monitor] No SLACK_WEBHOOK_URL — would post for: {info['pipeline_name']}")
        return

    pipeline_name = info["pipeline_name"]
    pipeline_text = info["text"]
    pipeline_link = info["link"]

    # Build the message blocks
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🚨 Pipeline Failure Detected"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Pipeline:*\n`{pipeline_name}`"},
                {"type": "mrkdwn", "text": f"*Status:*\n❌ Failed"},
            ],
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": pipeline_text},
        },
    ]

    if pipeline_link:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"<{pipeline_link}|View pipeline run>"},
        })

    # Root cause block — shown when we successfully fetched logs
    if root_cause:
        error_preview = "\n".join(
            f"> `{line[:180]}`" for line in root_cause.error_lines[:4]
        ) or "> _(no error lines captured)_"
        exit_note = f"  (exit code `{root_cause.exit_code}`)" if root_cause.exit_code else ""
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"🔎 *Root Cause — step `{root_cause.step_name}`*{exit_note}\n"
                    f"{error_preview}"
                ),
            },
        })

    blocks.append({"type": "divider"})

    if not search_results:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "🔍 *No matching troubleshooting threads found.*\n"
                    "Check `#scs_code-signing`, `#scs-sast`, `#cd-tekton-users-shared` manually."
                ),
            },
        })
    else:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"🔍 *Found {len(search_results)} related troubleshooting thread(s):*",
            },
        })
        for i, msg in enumerate(search_results[:3], 1):
            channel = msg.channel or "unknown"
            snippet = msg.text[:200].replace("\n", " ")
            reply = ""
            if msg.thread_replies:
                reply = f"\n> 💬 _{msg.thread_replies[0][:150].replace(chr(10), ' ')}_"
            permalink = f"\n> <{msg.permalink}|View thread>" if msg.permalink else ""
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{i}. #{channel}*\n> {snippet}{'...' if len(msg.text) > 200 else ''}{reply}{permalink}",
                },
            })

    payload = {
        "text": f"🚨 Pipeline failure: {pipeline_name}",
        "blocks": blocks,
    }

    resp = httpx.post(
        webhook_url,
        content=json.dumps(payload),
        headers={"Content-Type": "application/json"},
        timeout=10,
    )
    resp.raise_for_status()


# ---------------------------------------------------------------------------
# Main monitor loop
# ---------------------------------------------------------------------------

def _extract_search_query(info: dict) -> str:
    """Build a fallback search query from the pipeline name alone."""
    import re
    name = info["pipeline_name"]
    base = re.sub(r"-(ce|ci|pr|cd)-.*$", "", name)
    return f"{base} pipeline failed"


def poll_once(verbose: bool = True) -> int:
    """Check for new failures once. Returns count of failures processed."""
    def log(msg: str) -> None:
        if verbose:
            print(msg)

    refresh_slack_env()
    client = _get_client()
    processed = load_processed_timestamps()

    try:
        resp = client.conversations_history(channel=PIPELINE_NOTIFICATIONS_CHANNEL_ID, limit=20)
    except SlackApiError as exc:
        log(f"[monitor] Failed to fetch notifications: {exc}")
        return 0

    new_failures = []
    for msg in resp.get("messages", []):
        ts = msg.get("ts", "")
        if ts in processed:
            continue
        if _is_failure(msg):
            new_failures.append(msg)

    if not new_failures:
        log(f"[monitor] No new failures in #{PIPELINE_NOTIFICATIONS_CHANNEL}.")
        mark_processed([msg.get("ts", "") for msg in resp.get("messages", [])
                        if msg.get("ts") not in processed])
        return 0

    log(f"[monitor] Found {len(new_failures)} new failure(s).")

    for msg in new_failures:
        info = _extract_pipeline_info(msg)
        log(f"[monitor] Failure: {info['text'][:100]}")

        # --- Attempt to fetch real error from IBM Cloud logs ---
        root_cause: FailedStep | None = None
        query = _extract_search_query(info)  # fallback query

        run_url = info.get("link", "")
        if run_url and os.environ.get("IBM_CLOUD_API_KEY"):
            try:
                failed_steps = get_failed_steps(run_url)
                if failed_steps:
                    root_cause = failed_steps[0]
                    query = root_cause.search_query
                    log(
                        f"[monitor] Root cause: step={root_cause.step_name!r} "
                        f"exit={root_cause.exit_code!r} "
                        f"error={root_cause.error_summary[:80]!r}"
                    )
                    log(f"[monitor] Search query (from logs): {query!r}")
                else:
                    log("[monitor] Log fetch succeeded but no failed steps found — using fallback query.")
            except Exception as exc:
                log(f"[monitor] ⚠️  Log fetch failed ({exc!r}) — falling back to pipeline-name query.")
        else:
            if not run_url:
                log("[monitor] No run URL found — using fallback query.")
            else:
                log("[monitor] IBM_CLOUD_API_KEY not set — using fallback query.")
            log(f"[monitor] Searching (fallback): {query!r}")

        log(f"[monitor] Searching: {query!r}")

        try:
            results = search_troubleshooting(query=query, max_results=3)
            log(f"[monitor] Found {len(results)} result(s).")
        except Exception as exc:
            log(f"[monitor] Search failed: {exc}")
            results = []

        try:
            _post_failure_analysis(info, results, root_cause=root_cause)
            log(f"[monitor] ✅ Posted analysis for {info['pipeline_name']}")
        except Exception as exc:
            log(f"[monitor] ❌ Failed to post: {exc}")

    # Mark all fetched messages as processed (failures and non-failures)
    all_ts = [m.get("ts", "") for m in resp.get("messages", []) if m.get("ts")]
    mark_processed(all_ts)

    return len(new_failures)


def run_monitor(poll_interval: int = POLL_INTERVAL) -> None:
    """Run the monitor in a continuous loop."""
    print(f"👀 Pipeline failure monitor started.")
    print(f"   Watching: #{PIPELINE_NOTIFICATIONS_CHANNEL}")
    print(f"   Polling every {poll_interval}s. Press Ctrl+C to stop.\n")

    while True:
        try:
            poll_once(verbose=True)
        except KeyboardInterrupt:
            print("\n[monitor] Stopped.")
            break
        except Exception as exc:
            print(f"[monitor] Unexpected error: {exc}")

        time.sleep(poll_interval)
