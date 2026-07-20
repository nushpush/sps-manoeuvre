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
]

ANNOUNCEMENT_CHANNEL_IDS: dict[str, str] = {
    "one-pipeline-announce": "C04TZHM220P",
    "devops-compliance": "CFQHG5PP1",
    "secure-pipelines-service": "C04SYRN5X88",
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
# Repo list — stored next to this package (team-local)
# ---------------------------------------------------------------------------

_REPOS_FILE = Path(__file__).parent / "repos.json"


class RepoEntry(TypedDict):
    repo: str          # "CICS/my-repo"
    description: str   # human-readable label


def load_repos() -> list[RepoEntry]:
    """Return the list of watched repos. Returns [] if the file is missing."""
    if not _REPOS_FILE.exists():
        return []
    with _REPOS_FILE.open() as fh:
        data = json.load(fh)
    return data.get("repos", [])


def save_repos(repos: list[RepoEntry]) -> None:
    with _REPOS_FILE.open("w") as fh:
        json.dump({"repos": repos}, fh, indent=2)


# ---------------------------------------------------------------------------
# State — global ~/.bob/sps-state.json  (tracks processed Slack timestamps)
# ---------------------------------------------------------------------------

_STATE_FILE = Path.home() / ".bob" / "sps-state.json"


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
