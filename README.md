# SPS Manoeuvre

Automated maintenance and intelligence for IBM Cloud Secure Pipeline Service (SPS) across multi-repository toolchains.

Operates in two complementary modes: as an interactive [Bob](https://bob.ibm.com) MCP server for assistive PR creation and troubleshooting, and as an automated background runner that monitors SPS announcement channels, identifies impacted repositories, dispatches formatted alerts, and diagnoses Tekton pipeline failures.

> **Getting started?** See [SETUP.md](SETUP.md) for the step-by-step installation guide.

---

## Repository Layout

| Path | Purpose |
|---|---|
| `src/sps_manoeuvre/__main__.py` | CLI entry point — dispatches `--setup`, `--doctor`, `--run`, `--monitor`, and MCP server mode |
| `src/sps_manoeuvre/main.py` | MCP server startup — registers all tools and starts the stdio transport |
| `src/sps_manoeuvre/monitor.py` | Announcement scan pipeline and Tekton failure monitor loop |
| `src/sps_manoeuvre/slack_client.py` | Reads Slack announcement/troubleshooting channels; posts webhook alerts |
| `src/sps_manoeuvre/slack_token_refresh.py` | Validates `SLACK_USER_TOKEN` and `SLACK_COOKIE` are present in the environment |
| `src/sps_manoeuvre/github_client.py` | Scans repositories, applies changes, and creates fix PRs via the GitHub API |
| `src/sps_manoeuvre/ibmcloud_client.py` | Fetches Tekton pipeline run logs from IBM Cloud for failure diagnosis |
| `src/sps_manoeuvre/config.py` | Loads `config.yaml`, channel registries, and processed-message deduplication state |
| `src/sps_manoeuvre/setup_wizard.py` | Interactive first-run wizard — writes `.bob/mcp.json` and scaffolds template files |
| `src/sps_manoeuvre/doctor.py` | Health-check command — verifies dependencies, credentials, and API connectivity |
| `src/sps_manoeuvre/repos.json` | Watchlist of repositories to scan (created from template during `--setup`) |
| `src/sps_manoeuvre/config.yaml.example` | Annotated template for channel and workspace customisation |
| `.bob/mcp.json` | Bob MCP server registration and injected environment variables (written by `--setup`) |
| `scripts/` | Launchd plist for macOS daily automation |
| `docs/` | Architecture diagrams and pipeline monitor flow documentation |

---

## MCP Tools

These tools are available to Bob when the MCP server is running.

| Tool | Description |
|---|---|
| `ping` | Health check — returns `pong` to confirm the server is reachable |
| `fetch_announcements` | Fetches the latest unprocessed messages from the SPS announcement Slack channels |
| `scan_repos_for_announcement` | Given an announcement text, identifies which watched repositories are impacted and what changes are needed |
| `apply_fix_to_repo` | Applies a suggested pipeline config change to a repository and optionally opens a PR |
| `search_troubleshooting` | Searches SPS troubleshooting Slack channels for threads matching a query; returns messages and their replies |
| `get_pipeline_failure_logs` | Fetches the Tekton pipeline run logs for a given IBM Cloud toolchain and pipeline run ID |
| `diagnose_pipeline_failure` | Combines log fetching and troubleshooting search to produce a diagnosis and suggested fix for a failed pipeline run |

---

## Commands Reference

| Command | Description |
|---|---|
| `sps-manoeuvre --setup` | Interactive wizard — configures `.bob/mcp.json`, Slack tokens, and repo watchlist |
| `sps-manoeuvre --doctor` | Diagnostic health check — verifies all dependencies, credentials, and API connectivity |
| `sps-manoeuvre --run` | Single-pass announcement scan → repo impact assessment → webhook alert dispatch |
| `sps-manoeuvre --monitor` | Continuous pipeline failure monitor (polls every 5 minutes) |
| `sps-manoeuvre` | Start the MCP stdio server (invoked automatically by Bob) |

All commands can also be run as `python3 -m sps_manoeuvre <flag>`.

---

## Configuration Reference

### Environment variables (set via `--setup`, stored in `.bob/mcp.json`)

| Variable | Required | Description |
|---|---|---|
| `GITHUB_TOKEN` | Yes | PAT for `github.ibm.com` with `repo` scope |
| `SLACK_WEBHOOK_URL` | Yes | Incoming webhook URL for outbound alerts |
| `SLACK_USER_TOKEN` | Yes | Slack session token (`xoxc-...`) for reading channels |
| `SLACK_COOKIE` | Yes | Slack session cookie (`xoxd-...`) for reading channels |
| `IBM_CLOUD_API_KEY` | Optional | IAM key for Tekton pipeline log fetching (`--monitor` only) |

### Channel customisation (`config.yaml`)

Copy `src/sps_manoeuvre/config.yaml.example` to `config.yaml` in the project root to override defaults:

```yaml
slack_output_channel: "sps-updates-modernization"

pipeline_notifications_channel: "cics-sps-notifications"
pipeline_notifications_channel_id: "C07LS8K2DTQ"

announcement_channels:
  - name: "one-pipeline-announce"
    id: "C04TZHM220P"
  - name: "devops-compliance"
    id: "CFQHG5PP1"
  - name: "secure-pipelines-service"
    id: "C04SYRN5X88"
  - name: "ciso-security-scanning-pipeline"
    id: "C02JTCEC00H"

troubleshooting_channels:
  - "scs_code-signing"
  - "scs-opensource-scan"
  - "scs-sast"
  - "cd-tekton-users-shared"
  - "ciso-security-scanning-pipeline"
```

---

## Daily Automation (macOS)

Automate daily announcement checks at 09:00 using `launchd`:

```bash
# Edit plist paths to point to your clone
nano scripts/com.sps-manoeuvre.daily-run.plist

# Install and load
cp scripts/com.sps-manoeuvre.daily-run.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.sps-manoeuvre.daily-run.plist
```

Logs are written to `.bob/daily-run.log`.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `SLACK_USER_TOKEN or SLACK_COOKIE is not set` | Tokens not configured | Re-run `sps-manoeuvre --setup` and paste your Slack tokens |
| `Missing required configuration key(s)` | `.bob/mcp.json` missing or incomplete | Run `sps-manoeuvre --setup` |
| GitHub API 401 / 404 on repo scan | `GITHUB_TOKEN` invalid or missing `repo` scope | Regenerate at `github.ibm.com/settings/tokens` |
| `No matching files found in any repo` | Announcement patterns don't match repo contents | Check repo files against the announced change |
| Bob MCP tool `ping` fails | `cwd` in `.bob/mcp.json` wrong or server not reloaded | Re-run `--setup`; reload MCP in Bob → Settings → MCP Servers |

---

## Architecture

- [Pipeline Monitor Flow & Sequence Diagrams](docs/pipeline_monitor_flow.md)
- [Zero-Secrets Production Architecture](docs/automation-setup.md)

---

## Development

```bash
# Run tests
python3 -m unittest discover -s tests -p "test_*.py"
```

Do not commit `.bob/mcp.json` or `.env` — they contain live credentials.
