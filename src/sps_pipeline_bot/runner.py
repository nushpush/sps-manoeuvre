"""Headless runner — full automated pipeline with no Bob/LLM required.

Triggered by: python3 -m sps_pipeline_bot --run

Flow:
  1. Auto-refresh Slack tokens from desktop app
  2. Fetch unprocessed announcements from the 3 announcement channels
  3. For each announcement — rule-based analysis to decide:
       - Is action required?
       - What file patterns to scan for?
       - What is the summary / suggested change?
  4. Scan watched repos for matching files
  5. Post a webhook alert to the output channel for each affected repo
  6. Mark announcements as processed (won't repeat next run)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .config import load_repos
from .github_client import scan_repos
from .slack_client import SlackMessage, fetch_announcement_messages
from .slack_token_refresh import refresh_slack_env
from .webhook import post_webhook_alert


# ---------------------------------------------------------------------------
# Rule-based announcement classifier
# ---------------------------------------------------------------------------

@dataclass
class Classification:
    action_required: bool
    summary: str
    file_patterns: list[str] = field(default_factory=list)
    suggested_change: str = ""


_RULES: list[tuple[list[str], Classification]] = [
    # Mend SCA CLI migration
    (
        ["mend sca", "opt-in-mend-sca", "mend sca cli"],
        Classification(
            action_required=True,
            summary="Migrate from Mend UA scan to Mend SCA CLI scan",
            file_patterns=[".pipeline-scan-config.yaml", ".pipeline-config*.yaml"],
            suggested_change=(
                "Add `opt-in-mend-sca` env var set to `1` and `mend-user-email` "
                "to the compliance-checks step in your pipeline scan config. "
                "The Mend UA scan is deprecated and will be removed before Feb 2027."
            ),
        ),
    ),
    # Versioned base image update
    (
        ["versioned base image", "pipeline-base-ubi:", "base image"],
        Classification(
            action_required=True,
            summary="Versioned base image update available",
            file_patterns=[".pipeline-config*.yaml", ".pipeline-scan-config.yaml"],
            suggested_change=(
                "If you pin a specific version tag (e.g. pipeline-base-ubi:3.x), "
                "update to the latest version. If you use :latest, no action needed."
            ),
        ),
    ),
    # detect-secrets / secrets baseline
    (
        ["detect-secrets", "secrets baseline", ".secrets.baseline"],
        Classification(
            action_required=True,
            summary="detect-secrets configuration change required",
            file_patterns=[".pipeline-config*.yaml", ".pipeline-scan-config.yaml", ".secrets.baseline"],
            suggested_change=(
                "Update your detect-secrets step or .secrets.baseline file "
                "as described in the announcement."
            ),
        ),
    ),
    # Code signing / GaraSign
    (
        ["garasign", "code sign", "csso-image-sign", "ciso-sign"],
        Classification(
            action_required=True,
            summary="Code signing configuration update required",
            file_patterns=[".pipeline-config*.yaml", "GaraSign", "sign"],
            suggested_change=(
                "Update your code signing step configuration as described in the announcement."
            ),
        ),
    ),
    # get_env deprecation
    (
        ["get_env", "secure values", "pipeline environment"],
        Classification(
            action_required=True,
            summary="Pipeline env variable retrieval method changing",
            file_patterns=[".pipeline-config*.yaml", ".pipeline-scan-config.yaml", "scripts/"],
            suggested_change=(
                "Review use of get_env for secure values in your pipeline scripts — "
                "this behaviour is changing. See announcement for details."
            ),
        ),
    ),
    # ZAP / dynamic scan
    (
        ["zap v1", "dast-zap", "zap scan"],
        Classification(
            action_required=True,
            summary="ZAP v1 dynamic scan deprecated — migrate to ZAP v2",
            file_patterns=[".pipeline-config*.yaml"],
            suggested_change=(
                "Remove dast-zap v1 configuration. ZAP v2 is now the only supported option."
            ),
        ),
    ),
    # CRA deprecation
    (
        ["cra deprecation", "cra is deprecated", "cra onboarding"],
        Classification(
            action_required=True,
            summary="CRA deprecated — migrate to Mend SCA",
            file_patterns=[".pipeline-config*.yaml", ".pipeline-scan-config.yaml"],
            suggested_change=(
                "CRA (Code Risk Analyser) is being deprecated. "
                "Migrate to Mend SCA following the onboarding guidance in the announcement."
            ),
        ),
    ),
    # Pipeline release notes — informational only
    (
        ["pipeline release:", "release notes", "backout plan", "v11.", "v10."],
        Classification(
            action_required=False,
            summary="Pipeline release notes (informational)",
        ),
    ),
    # Support questions / issues in wrong channels — skip
    (
        ["i s s u e", "describe the issue", "facing the below issue", "please do not post"],
        Classification(
            action_required=False,
            summary="Support question or channel notice (no action needed)",
        ),
    ),
]


def classify(message: SlackMessage) -> Classification:
    """Rule-based classifier — checks message text against known patterns."""
    text_lower = message.text.lower()

    for keywords, classification in _RULES:
        if any(kw in text_lower for kw in keywords):
            return classification

    # Default — unrecognised, flag as informational
    return Classification(
        action_required=False,
        summary="Unrecognised announcement — review manually",
    )


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_pipeline(verbose: bool = True) -> None:
    """Full automated pipeline: fetch → classify → scan → alert."""

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

    # Load repo watchlist
    repos = [r["repo"] for r in load_repos()]
    if not repos:
        log("⚠️  No repos in watchlist. Add repos to repos.json first.")
        return

    for msg in messages:
        classification = classify(msg)

        log(f"\n── [{msg.channel}] {msg.text[:80].strip()}...")
        log(f"   Category: {classification.summary}")

        if not classification.action_required:
            log("   → No action required, skipping.")
            continue

        if not classification.file_patterns:
            log("   → No file patterns to scan, skipping.")
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
                    change_description=(
                        f"Affected files: {', '.join(match.matched_files)}"
                    ),
                    pr_url=None,
                    announcement_permalink=msg.permalink or "",
                )
                log(f"   ✅ Alert posted for {match.repo}")
            except Exception as exc:
                log(f"   ❌ Failed to post alert for {match.repo}: {exc}")

    log("\n✅ Pipeline run complete.")
