# SPS Manoeuvre

Automated maintenance and intelligence for IBM Cloud Secure Pipeline Service (SPS) across multi-repository toolchains.

The bot operates in two complementary ways: as an interactive [Bob](https://bob.ibm.com) MCP server for assistive PR creation and troubleshooting, and as an automated background runner. It continuously monitors SPS announcement channels, identifies impacted repositories, dispatches formatted alerts, and diagnoses Tekton pipeline run failures.

---

## Prerequisites

| Requirement | Why Needed | How to Obtain |
|---|---|---|
| **Python >= 3.10** | Core runtime and typing support | Check `python3 --version`. Install via `pyenv` or `brew install python@3.11`. |
| **IBM Enterprise Slack Workspace** | Reading SPS channels and sending alerts | Logged into the IBM workspace on desktop Slack or web. |
| **GitHub Personal Access Token (PAT)** | Scanning repositories and creating fix PRs | [github.ibm.com/settings/tokens](https://github.ibm.com/settings/tokens) with `repo` scope. |
| **Slack Incoming Webhook URL** | Dispatching alerts to your team channel | Create an incoming webhook in your team's Slack app. |
| **IBM Cloud API Key** *(Optional)* | Extracting build failure logs in `--monitor` mode | [cloud.ibm.com/iam/apikeys](https://cloud.ibm.com/iam/apikeys) (only for `--monitor`). |
| **[Bob Desktop](https://bob.ibm.com)** *(Optional)* | Interactive tool use and guided code diffs | Download and install from [bob.ibm.com](https://bob.ibm.com). |

---

## Quick Start (<= 10 minutes)

Get from zero to first successful execution in 6 steps:

### 1. Clone the repository
```bash
git clone https://github.ibm.com/anushka-p/sps-manoeuvre.git
cd sps-manoeuvre
```

### 2. Install dependencies
```bash
pip3 install -e .
```

### 3. Run the interactive setup wizard
```bash
sps-manoeuvre --setup
```
*(Or run `python3 -m sps_manoeuvre --setup`)*
The wizard configures `.bob/mcp.json`, copies template files, and bootstraps macOS Slack Keychain credentials.

### 4. Run the diagnostic doctor
```bash
sps-manoeuvre --doctor
```
Ensures all dependencies, credentials, and API connectivity checks pass.

### 5. Configure your watched repositories
Edit `src/sps_manoeuvre/repos.json` to include your team's repos:
```json
{
  "repos": [
    { "repo": "CICS/cics-explorer-docs", "description": "CICS Explorer docs" }
  ]
}
```

### 6. Execute your first announcement scan
```bash
sps-manoeuvre --run
```

---

## Configuration Reference

### Environment Variables & Credentials (`.bob/mcp.json` or `.env`)

| Variable | Required | Description | Default / Source |
|---|---|---|---|
| `GITHUB_TOKEN` | Yes | PAT for `github.ibm.com` (and `github.com`) with `repo` scope | `ghp_...` |
| `SLACK_WEBHOOK_URL` | Yes | Incoming Webhook endpoint for team alerts | `https://hooks.slack.com/services/...` |
| `IBM_CLOUD_API_KEY` | Optional | IAM key for Tekton pipeline log analysis | Only required for `--monitor` |
| `SLACK_USER_TOKEN` | Non-macOS only | Personal session token (`xoxc-...`) | Auto-extracted on macOS |
| `SLACK_COOKIE` | Non-macOS only | Personal session cookie (`xoxd-...`) | Auto-extracted on macOS |

### Team Customization (`config.yaml`)

To customize channel destinations or add custom SPS channels, create `config.yaml` in the project root:

```yaml
# Destination channel name (human readable)
slack_output_channel: "sps-updates-modernization"

# Pipeline notifications channel for --monitor
pipeline_notifications_channel: "cics-sps-notifications"
pipeline_notifications_channel_id: "C07LS8K2DTQ"

# Monitored announcement channels
announcement_channels:
  - name: "one-pipeline-announce"
    id: "C04TZHM220P"
  - name: "devops-compliance"
    id: "CFQHG5PP1"
  - name: "secure-pipelines-service"
    id: "C04SYRN5X88"
  - name: "ciso-security-scanning-pipeline"
    id: "C02JTCEC00H"

# Troubleshooting channels searched during failure diagnostics
troubleshooting_channels:
  - "scs_code-signing"
  - "scs-opensource-scan"
  - "scs-sast"
  - "cd-tekton-users-shared"
  - "ciso-security-scanning-pipeline"
```

---

## Authentication Guide

### 1. GitHub Token
1. Navigate to **https://github.ibm.com/settings/tokens** -> **Generate new token (classic)**.
2. Provide a descriptive note (e.g., `sps-manoeuvre`).
3. Select scope: **`repo`** (Full control of private repositories).
4. Paste into setup prompt or `.bob/mcp.json`.

### 2. Slack Incoming Webhook
1. Navigate to **https://api.slack.com/apps**.
2. Select or create your team Slack app -> **Incoming Webhooks**.
3. Activate webhooks and click **Add New Webhook to Workspace**.
4. Select your output alert channel (e.g. `#sps-updates-modernization`).

### 3. Slack Channel Reading
- **macOS:** Auto-extracted from your local Slack desktop client storage via Chromium Safe Storage key. Run `sps-manoeuvre --bootstrap` once to grant access and cache the derived key.
- **Linux/Windows:** Extract `xoxc-` token from browser DevTools -> Network requests and `d` cookie value, then populate `SLACK_USER_TOKEN` and `SLACK_COOKIE` in `.bob/mcp.json`.

---

## Commands Reference

The CLI entrypoint supports multiple operational flags:

```bash
# Interactive setup wizard
sps-manoeuvre --setup

# Diagnostic health check
sps-manoeuvre --doctor

# One-time Slack Keychain token extraction (macOS)
sps-manoeuvre --bootstrap

# Single-pass announcement scan and repository alert dispatch
sps-manoeuvre --run

# Continuous pipeline failure monitor (polls every 5 minutes)
sps-manoeuvre --monitor

# Start MCP stdio server (invoked automatically by Bob)
sps-manoeuvre
```

*(All commands can also be run using `python3 -m sps_manoeuvre <flag>`)*

---

## Daily Automation (macOS Launchd)

Automate daily announcement checks at 09:00 AM using `launchd`:

```bash
# 1. Edit plist paths to point to your repository clone
nano scripts/com.sps-manoeuvre.daily-run.plist

# 2. Copy to User LaunchAgents
cp scripts/com.sps-manoeuvre.daily-run.plist ~/Library/LaunchAgents/

# 3. Load the agent
launchctl load ~/Library/LaunchAgents/com.sps-manoeuvre.daily-run.plist

# 4. Verify status
launchctl list | grep sps-manoeuvre
```
Logs are automatically written and rotated in `.bob/daily-run.log`.

---

## Troubleshooting

| Symptom | Cause | Solution |
|---|---|---|
| `sps-manoeuvre --doctor` fails on Slack Key | Slack Safe Storage key not bootstrapped | Run `sps-manoeuvre --bootstrap` in terminal and click "Allow" |
| `Missing required configuration key(s)` | `.bob/mcp.json` is missing or missing tokens | Run `sps-manoeuvre --setup` to configure credentials |
| GitHub API 401 / 404 on repo scan | GITHUB_TOKEN invalid or missing repo permissions | Verify token has `repo` scope on `github.ibm.com/settings/tokens` |
| `No matching files found in any repo` | Patterns do not match repository contents | Check repository files against announcement rule patterns |
| `Slack token auto-refresh failed` | Desktop Slack closed or not logged into workspace | Ensure Slack desktop app is open and logged into IBM workspace |
| Bob MCP tool `ping` fails | `cwd` in `.bob/mcp.json` incorrect or server not reloaded | Verify `.bob/mcp.json` points to valid paths; reload MCP in Bob Settings |

---

## Architecture & Flows

For in-depth architectural specifications and flow diagrams:
- [Pipeline Monitor Flow & Sequence Diagrams](docs/pipeline_monitor_flow.md)
- [Zero-Secrets Production Architecture](docs/automation-setup.md)

---

## Contributing & Development

### Running Tests
```bash
python3 -m unittest discover -s tests -p "test_*.py"
```

### Development Guidelines
1. Do not commit `.bob/mcp.json`, `.bob/slack-key.bin`, or `.env`.
2. Keep dependencies minimal; avoid unnecessary external frameworks.
3. Test all changes with `sps-manoeuvre --doctor` before submitting pull requests.
