"""Diagnostic doctor command for SPS Manoeuvre.

Run as:
    python -m sps_manoeuvre --doctor
    sps-manoeuvre --doctor

Performs checks and outputs PASS/WARN/FAIL status with actionable remedies.
Never logs or prints secrets.
"""

from __future__ import annotations

import importlib
import json
import os
import re
import sys
from pathlib import Path
from typing import NamedTuple

from .config import (
    ANNOUNCEMENT_CHANNELS,
    ANNOUNCEMENT_CHANNEL_IDS,
    load_repos,
)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_BOB_DIR = _PROJECT_ROOT / ".bob"
_MCP_JSON = _BOB_DIR / "mcp.json"
_SLACK_KEY = _BOB_DIR / "slack-key.bin"
_REPOS_FILE = Path(__file__).resolve().parent / "repos.json"


class CheckResult(NamedTuple):
    status: str  # "PASS", "WARN", "FAIL"
    message: str
    remedy: str = ""


def check_python() -> CheckResult:
    """Verify Python version >= 3.10."""
    ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 10):
        return CheckResult("PASS", f"Python version is {ver} (>= 3.10)")
    return CheckResult(
        "FAIL",
        f"Python version is {ver} (< 3.10)",
        "Install Python 3.10 or later using pyenv or official Python distribution.",
    )


def check_packages() -> CheckResult:
    """Verify required Python packages are installed and importable."""
    required = [
        ("mcp", "mcp"),
        ("slack_sdk", "slack-sdk"),
        ("github", "PyGithub"),
        ("httpx", "httpx"),
        ("Crypto", "pycryptodome"),
    ]
    missing = []
    for mod_name, pkg_name in required:
        try:
            importlib.import_module(mod_name)
        except ImportError:
            missing.append(pkg_name)

    if not missing:
        return CheckResult("PASS", "All required packages are installed")
    return CheckResult(
        "FAIL",
        f"Missing required packages: {', '.join(missing)}",
        "Run: pip install -e .",
    )


def _load_env_from_mcp_json() -> dict[str, str]:
    """Load env vars defined in .bob/mcp.json without side-effects."""
    if not _MCP_JSON.exists():
        return {}
    try:
        with _MCP_JSON.open() as fh:
            data = json.load(fh)
            return data.get("mcpServers", {}).get("sps-manoeuvre", {}).get("env", {})
    except Exception:
        return {}


def check_mcp_json() -> CheckResult:
    """Verify .bob/mcp.json exists and contains required keys."""
    if not _MCP_JSON.exists():
        return CheckResult(
            "FAIL",
            f"{_MCP_JSON} does not exist",
            "Run setup wizard: python -m sps_manoeuvre --setup",
        )

    env = _load_env_from_mcp_json()
    missing_keys = []
    # Check GITHUB_TOKEN and SLACK_WEBHOOK_URL either in mcp.json or os.environ
    gh_tok = env.get("GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")
    webhook = env.get("SLACK_WEBHOOK_URL") or os.environ.get("SLACK_WEBHOOK_URL")

    if not gh_tok:
        missing_keys.append("GITHUB_TOKEN")
    if not webhook:
        missing_keys.append("SLACK_WEBHOOK_URL")

    if missing_keys:
        return CheckResult(
            "FAIL",
            f"Missing required configuration key(s): {', '.join(missing_keys)}",
            "Update .bob/mcp.json or run: python -m sps_manoeuvre --setup",
        )

    return CheckResult("PASS", ".bob/mcp.json exists with required keys")


def check_slack_key() -> CheckResult:
    """Verify .bob/slack-key.bin exists on macOS."""
    if sys.platform != "darwin":
        # On non-macOS, check if SLACK_USER_TOKEN and SLACK_COOKIE are configured
        env = _load_env_from_mcp_json()
        has_user_tok = env.get("SLACK_USER_TOKEN") or os.environ.get("SLACK_USER_TOKEN")
        has_cookie = env.get("SLACK_COOKIE") or os.environ.get("SLACK_COOKIE")
        if has_user_tok and has_cookie:
            return CheckResult("PASS", "SLACK_USER_TOKEN and SLACK_COOKIE configured (non-macOS)")
        return CheckResult(
            "WARN",
            "Non-macOS system without SLACK_USER_TOKEN and SLACK_COOKIE configured",
            "If channel reading is required on Linux/Windows, provide SLACK_USER_TOKEN and SLACK_COOKIE in .bob/mcp.json",
        )

    if _SLACK_KEY.exists():
        return CheckResult("PASS", f"Cached Slack AES key found at {_SLACK_KEY}")
    return CheckResult(
        "FAIL",
        f"Slack AES key not cached ({_SLACK_KEY} missing)",
        "Run: python -m sps_manoeuvre --bootstrap",
    )


def check_repos_json() -> CheckResult:
    """Verify repos.json exists and contains at least one non-placeholder entry."""
    if not _REPOS_FILE.exists():
        return CheckResult(
            "FAIL",
            f"{_REPOS_FILE} does not exist",
            "Copy repos.json.example to repos.json and add your repositories.",
        )

    repos = load_repos()
    if not repos:
        return CheckResult(
            "FAIL",
            f"{_REPOS_FILE} contains no active repositories (or only placeholders)",
            f"Add target repositories (e.g. CICS/my-repo) into {_REPOS_FILE}",
        )
    return CheckResult("PASS", f"Watched repos configured ({len(repos)} repo(s) active)")


