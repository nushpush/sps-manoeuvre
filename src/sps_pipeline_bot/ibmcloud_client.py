"""IBM Cloud Tekton Pipelines API client.

Fetches pipeline run logs to extract the actual error message from a failed run.
Uses IBM Cloud IAM API key for authentication.

Environment variables required:
  IBM_CLOUD_API_KEY  — IBM Cloud API key with access to the Tekton pipelines
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

# Log lines that indicate the real error (vs noise/debug)
_ERROR_PATTERNS = [
    r"\[ERROR\]",
    r"::error::",
    r"Exit Code: '[^0]",
    r"BUILD FAILURE",
    r"FAILED",
    r"Exception",
    r"fatal:",
    r"Error:",
]
_ERROR_RE = re.compile("|".join(_ERROR_PATTERNS), re.IGNORECASE)

# Noise patterns to skip even if they match above
_SKIP_PATTERNS = re.compile(
    r"(debug|metric\.ts|cocoa-cli.*metric|Skipping step because a previous step failed)",
    re.IGNORECASE,
)


@dataclass
class FailedStep:
    step_name: str
    error_lines: list[str] = field(default_factory=list)
    exit_code: str = ""

    @property
    def error_summary(self) -> str:
        """First meaningful error line, cleaned of timestamps."""
        for line in self.error_lines:
            clean = re.sub(r"^\S+Z\s+", "", line).strip()
            clean = re.sub(r"::error::", "", clean).strip()
            if clean and len(clean) > 10:
                return clean
        return f"Step {self.step_name} failed"

    @property
    def search_query(self) -> str:
        """Extract keywords for troubleshooting search."""
        summary = self.error_summary
        # Strip Maven/Java boilerplate, keep the meaningful part
        summary = re.sub(r"\[ERROR\]\s*", "", summary)
        summary = re.sub(r"at [\w\.$]+\([\w\.]+:\d+\)", "", summary)
        summary = re.sub(r"Stage \w+ collect evidence returned.*", "stage failed", summary)
        return summary[:200].strip()


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
    """Fetch logs for a failed pipeline run and return steps with errors.

    Args:
        run_url: The IBM Cloud pipeline run URL from the Slack notification.

    Returns:
        List of FailedStep objects, ordered by significance (root cause first).
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

    failed_steps: list[FailedStep] = []

    for entry in log_entries:
        step_name = entry.get("name", "")

        # Skip sidecar steps (dind, tekton-log-results) — they're infrastructure noise
        if any(skip in step_name for skip in ["dind", "tekton-log-results"]):
            continue

        log_resp = httpx.get(entry["href"], headers=headers, timeout=15)
        if log_resp.status_code != 200:
            continue
        content = log_resp.json().get("data", "")

        lines = content.split("\n")
        error_lines = []
        exit_code = ""

        for line in lines:
            # Extract exit code
            ec_match = re.search(r"Exit Code: '(\d+)'", line)
            if ec_match:
                exit_code = ec_match.group(1)

            clean = _strip_timestamp(line)
            if not clean:
                continue
            if _ERROR_RE.search(clean) and not _SKIP_PATTERNS.search(clean):
                error_lines.append(clean)

        # Only include steps that actually failed (non-zero exit or real errors)
        if exit_code and exit_code != "0":
            failed_steps.append(FailedStep(
                step_name=step_name,
                error_lines=error_lines[:20],  # cap at 20 lines
                exit_code=exit_code,
            ))
        elif error_lines and "Skipping step because a previous step failed" not in (error_lines[0] if error_lines else ""):
            # Some steps fail without an explicit exit code
            if any("Exit Code:" not in l for l in error_lines):
                failed_steps.append(FailedStep(
                    step_name=step_name,
                    error_lines=error_lines[:20],
                    exit_code=exit_code,
                ))

    # Sort: steps with non-zero exit code first (root cause), skipped steps last
    failed_steps.sort(key=lambda s: (s.exit_code == "" or s.exit_code == "0", s.step_name))

    return failed_steps
