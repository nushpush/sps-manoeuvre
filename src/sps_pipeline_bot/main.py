#!/usr/bin/env python3
"""SPS Pipeline Bot — MCP server entry point.

All LLM reasoning is handled by Bob. These tools are pure data-fetch and action layers.

## Automated workflow (what Bob should do end-to-end)

1. fetch_announcements
      → Returns unprocessed messages from #one-pipeline-announce, #devops-compliance,
        #secure-pipelines-service. Each message is marked processed after fetching so
        it won't appear again on the next run.

2. For each announcement — Bob analyses the text and decides:
      - Is action required? (ignore release notes, informational posts, support questions)
      - What category? (image-update, mend-migration, scan-config, code-signing, detect-secrets, etc.)
      - What file patterns to look for? (e.g. ['.pipeline-config*.yaml', '.pipeline-scan-config.yaml'])
      - What change is needed? (e.g. "add opt-in-mend-sca: 1 to compliance-checks step")

3. scan_repos_tool(file_patterns)
      → Finds which watched repos contain the affected files.
      → Skip repos with no matching files.

4. get_repo_files(repo, file_patterns)
      → Fetches current file contents so Bob can see what already exists and determine
        the exact diff needed.

5. For each affected repo — Bob generates the updated file content, then:

   a. Show the diff to the user in chat and ask for confirmation before proceeding.

   b. On confirmation → create_pr(repo, branch_name, pr_title, pr_body, file_changes)
         → Opens a PR on github.ibm.com with the proposed changes.

   c. post_webhook_alert(repo, summary, suggested_change, change_description,
                         announcement_permalink, pr_url)
         → Posts to the team's output Slack channel with a link to the PR.

6. If user declines to create a PR — still call post_webhook_alert with pr_url=""
      so the team is notified and can act manually.

## Tools exposed

  ping                         — smoke test
  fetch_announcements          — read unprocessed messages from 3 announcement channels
  search_troubleshoot_channels — search 5 troubleshooting channels by keyword
  scan_repos_tool              — find repos containing files matching given patterns
  get_repo_files               — fetch current file contents from a repo
  create_pr                    — open a GitHub PR with specified file changes
  post_webhook_alert           — notify via existing notification app webhook
  list_repos                   — show the configured repo watchlist
  add_repo / remove_repo       — manage the watchlist
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from .config import load_repos, save_repos
from .github_client import AnnouncementAnalysis, build_file_context, create_pull_request, scan_repos
from .slack_client import fetch_announcement_messages, post_webhook_alert as _post_webhook, search_troubleshooting
from .slack_token_refresh import refresh_slack_env

# Auto-refresh Slack tokens from the desktop app on startup
refresh_slack_env()

mcp = FastMCP("sps-pipeline-bot")


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

@mcp.tool()
def ping() -> str:
    """Smoke-test tool — returns pong."""
    return "pong"


# ---------------------------------------------------------------------------
# Repo watchlist management
# ---------------------------------------------------------------------------

@mcp.tool()
def list_repos() -> list[dict]:
    """Return the list of repositories currently being watched for SPS changes."""
    return load_repos()  # type: ignore[return-value]


@mcp.tool()
def add_repo(repo: str, description: str = "") -> str:
    """Add a repository to the watchlist.

    Args:
        repo: Repository in 'ORG/NAME' format, e.g. 'CICS/cics-explorer-docs'.
        description: Optional human-readable label.
    """
    repos = load_repos()
    if any(r["repo"] == repo for r in repos):
        return f"Repository '{repo}' is already in the watchlist."
    repos.append({"repo": repo, "description": description})
    save_repos(repos)
    return f"Added '{repo}' to the watchlist."


@mcp.tool()
def remove_repo(repo: str) -> str:
    """Remove a repository from the watchlist.

    Args:
        repo: Repository in 'ORG/NAME' format.
    """
    repos = load_repos()
    before = len(repos)
    repos = [r for r in repos if r["repo"] != repo]
    if len(repos) == before:
        return f"Repository '{repo}' was not found in the watchlist."
    save_repos(repos)
    return f"Removed '{repo}' from the watchlist."


# ---------------------------------------------------------------------------
# Slack — fetch announcements (user token, no app registration)
# ---------------------------------------------------------------------------

@mcp.tool()
def fetch_announcements(limit: int = 20) -> list[dict]:
    """Fetch unprocessed messages from the three SPS announcement channels.

    Channels monitored: #one-pipeline-announce, #devops-complines, #secure-pipelines-service

    Returns messages not yet seen (tracked in .bob/sps-state.json).
    Each result includes: channel, ts, text, permalink, username.

    Bob should analyse each message text to determine:
    - Is action required?
    - What category is the change (image-update, scan-config, code-signing, detect-secrets, etc.)?
    - What file patterns to look for in repos?
    - What change is needed?

    Args:
        limit: Max messages to fetch per channel (default 20).
    """
    messages = fetch_announcement_messages(limit=limit)
    return [
        {
            "channel": m.channel,
            "ts": m.ts,
            "text": m.text,
            "permalink": m.permalink,
            "username": m.username,
        }
        for m in messages
    ]


# ---------------------------------------------------------------------------
# Slack — search troubleshooting channels (user token, read-only)
# ---------------------------------------------------------------------------

@mcp.tool()
def search_troubleshoot_channels(query: str, max_results: int = 10) -> list[dict]:
    """Search the five troubleshooting Slack channels for threads matching a query.

    Channels searched: #scs_code-signing, #scs-opensource-scan, #scs-sast,
                       #cd-tekton-users-shared, #ciso-security-scanning-pipeline

    Returns matching threads including their replies. Bob should read the thread
    text and replies to synthesise the best solution that worked.

    Args:
        query: Error message, keyword, or description of the build failure.
        max_results: Max matching threads to return (default 10).
    """
    messages = search_troubleshooting(query=query, max_results=max_results)
    return [
        {
            "channel": m.channel,
            "ts": m.ts,
            "text": m.text,
            "permalink": m.permalink,
            "username": m.username,
            "thread_replies": m.thread_replies,
        }
        for m in messages
    ]


# ---------------------------------------------------------------------------
# GitHub — scan repos for affected files
# ---------------------------------------------------------------------------

@mcp.tool()
def scan_repos_tool(file_patterns: list[str], repos: list[str] | None = None) -> list[dict]:
    """Scan repos for files matching the given patterns.

    If repos is not supplied, uses the configured watchlist from repos.json.
    Returns only repos where at least one matching file was found.

    Args:
        file_patterns: Filename patterns to search for, e.g. ['.pipeline-config*.yaml', 'GaraSign'].
        repos: Optional list of 'ORG/NAME' repos. Defaults to the watchlist.
    """
    if repos is None:
        repos = [r["repo"] for r in load_repos()]
    matches = scan_repos(repos=repos, file_patterns=file_patterns)
    return [
        {
            "repo": m.repo,
            "matched_files": m.matched_files,
        }
        for m in matches
    ]


@mcp.tool()
def get_repo_files(repo: str, file_patterns: list[str]) -> dict:
    """Fetch the current contents of files in a repo that match the given patterns.

    Returns a formatted block of file contents for Bob to analyse and determine
    what changes are needed.

    Args:
        repo: 'ORG/NAME' repository, e.g. 'CICS/cics-explorer-docs'.
        file_patterns: Filename patterns to match inside the repo.
    """
    matches = scan_repos(repos=[repo], file_patterns=file_patterns)
    if not matches:
        return {
            "repo": repo,
            "matched_files": [],
            "file_contents": {},
            "formatted": "No matching files found.",
        }
    match = matches[0]
    return {
        "repo": repo,
        "matched_files": match.matched_files,
        "file_contents": match.file_contents,
        "formatted": build_file_context(match.file_contents),
    }


# ---------------------------------------------------------------------------
# GitHub — create PR
# ---------------------------------------------------------------------------

@mcp.tool()
def create_pr(
    repo: str,
    branch_name: str,
    pr_title: str,
    pr_body: str,
    file_changes: dict[str, str],
    base_branch: str = "main",
) -> dict:
    """Create a GitHub PR with the specified file changes on github.ibm.com.

    IMPORTANT: Only call this after Bob has shown the diff to the user and received
    explicit confirmation to proceed.

    Args:
        repo: 'ORG/NAME' repository.
        branch_name: New branch name, e.g. 'sps-bot/update-scan-config'.
        pr_title: Title for the pull request.
        pr_body: Description / body for the pull request.
        file_changes: Dict mapping file paths to their complete new content.
        base_branch: Base branch to merge into (default 'main').
    """
    pr_url = create_pull_request(
        repo_name=repo,
        branch_name=branch_name,
        title=pr_title,
        body=pr_body,
        file_changes=file_changes,
        base_branch=base_branch,
    )
    return {"repo": repo, "pr_url": pr_url}


# ---------------------------------------------------------------------------
# Notifications — post via existing webhook-enabled notification app
# ---------------------------------------------------------------------------

@mcp.tool()
def post_webhook_alert(
    repo: str,
    summary: str,
    suggested_change: str,
    change_description: str,
    announcement_permalink: str,
    pr_url: str = "",
) -> dict:
    """Post a repo-change alert via the existing notification app's incoming webhook.

    Sends a formatted Slack Block Kit message to whatever channel the webhook
    is configured to post to in your existing notification app.

    Args:
        repo: 'ORG/NAME' repository.
        summary: One-line summary of the SPS announcement.
        suggested_change: What the announcement requires repos to change.
        change_description: Description of the specific changes made / to be made.
        announcement_permalink: Slack permalink to the original announcement message.
        pr_url: PR URL if one was already created, otherwise empty string.
    """
    _post_webhook(
        repo=repo,
        summary=summary,
        suggested_change=suggested_change,
        change_description=change_description,
        pr_url=pr_url or None,
        announcement_permalink=announcement_permalink,
    )
    return {"posted": True, "repo": repo}


def run() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    run()