def check_webhook_url() -> CheckResult:
    """Verify SLACK_WEBHOOK_URL format."""
    env = _load_env_from_mcp_json()
    webhook = os.environ.get("SLACK_WEBHOOK_URL") or env.get("SLACK_WEBHOOK_URL", "")
    if not webhook:
        return CheckResult(
            "FAIL",
            "SLACK_WEBHOOK_URL is not configured",
            "Configure SLACK_WEBHOOK_URL in .bob/mcp.json or environment",
        )
    # Check URL structure
    if re.match(r"^https://hooks\.slack\.com/services/T[A-Z0-9]+/B[A-Z0-9]+/[A-Za-z0-9]+$", webhook):
        return CheckResult("PASS", "SLACK_WEBHOOK_URL format is valid")
    if webhook.startswith("https://hooks.slack.com/"):
        return CheckResult("PASS", "SLACK_WEBHOOK_URL is a valid Slack webhook endpoint")
    return CheckResult(
        "WARN",
        "SLACK_WEBHOOK_URL does not match standard Slack hooks format",
        "Ensure webhook URL starts with https://hooks.slack.com/services/...",
    )


def check_github_connectivity() -> CheckResult:
    """Verify GitHub connectivity by testing authenticated user/PAT."""
    env = _load_env_from_mcp_json()
    token = os.environ.get("GITHUB_TOKEN") or env.get("GITHUB_TOKEN", "")
    if not token:
        return CheckResult(
            "FAIL",
            "GITHUB_TOKEN not available for connectivity test",
            "Configure GITHUB_TOKEN in .bob/mcp.json",
        )

    try:
        from github import Github, GithubException
        # Default test against GHE (https://github.ibm.com/api/v3)
        gh = Github(base_url="https://github.ibm.com/api/v3", login_or_token=token)
        user = gh.get_user()
        login = user.login
        return CheckResult("PASS", f"GitHub GHE connectivity authenticated as '{login}'")
    except Exception as exc:
        return CheckResult(
            "FAIL",
            f"GitHub authentication failed: {exc}",
            "Verify your GITHUB_TOKEN on https://github.ibm.com/settings/tokens with 'repo' scope.",
        )


def check_slack_connectivity() -> CheckResult:
    """Verify Slack connectivity by fetching history for the first announcement channel."""
    # Ensure env is refreshed
    try:
        from .slack_token_refresh import refresh_slack_env
        from .slack_client import _get_client
        refresh_slack_env()
    except Exception:
        pass

    channel_name = ANNOUNCEMENT_CHANNELS[0] if ANNOUNCEMENT_CHANNELS else "one-pipeline-announce"
    channel_id = ANNOUNCEMENT_CHANNEL_IDS.get(channel_name)
    if not channel_id:
        return CheckResult("WARN", f"No channel ID configured for {channel_name}")

    try:
        from .slack_client import _get_client
        client = _get_client()
        resp = client.conversations_history(channel=channel_id, limit=1)
        if resp.get("ok"):
            return CheckResult("PASS", f"Slack read connectivity confirmed on #{channel_name}")
        return CheckResult(
            "FAIL",
            f"Slack read failed: {resp.get('error', 'unknown error')}",
            "Re-run 'python -m sps_manoeuvre --bootstrap' or check Slack login status.",
        )
    except Exception as exc:
        return CheckResult(
            "FAIL",
            f"Slack connectivity check failed: {exc}",
            "Run 'python -m sps_manoeuvre --bootstrap' to refresh cached credentials.",
        )


def check_ibmcloud_api_key() -> CheckResult:
    """Verify IBM Cloud API key presence."""
    env = _load_env_from_mcp_json()
    key = os.environ.get("IBM_CLOUD_API_KEY") or env.get("IBM_CLOUD_API_KEY", "")
    if key:
        return CheckResult("PASS", "IBM_CLOUD_API_KEY is configured")
    return CheckResult(
        "WARN",
        "IBM_CLOUD_API_KEY is not configured",
        "Optional: required only for --monitor Tekton log analysis. Add to .bob/mcp.json if needed.",
    )


def run() -> int:
    """Execute all diagnostic checks and print report."""
    print("=" * 65)
    print("🩺 SPS Manoeuvre — Diagnostic Doctor")
    print("=" * 65)

    checks = [
        ("Python Version", check_python),
        ("Required Packages", check_packages),
        ("MCP Config (.bob/mcp.json)", check_mcp_json),
        ("Slack Desktop AES Key", check_slack_key),
        ("Repos Watchlist", check_repos_json),
        ("Slack Webhook URL Format", check_webhook_url),
        ("GitHub Connectivity", check_github_connectivity),
        ("Slack Connectivity", check_slack_connectivity),
        ("IBM Cloud API Key", check_ibmcloud_api_key),
    ]

    results: list[tuple[str, CheckResult]] = []
    fail_count = 0
    warn_count = 0

    for name, check_fn in checks:
        try:
            res = check_fn()
        except Exception as exc:
            res = CheckResult("FAIL", f"Unexpected check error: {exc}", "Inspect logs or re-run setup.")
        results.append((name, res))

        icon = "✅" if res.status == "PASS" else ("⚠️ " if res.status == "WARN" else "❌")
        print(f"{icon} [{res.status}] {name}: {res.message}")
        if res.status == "FAIL":
            fail_count += 1
        elif res.status == "WARN":
            warn_count += 1

    print("\n" + "=" * 65)
    if fail_count > 0:
        print(f"❌ Diagnostic found {fail_count} failure(s) and {warn_count} warning(s).\n")
        print("Remediation steps:")
        for name, res in results:
            if res.status == "FAIL" and res.remedy:
                print(f"  • {name}: {res.remedy}")
        print("=" * 65)
        return 1
    elif warn_count > 0:
        print(f"⚠️  Doctor passed with {warn_count} warning(s). All core features operational.")
        print("=" * 65)
        return 0
    else:
        print("🎉 All checks PASSED! SPS Manoeuvre is ready for production use.")
        print("=" * 65)
        return 0


if __name__ == "__main__":
    sys.exit(run())
