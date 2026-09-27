"""Configuration: channel registry, repo list, and state management."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TypedDict


# ---------------------------------------------------------------------------
# Channel registry
# ---------------------------------------------------------------------------

# Channel name -> ID mapping (conversations.list is blocked on IBM enterprise Slack)
ANNOUNCEMENT_CHANNELS = [
    "one-pipeline-announce",
    "devops-compliance",
    "secure-pipelines-service",
    "ciso-security-scanning-pipeline",
]

ANNOUNCEMENT_CHANNEL_IDS: dict[str, str] = {
    "one-pipeline-announce": "C04TZHM220P",
    "devops-compliance": "CFQHG5PP1",
    "secure-pipelines-service": "C04SYRN5X88",
    "ciso-security-scanning-pipeline": "C02JTCEC00H",
}

TROUBLESHOOTING_CHANNELS = [
    "scs_code-signing",
    "scs-opensource-scan",
    "scs-sast",
    "cd-tekton-users-shared",
    "ciso-security-scanning-pipeline",
]

ALL_CHANNELS = ANNOUNCEMENT_CHANNELS + TROUBLESHOOTING_CHANNELS

SLACK_OUTPUT_CHANNEL = "sps-updates-modernization"

# Pipeline status notifications channel
PIPELINE_NOTIFICATIONS_CHANNEL = "cics-sps-notifications"
PIPELINE_NOTIFICATIONS_CHANNEL_ID = "C07LS8K2DTQ"

# Colour codes used by the notification bot
PIPELINE_FAILURE_COLOUR = "#f2446f"
PIPELINE_SUCCESS_COLOUR = "#36a64f"

# ---------------------------------------------------------------------------
# Repo list — gitignored, local to each user's machine.
# On first use, auto-bootstrapped from repos.json.example.
# ---------------------------------------------------------------------------

_REPOS_FILE = Path(__file__).parent / "repos.json"
_REPOS_EXAMPLE = Path(__file__).parent / "repos.json.example"


class RepoEntry(TypedDict):
    repo: str          # "CICS/my-repo"
    description: str   # human-readable label


def load_repos() -> list[RepoEntry]:
    """Return the list of watched repos.

    If repos.json doesn't exist, copies repos.json.example as a starting point
    and returns an empty list — the user should edit repos.json to add their repos.
    """
    if not _REPOS_FILE.exists():
        if _REPOS_EXAMPLE.exists():
            import shutil
            shutil.copy(_REPOS_EXAMPLE, _REPOS_FILE)
        return []
    with _REPOS_FILE.open() as fh:
        data = json.load(fh)
    # filter out the placeholder entry from the example
    return [r for r in data.get("repos", []) if r.get("repo") != "ORG/repo-name"]


def save_repos(repos: list[RepoEntry]) -> None:
    with _REPOS_FILE.open("w") as fh:
        json.dump({"repos": repos}, fh, indent=2)


# ---------------------------------------------------------------------------
# State — .bob/sps-state.json next to this project
# Falls back to ~/.bob/sps-state.json if the project .bob dir doesn't exist.
# ---------------------------------------------------------------------------

_PROJECT_BOB = Path(__file__).parent.parent.parent / ".bob"
_STATE_FILE = (
    _PROJECT_BOB / "sps-state.json"
    if _PROJECT_BOB.is_dir()
    else Path.home() / ".bob" / "sps-state.json"
)


def load_processed_timestamps() -> set[str]:
    if not _STATE_FILE.exists():
        return set()
    with _STATE_FILE.open() as fh:
        data = json.load(fh)
    return set(data.get("processed_ts", []))


def mark_processed(timestamps: list[str]) -> None:
    existing = load_processed_timestamps()
    combined = sorted(existing | set(timestamps))
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with _STATE_FILE.open("w") as fh:
        json.dump({"processed_ts": combined}, fh, indent=2)
