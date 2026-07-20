"""Automated monitors — announcement runner and pipeline failure watcher.

Two modes, both triggered from __main__.py:

  --run      Fetch new SPS announcements → classify → scan repos → post alerts.
             Safe to schedule (cron/launchd). Runs once and exits.

  --monitor  Poll #cics-sps-notifications for pipeline failures → fetch IBM Cloud
             logs → extract BUILD FAILURE context → search SPS channels if it's an
             SPS/infra issue → post findings to the output channel.
             Runs continuously (polls every 5 minutes).
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field

import httpx
from slack_sdk.errors import SlackApiError

from .config import (
    PIPELINE_FAILURE_COLOUR,
    PIPELINE_NOTIFICATIONS_CHANNEL,
    PIPELINE_NOTIFICATIONS_CHANNEL_ID,
    load_processed_timestamps,
    load_repos,
    mark_processed,
)
from .github_client import scan_repos
from .ibmcloud_client import FailedStep, get_failed_steps
from .slack_client import (
    SlackMessage,
    _get_client,
    fetch_announcement_messages,
    post_webhook_alert,
    search_troubleshooting,
)
from .slack_token_refresh import refresh_slack_env

POLL_INTERVAL = 300  # seconds between failure-monitor polls (5 minutes)


# ===========================================================================
# PART 1 — Announcement runner  (--run)
# ===========================================================================

@dataclass
class _Classification:
    action_required: bool
    summary: str
    file_patterns: list[str] = field(default_factory=list)
    suggested_change: str = ""


_RULES: list[tuple[list[str], _Classification]] = [
    (
        ["mend sca", "opt-in-mend-sca", "mend sca cli"],
        _Classification(
            action_required=True,
            summary="Migrate from Mend UA scan to Mend SCA CLI scan",
            file_patterns=[".pipeline-scan-config.yaml", ".pipeline-config*.yaml"],
            suggested_change=(
                "Add `opt-in-mend-sca` env var set to `1` and `mend-user-email` "
                "to the compliance-checks step in your pipeline scan config."
            ),
        ),
    ),
    (
        ["versioned base image", "pipeline-base-ubi:", "base image"],
        _Classification(
            action_required=True,
            summary="Versioned base image update available",
            file_patterns=[".pipeline-config*.yaml", ".pipeline-scan-config.yaml"],
            suggested_change=(
                "If you pin a specific version tag (e.g. pipeline-base-ubi:3.x), "
                "update to the latest version. If you use :latest, no action needed."
            ),
        ),
    ),
    (
        ["detect-secrets", "secrets baseline", ".secrets.baseline"],
        _Classification(
            action_required=True,
            summary="detect-secrets configuration change required",
            file_patterns=[".pipeline-config*.yaml", ".pipeline-scan-config.yaml", ".secrets.baseline"],
            suggested_change="Update your detect-secrets step or .secrets.baseline file as described in the announcement.",
        ),
    ),
    (
        ["garasign", "code sign", "csso-image-sign", "ciso-sign"],
        _Classification(
            action_required=True,
            summary="Code signing configuration update required",
            file_patterns=[".pipeline-config*.yaml", "GaraSign", "sign"],
            suggested_change="Update your code signing step configuration as described in the announcement.",
        ),
    ),
    (
        ["get_env", "secure values", "pipeline environment"],
        _Classification(
            action_required=True,
            summary="Pipeline env variable retrieval method changing",
            file_patterns=[".pipeline-config*.yaml", ".pipeline-scan-config.yaml", "scripts/"],
            suggested_change="Review use of get_env for secure values in your pipeline scripts.",
        ),
    ),
    (
        ["zap v1", "dast-zap", "zap scan"],
        _Classification(
            action_required=True,
            summary="ZAP v1 dynamic scan deprecated — migrate to ZAP v2",
            file_patterns=[".pipeline-config*.yaml"],
            suggested_change="Remove dast-zap v1 configuration. ZAP v2 is now the only supported option.",
        ),
    ),
    (
        ["cra deprecation", "cra is deprecated", "cra onboarding"],
        _Classification(
            action_required=True,
            summary="CRA deprecated — migrate to Mend SCA",
            file_patterns=[".pipeline-config*.yaml", ".pipeline-scan-config.yaml"],
            suggested_change="Migrate to Mend SCA following the onboarding guidance in the announcement.",
        ),
    ),
    (
        ["pipeline release:", "release notes", "backout plan", "v11.", "v10."],
        _Classification(action_required=False, summary="Pipeline release notes (informational)"),
    ),
    (
        ["i s s u e", "describe the issue", "facing the below issue", "please do not post"],
        _Classification(action_required=False, summary="Support question or channel notice (no action needed)"),
    ),
]


def _classify(message: SlackMessage) -> _Classification:
    text_lower = message.text.lower()
    for keywords, classification in _RULES:
        if any(kw in text_lower for kw in keywords):
            return classification
    return _Classification(action_required=False, summary="Unrecognised announcement — review manually")


def run_pipeline(verbose: bool = True) -> None:
    """Fetch announcements → classify → scan repos → post webhook alerts."""

    def log(msg: str) -> None:
        if verbose:
            print(msg)

    log("🔄 Refreshing Slack tokens...")
    refresh_slack_env()

    log("📡 Fetching announcements...")
    messages = fetch_announcement_messages(limit=20)

    if not messages:
        log("✅ No new announcements.")
        return

    log(f"📬 Found {len(messages)} new announcement(s).")

    repos = [r["repo"] for r in load_repos()]
    if not repos:
        log("⚠️  No repos in watchlist. Add repos to repos.json first.")
        return

    for msg in messages:
        classification = _classify(msg)
        log(f"\n── [{msg.channel}] {msg.text[:80].strip()}...")
        log(f"   Category: {classification.summary}")

        if not classification.action_required or not classification.file_patterns:
            log("   → Skipping (no action required or no file patterns).")
            continue

        log(f"   → Scanning {len(repos)} repos for {classification.file_patterns}...")
        matches = scan_repos(repos=repos, file_patterns=classification.file_patterns)

        if not matches:
            log("   → No matching files found in any repo.")
            continue

        log(f"   → Found matches in {len(matches)} repo(s): {[m.repo for m in matches]}")

        for match in matches:
            log(f"   → Posting alert for {match.repo}...")
            try:
                post_webhook_alert(
                    repo=match.repo,
                    summary=classification.summary,
                    suggested_change=classification.suggested_change,
                    change_description=f"Affected files: {', '.join(match.matched_files)}",
                    pr_url=None,
                    announcement_permalink=msg.permalink or "",
                )
                log(f"   ✅ Alert posted for {match.repo}")
            except Exception as exc:
                log(f"   ❌ Failed to post alert for {match.repo}: {exc}")

    log("\n✅ Pipeline run complete.")


# ===========================================================================
# PART 2 — Pipeline failure monitor  (--monitor)
# ===========================================================================

def _is_failure(msg: dict) -> bool:
    """Return True if this Slack notification represents a pipeline failure."""
    for attachment in msg.get("attachments", []):
        if attachment.get("color") == PIPELINE_FAILURE_COLOUR:
            return True
    texts = []
    for attachment in msg.get("attachments", []):
        for block in attachment.get("blocks", []):
            t = block.get("text", {})
            texts.append(t.get("text", "") if isinstance(t, dict) else str(t))
    combined = "\n".join(texts).lower()
    return "has failed" in combined or "pipeline failed" in combined


def _extract_pipeline_info(msg: dict) -> dict:
    """Extract pipeline name, description text, and run URL from a notification message."""
    link = ""
    pipeline_text = ""

    for attachment in msg.get("attachments", []):
        for block in attachment.get("blocks", []):
            t = block.get("text", {})
            raw = t.get("text", "") if isinstance(t, dict) else str(t)
            if "pipeline run" in raw.lower():
                pipeline_text = raw
            link_match = re.search(r"<(https://[^|>]+)\|", raw)
            if link_match:
                link = link_match.group(1)

    clean_text = re.sub(r"<https?://[^>]+>", "", pipeline_text).strip()
    clean_text = re.sub(r"\*Link:\*.*", "", clean_text).strip()

    name_match = re.match(r"^([\w\-]+)\s+pipeline run", clean_text)
    pipeline_name = name_match.group(1) if name_match else "unknown pipeline"

    return {"pipeline_name": pipeline_name, "text": clean_text, "link": link}


def _post_failure_analysis(
    info: dict,
    search_results: list,
    root_cause: FailedStep | None = None,
) -> None:
    """Post failure + troubleshooting findings to the output webhook channel."""
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        print(f"[monitor] No SLACK_WEBHOOK_URL — would post for: {info['pipeline_name']}")
        return

    blocks: list[dict] = [
        {"type": "header", "text": {"type": "plain_text", "text": "🚨 Pipeline Failure Detected"}},
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Pipeline:*\n`{info['pipeline_name']}`"},
                {"type": "mrkdwn", "text": "*Status:*\n❌ Failed"},
            ],
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": info["text"]}},
    ]

    if info["link"]:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"<{info['link']}|View pipeline run>"}})

    if root_cause and root_cause.is_build_failure and root_cause.error_lines:
        error_preview = "\n".join(f"> `{line[:180]}`" for line in root_cause.error_lines[:6])
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"🔎 *BUILD FAILURE in step `{root_cause.step_name}`*\n{error_preview}"},
        })

    blocks.append({"type": "divider"})

    is_sps_issue = root_cause is None or not root_cause.is_build_failure
    if not search_results and is_sps_issue:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": (
                "🔍 *No matching troubleshooting threads found.*\n"
                "Check `#scs_code-signing`, `#scs-sast`, `#cd-tekton-users-shared` manually."
            )},
        })
    elif search_results:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"🔍 *Found {len(search_results)} related troubleshooting thread(s):*"},
        })
        for i, msg in enumerate(search_results[:3], 1):
            channel = msg.channel or "unknown"
            snippet = msg.text[:200].replace("\n", " ")
            reply = f"\n> 💬 _{msg.thread_replies[0][:150].replace(chr(10), ' ')}_" if msg.thread_replies else ""
            permalink = f"\n> <{msg.permalink}|View thread>" if msg.permalink else ""
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*{i}. #{channel}*\n> {snippet}{'...' if len(msg.text) > 200 else ''}{reply}{permalink}"},
            })

    resp = httpx.post(
        webhook_url,
        content=json.dumps({"text": f"🚨 Pipeline failure: {info['pipeline_name']}", "blocks": blocks}),
        headers={"Content-Type": "application/json"},
        timeout=10,
    )
    resp.raise_for_status()


def poll_once(verbose: bool = True) -> int:
    """Check for new pipeline failures once. Returns count of failures processed."""
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

    new_failures = [
        msg for msg in resp.get("messages", [])
        if msg.get("ts") not in processed and _is_failure(msg)
    ]

    if not new_failures:
        log(f"[monitor] No new failures in #{PIPELINE_NOTIFICATIONS_CHANNEL}.")
        mark_processed([m.get("ts", "") for m in resp.get("messages", []) if m.get("ts") not in processed])
        return 0

    log(f"[monitor] Found {len(new_failures)} new failure(s).")

    for msg in new_failures:
        info = _extract_pipeline_info(msg)
        log(f"[monitor] Failure: {info['text'][:100]}")

        root_cause: FailedStep | None = None
        query = re.sub(r"-(ce|ci|pr|cd)-.*$", "", info["pipeline_name"]) + " pipeline failed"

        run_url = info.get("link", "")
        if run_url and os.environ.get("IBM_CLOUD_API_KEY"):
            try:
                failed_steps = get_failed_steps(run_url)
                if failed_steps:
                    root_cause = failed_steps[0]
                    if root_cause.is_build_failure:
                        log(f"[monitor] BUILD FAILURE in step {root_cause.step_name!r}")
                        log(f"[monitor] Context: {root_cause.error_summary[:120]!r}")
                    else:
                        log("[monitor] No BUILD FAILURE — treating as SPS/infra issue.")
                    query = root_cause.search_query
            except Exception as exc:
                log(f"[monitor] ⚠️  Log fetch failed ({exc!r}) — using fallback query.")
        else:
            log(f"[monitor] {'No run URL' if not run_url else 'No IBM_CLOUD_API_KEY'} — using fallback query.")

        is_sps_issue = root_cause is None or not root_cause.is_build_failure
        if is_sps_issue:
            log(f"[monitor] SPS/infra issue — searching: {query!r}")
            try:
                results = search_troubleshooting(query=query, max_results=3)
                log(f"[monitor] Found {len(results)} result(s).")
            except Exception as exc:
                log(f"[monitor] Search failed: {exc}")
                results = []
        else:
            log("[monitor] Build failure — skipping SPS channel search.")
            results = []

        try:
            _post_failure_analysis(info, results, root_cause=root_cause)
            log(f"[monitor] ✅ Posted analysis for {info['pipeline_name']}")
        except Exception as exc:
            log(f"[monitor] ❌ Failed to post: {exc}")

    mark_processed([m.get("ts", "") for m in resp.get("messages", []) if m.get("ts")])
    return len(new_failures)


def run_monitor(poll_interval: int = POLL_INTERVAL) -> None:
    """Run the pipeline failure monitor in a continuous loop."""
    print("👀 Pipeline failure monitor started.")
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
