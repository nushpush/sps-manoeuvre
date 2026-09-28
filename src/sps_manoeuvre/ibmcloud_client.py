"""IBM Cloud Tekton Pipelines API client.

Fetches pipeline run logs to extract the actual error message from a failed run.
Uses IBM Cloud IAM API key for authentication.

Environment variables required:
  IBM_CLOUD_API_KEY  — IBM Cloud API key with access to the Tekton pipelines

Logic:
  1. Scan every step log for "BUILD FAILURE".
  2. If found → that step is the root cause; capture the surrounding context lines.
  3. If no BUILD FAILURE anywhere → the failure is an SPS/infra problem, not a
     build failure.  Caller should search SPS troubleshooting channels instead.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

import httpx


_IAM_TOKEN_URL = "https://iam.cloud.ibm.com/identity/token"

# Region map from env_id in pipeline URL (e.g. ibm:yp:eu-gb -> eu-gb)
_REGION_API_URLS = {
    "eu-gb":    "https://api.eu-gb.devops.cloud.ibm.com",
    "us-south": "https://api.us-south.devops.cloud.ibm.com",
    "eu-de":    "https://api.eu-de.devops.cloud.ibm.com",
    "au-syd":   "https://api.au-syd.devops.cloud.ibm.com",
    "us-east":  "https://api.us-east.devops.cloud.ibm.com",
}
_DEFAULT_REGION = "eu-gb"

# How many lines before/after "BUILD FAILURE" to include as context
_CONTEXT_LINES = 10


@dataclass
class FailedStep:
    step_name: str
    error_lines: list[str] = field(default_factory=list)  # context around BUILD FAILURE
    is_build_failure: bool = True  # False = SPS/infra failure (no BUILD FAILURE found)

    @property
    def error_summary(self) -> str:
        """Return the most meaningful line from the captured context."""
        if not self.error_lines:
            return f"Step {self.step_name} failed"
        # Return the first non-empty, non-separator line
        for line in self.error_lines:
            stripped = line.strip()
            if stripped and stripped != "-" * 10:
                return stripped[:300]
        return self.error_lines[0][:300]

    @property
    def search_query(self) -> str:
        """Keywords for SPS troubleshooting search (used when is_build_failure=False)."""
        return f"{self.step_name} failed"


def _get_iam_token(api_key: str) -> str:
    """Exchange an IBM Cloud API key for a short-lived IAM bearer token."""
    resp = httpx.post(
        _IAM_TOKEN_URL,
        data={
            "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
            "apikey": api_key,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _region_from_url(run_url: str) -> str:
    """Extract region from a pipeline run URL env_id parameter."""
    m = re.search(r"env_id=ibm:yp:([\w-]+)", run_url)
    return m.group(1) if m else _DEFAULT_REGION


def _ids_from_url(run_url: str) -> tuple[str, str]:
    """Extract (pipeline_id, run_id) from a cloud.ibm.com pipeline run URL."""
    m = re.search(r"tekton/([a-f0-9-]+)/runs/([a-f0-9-]+)", run_url)
    if not m:
        raise ValueError(f"Could not extract pipeline/run IDs from URL: {run_url}")
    return m.group(1), m.group(2)


def _strip_timestamp(line: str) -> str:
    """Remove the leading ISO timestamp from a log line."""
    return re.sub(r"^\S+Z\s+", "", line).strip()


def get_failed_steps(run_url: str) -> list[FailedStep]:
    """Fetch logs for a failed pipeline run and return the step(s) that failed.

    Strategy:
      - Search every step for "BUILD FAILURE".
      - If found, return a FailedStep with context lines around the failure.
      - If not found in any step, return a single FailedStep with
        is_build_failure=False so the caller knows to search SPS channels.

    Args:
        run_url: The IBM Cloud pipeline run URL from the Slack notification.

    Returns:
        List with one FailedStep.  Empty list only if the API itself failed.
    """
    api_key = os.environ.get("IBM_CLOUD_API_KEY")
    if not api_key:
        raise RuntimeError(
            "IBM_CLOUD_API_KEY is not set. "
            "Add it to mcp.json env to enable log fetching."
        )

    pipeline_id, run_id = _ids_from_url(run_url)
    region = _region_from_url(run_url)
    base_api = _REGION_API_URLS.get(region, _REGION_API_URLS[_DEFAULT_REGION])
    base = f"{base_api}/pipeline/v2/tekton_pipelines/{pipeline_id}"

    iam_token = _get_iam_token(api_key)
    headers = {"Authorization": f"Bearer {iam_token}"}

    # Fetch list of log IDs
    logs_resp = httpx.get(
        f"{base}/pipeline_runs/{run_id}/logs",
        headers=headers,
        timeout=15,
    )
    logs_resp.raise_for_status()
    log_entries = logs_resp.json().get("logs", [])

    for entry in log_entries:
        step_name = entry.get("name", "")

        # Skip infrastructure sidecar steps
        if any(skip in step_name for skip in ["dind", "tekton-log-results"]):
            continue

        log_resp = httpx.get(entry["href"], headers=headers, timeout=15)
        if log_resp.status_code != 200:
            continue
        content = log_resp.json().get("data", "")

        lines = [_strip_timestamp(l) for l in content.split("\n")]

        # Find the first "BUILD FAILURE" line
        for i, line in enumerate(lines):
            if "BUILD FAILURE" in line:
                # Capture _CONTEXT_LINES before and after
                start = max(0, i - _CONTEXT_LINES)
                end = min(len(lines), i + _CONTEXT_LINES + 1)
                context = [l for l in lines[start:end] if l]
                return [FailedStep(
                    step_name=step_name,
                    error_lines=context,
                    is_build_failure=True,
                )]

    # No BUILD FAILURE found anywhere — SPS/infra issue
    return [FailedStep(
        step_name="unknown",
        error_lines=[],
        is_build_failure=False,
    )]
