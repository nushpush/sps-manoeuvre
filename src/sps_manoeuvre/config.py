"""Configuration: channel registry, repo list, and state management."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TypedDict


# ---------------------------------------------------------------------------
# Default Channel registry (IBM CICS / SPS standard defaults)
# ---------------------------------------------------------------------------

_DEFAULT_ANNOUNCEMENT_CHANNELS = [
    "one-pipeline-announce",
    "devops-compliance",
    "secure-pipelines-service",
    "ciso-security-scanning-pipeline",
]

_DEFAULT_ANNOUNCEMENT_CHANNEL_IDS: dict[str, str] = {
    "one-pipeline-announce": "C04TZHM220P",
    "devops-compliance": "CFQHG5PP1",
    "secure-pipelines-service": "C04SYRN5X88",
    "ciso-security-scanning-pipeline": "C02JTCEC00H",
}

_DEFAULT_TROUBLESHOOTING_CHANNELS = [
    "scs_code-signing",
    "scs-opensource-scan",
    "scs-sast",
    "cd-tekton-users-shared",
    "ciso-security-scanning-pipeline",
]

_DEFAULT_SLACK_OUTPUT_CHANNEL = "sps-updates-modernization"
_DEFAULT_PIPELINE_NOTIFICATIONS_CHANNEL = "cics-sps-notifications"
_DEFAULT_PIPELINE_NOTIFICATIONS_CHANNEL_ID = "C07LS8K2DTQ"


# ---------------------------------------------------------------------------
# YAML config override parser (pure-Python basic YAML parser to avoid hard PyYAML dep)
# ---------------------------------------------------------------------------

def _load_yaml_config() -> dict:
    """Load config overrides from config.yaml if present in project or package dir."""
    locations = [
        Path(__file__).resolve().parent / "config.yaml",
        Path(__file__).resolve().parent.parent.parent / "config.yaml",
    ]
    for loc in locations:
        if loc.is_file():
            try:
                # Try yaml module if available
                import yaml  # type: ignore[import-untyped]
                with loc.open() as fh:
                    return yaml.safe_load(fh) or {}
            except ImportError:
                # Basic line-by-line fallback for standard config keys
                return _parse_simple_yaml(loc.read_text())
            except Exception:
                pass
    return {}


def _parse_simple_yaml(text: str) -> dict:
    """Simple parser for flat or 1-level list YAML entries without external dependencies."""
    data: dict = {}
    current_list_key = None
    current_dict_item: dict | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("- "):
            item_val = line[2:].strip().strip("\"'")
            if ":" in item_val:
                k, v = item_val.split(":", 1)
                item_dict = {k.strip(): v.strip().strip("\"'")}
                if current_list_key:
                    data.setdefault(current_list_key, []).append(item_dict)
            elif current_list_key:
                data.setdefault(current_list_key, []).append(item_val)
        elif ":" in line:
            parts = line.split(":", 1)
            key = parts[0].strip()
            val = parts[1].strip().strip("\"'")
            if not val:
                current_list_key = key
            else:
                current_list_key = None
                data[key] = val
    return data


_yaml_cfg = _load_yaml_config()

# Configure channels with overrides if present
ANNOUNCEMENT_CHANNELS: list[str] = []
ANNOUNCEMENT_CHANNEL_IDS: dict[str, str] = dict(_DEFAULT_ANNOUNCEMENT_CHANNEL_IDS)

if "announcement_channels" in _yaml_cfg and isinstance(_yaml_cfg["announcement_channels"], list):
    for ch in _yaml_cfg["announcement_channels"]:
        if isinstance(ch, dict) and "name" in ch:
            ch_name = ch["name"]
            ANNOUNCEMENT_CHANNELS.append(ch_name)
            if "id" in ch:
                ANNOUNCEMENT_CHANNEL_IDS[ch_name] = ch["id"]
        elif isinstance(ch, str):
            ANNOUNCEMENT_CHANNELS.append(ch)
else:
    ANNOUNCEMENT_CHANNELS = list(_DEFAULT_ANNOUNCEMENT_CHANNELS)

TROUBLESHOOTING_CHANNELS: list[str] = (
    _yaml_cfg["troubleshooting_channels"]
    if "troubleshooting_channels" in _yaml_cfg and isinstance(_yaml_cfg["troubleshooting_channels"], list)
    else list(_DEFAULT_TROUBLESHOOTING_CHANNELS)
)

ALL_CHANNELS = ANNOUNCEMENT_CHANNELS + TROUBLESHOOTING_CHANNELS

SLACK_OUTPUT_CHANNEL = str(_yaml_cfg.get("slack_output_channel", _DEFAULT_SLACK_OUTPUT_CHANNEL))

# Pipeline status notifications channel
PIPELINE_NOTIFICATIONS_CHANNEL = str(_yaml_cfg.get("pipeline_notifications_channel", _DEFAULT_PIPELINE_NOTIFICATIONS_CHANNEL))
PIPELINE_NOTIFICATIONS_CHANNEL_ID = str(_yaml_cfg.get("pipeline_notifications_channel_id", _DEFAULT_PIPELINE_NOTIFICATIONS_CHANNEL_ID))

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
