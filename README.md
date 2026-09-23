# SPS Pipeline Bot

An IBM Bob MCP server that automates IBM Cloud Secure Pipeline Service (SPS) maintenance across multiple repositories.

The bot has **two jobs**:

1. **Announcement watcher** — monitors SPS announcement channels on IBM enterprise Slack, identifies which of your watched repos are affected by a change, and posts a formatted alert to your team channel (including a link to any PR it raises).
2. **Failure monitor** — watches your pipeline notifications channel for failures, fetches the real error message from IBM Cloud Tekton logs, and either surfaces the `BUILD FAILURE` context directly or searches SPS troubleshooting channels for a known fix.

Both jobs are powered by [Bob](https://bob.ibm.com) as an MCP server, and can also run standalone from the command line.

---

## Contents

- [How it works](#how-it-works)
- [Prerequisites](#prerequisites)
- [Required credentials and variables](#required-credentials-and-variables)
- [Installation](#installation)
- [Configuration](#configuration)
- [Daily automation (macOS launchd)](#daily-automation-macos-launchd)
- [Day-to-day usage with Bob](#day-to-day-usage-with-bob)
- [Running standalone](#running-standalone)
- [Repo watchlist](#repo-watchlist)
- [How Slack reading works (no app needed)](#how-slack-reading-works-no-app-needed)
- [Manual token setup (non-macOS)](#manual-token-setup-non-macos)
- [Troubleshooting](#troubleshooting)
- [Security notes](#security-notes)

---

## How it works

```
IBM Slack announcement channels
        │
        │  (your Slack session — no app needed)
        ▼
 fetch_announcements()   ←── Bob calls this tool
        │
        │  classify by keyword → action_required?
        ▼
 scan_repos_tool()       ←── finds affected repos
        │
        ▼
 get_repo_files()        ←── Bob reads current file contents
        │
        │  Bob generates the diff, shows it to you for confirmation
        ▼
 create_pr()             ←── opens PR on github.ibm.com
        │
        ▼
 post_webhook_alert()    ←── posts to your team Slack channel
```

For pipeline failures:

```
#cics-sps-notifications  (polled every 5 min)
        │
        ▼
 IBM Cloud Tekton API   ←── fetch step logs
        │
        │  search for "BUILD FAILURE"
        ├── found  →  show error context in Slack
        └── not found → search_troubleshoot_channels()  →  post findings
```

---

## Prerequisites

| Requirement | Notes |
|---|---|
| **macOS** | Slack token auto-refresh reads from the Slack desktop app on disk. Linux/Windows users must set tokens manually — see [Manual token setup](#manual-token-setup-non-macos). |
| **[Bob](https://bob.ibm.com) installed** | The bot runs as a Bob MCP server. Install Bob from https://bob.ibm.com. |
| **Slack desktop app — installed and logged in** | Required for automatic token refresh on macOS. Must be the IBM enterprise Slack workspace. |
| **Python 3.10 or later** | Check: `python3 --version`. Install via [pyenv](https://github.com/pyenv/pyenv) or https://python.org. |
| **GitHub Personal Access Token (PAT)** | For `github.ibm.com`. Needs `repo` scope (full). See [Step 3](#step-3--github-personal-access-token). |
| **Slack incoming webhook URL** | For posting outbound alerts to your team channel. Comes from a Slack app's Incoming Webhooks page. See [Step 4](#step-4--slack-incoming-webhook). |
| **IBM Cloud API key** | For log fetching in the failure monitor. Create one at https://cloud.ibm.com/iam/apikeys. Required only for the `--monitor` mode and the `IBM_CLOUD_API_KEY` variable. |

---

## Required credentials and variables

These are the **only values you need to provide**. All are set in `.bob/mcp.json` (never committed — gitignored).

| Variable | Required | Description | How to get it |
|---|---|---|---|
| `GITHUB_TOKEN` | ✅ Always | PAT for `github.ibm.com` with `repo` scope | [github.ibm.com/settings/tokens](https://github.ibm.com/settings/tokens) → Generate new token (classic) → tick `repo` |
| `SLACK_WEBHOOK_URL` | ✅ Always | Incoming webhook URL for your team's output channel | Your Slack app → Incoming Webhooks → Add webhook for e.g. `#sps-updates-modernization` |
| `IBM_CLOUD_API_KEY` | ⚠️ Failure monitor only | IBM Cloud API key for fetching Tekton run logs | [cloud.ibm.com/iam/apikeys](https://cloud.ibm.com/iam/apikeys) → Create |
| `SLACK_USER_TOKEN` | macOS: auto | Your personal Slack session token (`xoxc-`) | Auto-extracted from Slack desktop app after `--bootstrap`. Manual: see [non-macOS setup](#manual-token-setup-non-macos). |
| `SLACK_COOKIE` | macOS: auto | Your Slack session cookie (`xoxd-`) | Auto-extracted from Slack desktop app after `--bootstrap`. Manual: see [non-macOS setup](#manual-token-setup-non-macos). |

> **macOS users:** `SLACK_USER_TOKEN` and `SLACK_COOKIE` are extracted automatically from your Slack desktop app at runtime — you do **not** need to set them in `mcp.json`. Just run `--bootstrap` once (Step 5).

> **Linux / Windows users:** Set `SLACK_USER_TOKEN` and `SLACK_COOKIE` manually in `mcp.json` — see [Manual token setup](#manual-token-setup-non-macos).

---

## Installation

### Step 1 — Clone the repo

```bash
git clone https://github.ibm.com/anushka-p/sps-pipeline-bot.git
cd sps-pipeline-bot
```

### Step 2 — Install Python dependencies

```bash
pip3 install -e .
```

This installs: `mcp`, `slack-sdk`, `PyGithub`, `httpx`, `pycryptodome`.

---

### Step 3 — GitHub Personal Access Token

1. Go to **https://github.ibm.com/settings/tokens**
2. Click **Generate new token (classic)**
3. Name: `sps-pipeline-bot`
4. Scopes: tick **`repo`** (full) — this covers reading files and creating PRs
5. Copy the `ghp_...` value — you'll add it to `mcp.json` in Step 6

> If you also watch repos on `github.com` (e.g. `IBM/...`), use a PAT that has access to both hosts, or create a separate token for public GitHub.

---

### Step 4 — Slack incoming webhook

The bot **reads** Slack using your personal session (no app needed — see [How Slack reading works](#how-slack-reading-works-no-app-needed)).
For **posting** alerts it needs an incoming webhook from a Slack app:

1. Go to **https://api.slack.com/apps** → open or create an app → **Incoming Webhooks**
2. Toggle **Activate Incoming Webhooks** → ON
3. Click **Add New Webhook to Workspace** → choose your output channel (e.g. `#sps-updates-modernization`)
4. Copy the webhook URL: `https://hooks.slack.com/services/T.../B.../...`

---

### Step 5 — Bootstrap Slack token auto-refresh (macOS only)

Run this **once** from a terminal — it caches the AES key needed to read your Slack session:

```bash
cd sps-pipeline-bot/src
python3 -m sps_pipeline_bot --bootstrap
```

macOS will show a **"python3 wants to access Slack Safe Storage"** Keychain dialog — click **Allow**.

The derived key is saved to `.bob/slack-key.bin` (gitignored, `chmod 600`).
From now on, the bot reads your Slack tokens automatically at runtime — no further action needed.

---

### Step 6 — Configure the Bob MCP server

Create or edit **`.bob/mcp.json`** inside the project directory:

```json
{
  "mcpServers": {
    "sps-pipeline-bot": {
      "command": "python3",
      "args": ["-m", "sps_pipeline_bot"],
      "cwd": "/absolute/path/to/sps-pipeline-bot/src",
      "env": {
        "GITHUB_TOKEN": "ghp_your-token-here",
        "SLACK_WEBHOOK_URL": "https://hooks.slack.com/services/T.../B.../...",
        "IBM_CLOUD_API_KEY": "your-ibm-cloud-api-key"
      }
    }
  }
}
```

> **Note:** Replace `/absolute/path/to/sps-pipeline-bot/src` with the actual path on your machine.
>
> `SLACK_USER_TOKEN` and `SLACK_COOKIE` are **not** needed here on macOS — the bot reads them live from your Slack desktop app.
>
> On Linux/Windows, add them manually:
> ```json
> "SLACK_USER_TOKEN": "xoxc-...",
> "SLACK_COOKIE": "xoxd-..."
> ```

---

### Step 7 — Add your repositories to the watchlist

Ask Bob:
> *"add repo CICS/my-repo to the sps pipeline bot watchlist"*

Or edit `src/sps_pipeline_bot/repos.json` directly:

```json
{
  "repos": [
    { "repo": "CICS/my-repo", "description": "My CICS plugin" },
    { "repo": "IBM/cics-bundle-maven", "description": "CICS Bundle Maven (github.com)" }
  ]
}
```

Format is `ORG/NAME`. Repos prefixed with `IBM/` are looked up on `github.com`; all others on `github.ibm.com`.

---

### Step 8 — Reload Bob and test

1. In Bob: **Settings → MCP Servers → Reload** (or restart Bob)
2. Ask Bob: *"ping the sps pipeline bot"* → should return `pong`
3. Ask Bob: *"fetch the latest SPS announcements"*
4. Ask Bob: *"list my watched repos"*

---

## Configuration

### Channel registry (`src/sps_pipeline_bot/config.py`)

The bot monitors these Slack channels by default. Channel IDs are hardcoded because `conversations.list` is blocked on IBM enterprise Slack.

**Announcement channels** (polled for new SPS changes):

| Channel | Channel ID |
|---|---|
| `#one-pipeline-announce` | `C04TZHM220P` |
| `#devops-compliance` | `CFQHG5PP1` |
| `#secure-pipelines-service` | `C04SYRN5X88` |
| `#ciso-security-scanning-pipeline` | `C02JTCEC00H` |

**Troubleshooting channels** (searched when diagnosing failures):

| Channel |
|---|
| `#scs_code-signing` |
| `#scs-opensource-scan` |
| `#scs-sast` |
| `#cd-tekton-users-shared` |
| `#ciso-security-scanning-pipeline` |

To add a channel: find its ID (right-click the channel in Slack → Copy link — the ID is the `C...` part at the end), then add it to `ANNOUNCEMENT_CHANNELS` / `ANNOUNCEMENT_CHANNEL_IDS` in `config.py`.

### Pipeline notifications channel

Failures are detected from `#cics-sps-notifications` (ID: `C07LS8K2DTQ`). Update `PIPELINE_NOTIFICATIONS_CHANNEL` and `PIPELINE_NOTIFICATIONS_CHANNEL_ID` in `config.py` if your team uses a different channel.

---

## Daily automation (macOS launchd)

To run the announcement check automatically every day at 09:00:

```bash
# 1. Edit the plist — update both path values to your actual project location
nano scripts/com.sps-pipeline-bot.daily-run.plist

# 2. Install
cp scripts/com.sps-pipeline-bot.daily-run.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.sps-pipeline-bot.daily-run.plist

# 3. Verify it's loaded
launchctl list | grep sps-pipeline-bot

# 4. To run immediately (test)
launchctl start com.sps-pipeline-bot.daily-run

# 5. To uninstall
launchctl unload ~/Library/LaunchAgents/com.sps-pipeline-bot.daily-run.plist
```

Logs are written to `.bob/daily-run.log` (last 500 lines are kept).

---

## Day-to-day usage with Bob

| What you want | What to say to Bob |
|---|---|
| Check for new SPS announcements | *"fetch the latest SPS announcements"* |
| See which repos are affected | *"scan my repos for pipeline config files"* |
| Read current file content | *"get the pipeline config files from CICS/my-repo"* |
| Create a PR with a fix | *"create a PR in CICS/my-repo to update the compliance-checks image to 3.64"* |
| Push extra changes to an existing PR branch | *"push these changes to branch sps-bot/my-fix in CICS/my-repo"* |
| Search for a known fix | *"troubleshoot: GaraSign loader path not found"* |
| Post an alert to Slack | *"post an alert to Slack for CICS/my-repo"* |
| Search all files for a pattern | *"search CICS/my-repo for all usages of get_env"* |
| List watched repos | *"list my watched repos"* |
| Add a repo | *"add repo CICS/new-repo to the watchlist"* |
| Remove a repo | *"remove repo CICS/old-repo from the watchlist"* |
| Smoke test | *"ping the sps pipeline bot"* |

### Full end-to-end workflow

Bob handles the entire workflow automatically when asked:

1. `fetch_announcements` — reads unprocessed messages from announcement channels
2. Classifies each message — action required? what category? what files to look for?
3. `scan_repos_tool` — finds which watched repos contain affected files
4. `get_repo_files` — fetches current file contents so Bob can see what needs changing
5. **Shows you the proposed diff — waits for your confirmation**
6. `create_pr` — opens a PR on github.ibm.com with the changes
7. `post_webhook_alert` — notifies your team channel with a link to the PR

---

## Running standalone

The bot can run without Bob, directly from the command line:

```bash
cd sps-pipeline-bot/src

# One-time: cache the Slack key (macOS only)
python3 -m sps_pipeline_bot --bootstrap

# Fetch announcements → scan repos → post Slack alerts (runs once, safe to schedule)
python3 -m sps_pipeline_bot --run

# Watch for pipeline failures (runs continuously, polls every 5 minutes)
python3 -m sps_pipeline_bot --monitor
```

Credentials must be exported as environment variables before running standalone:

```bash
export GITHUB_TOKEN="ghp_..."
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
export IBM_CLOUD_API_KEY="..."   # only needed for --monitor
```

Or use the `.env.example` file as a template:

```bash
cp .env.example .env
# edit .env with your values
export $(cat .env | xargs)
python3 -m sps_pipeline_bot --run
```

---

## Repo watchlist

The watchlist lives in `src/sps_pipeline_bot/repos.json`. It is not gitignored — commit your team's watchlist so everyone starts with the right repos.

```json
{
  "repos": [
    { "repo": "CICS/cics-explorer-docs",    "description": "CICS Explorer documentation" },
    { "repo": "CICS/cics-cm-plugin",         "description": "CICS CM Plugin" },
    { "repo": "IBM/cics-bundle-maven",        "description": "CICS Bundle Maven (github.com)" }
  ]
}
```

Repos with org prefix `IBM/` are fetched from `github.com`. All others from `github.ibm.com`.

---

## How Slack reading works (no app needed)

The bot reads Slack channels using your **personal Slack session** — the same session your Slack desktop app uses.

- ✅ No Slack app registration or workspace admin approval needed for reading
- ✅ Works on IBM enterprise Slack where `conversations.list` is blocked
- ✅ Tokens refresh automatically from the Slack desktop app on disk (macOS)
- ⚠️ Reading is done as *you* — the bot sees what you can see

On macOS, the session token (`xoxc-`) lives in:
`~/Library/Application Support/Slack/Local Storage/leveldb/`

And the cookie (`xoxd-`) in:
`~/Library/Application Support/Slack/Cookies`

The `--bootstrap` command derives and caches the AES key needed to decrypt the cookie, so subsequent runs never touch the macOS Keychain.

---

## Manual token setup (non-macOS)

On Linux or Windows, extract your Slack tokens from the browser:

1. Open **Slack in Chrome** → your IBM Z workspace
2. Open **DevTools** (`F12`) → **Network** tab
3. Click any channel to trigger a request
4. Filter by **`conversations.history`** or **`api.slack.com`**
5. Click a request → **Headers**:
   - Copy `Authorization: Bearer xoxc-...` → this is `SLACK_USER_TOKEN`
   - Copy `Cookie: d=xoxd-...` → copy just the `xoxd-...` value → this is `SLACK_COOKIE`

Add both to `.bob/mcp.json`:

```json
"env": {
  "SLACK_USER_TOKEN": "xoxc-...",
  "SLACK_COOKIE": "xoxd-...",
  "GITHUB_TOKEN": "ghp_...",
  "SLACK_WEBHOOK_URL": "https://hooks.slack.com/services/...",
  "IBM_CLOUD_API_KEY": "..."
}
```

The `xoxc-` token stays valid until you log out of Slack in your browser. When it expires, re-extract and update `mcp.json`.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ping` returns nothing / no response | Check `cwd` in `mcp.json` is the `src/` directory. Reload Bob MCP servers. |
| `SLACK_USER_TOKEN not set` | macOS: run `python3 -m sps_pipeline_bot --bootstrap`. Non-macOS: set token manually in `mcp.json`. |
| `Slack AES key not found` | Run `--bootstrap` again — `.bob/slack-key.bin` may be missing or corrupt. |
| `enterprise_is_restricted` on channel lookup | Already handled — channel IDs are hardcoded in `config.py`. |
| GitHub 404 on a repo | Check format is `ORG/NAME`, PAT has `repo` scope, and you have access to the repo. |
| Webhook POST fails (4xx) | Verify `SLACK_WEBHOOK_URL` is correct, the webhook is active, and the app is still installed. |
| Log fetch times out / no IBM Cloud logs | IBM Cloud API times out for runs older than ~3 weeks — expected. The bot falls back to searching troubleshooting channels. |
| No IBM_CLOUD_API_KEY set | `--monitor` still works — it searches SPS troubleshooting channels as a fallback instead of fetching logs. |
| `pycryptodome` not found | `pip3 install pycryptodome` — or re-run `pip3 install -e .` from the project root. |
| Daily launchd job not running | Check `launchctl list | grep sps-pipeline-bot`. If not listed, `launchctl load ~/Library/LaunchAgents/com.sps-pipeline-bot.daily-run.plist`. Check the log at `.bob/daily-run.log`. |

---

## Security notes

- `.bob/slack-key.bin` — `chmod 600`, gitignored. Never commit this file.
- `.bob/mcp.json` — contains tokens and API keys, gitignored. Never commit this file.
- `.bob/sps-state.json` — contains only Slack message timestamps (no secrets), gitignored.
- The bot **never writes to Slack directly** — all outbound messages go through the webhook URL you configure.
- The bot only needs `repo` scope on GitHub — no admin, no org-level access.
- For a zero-secrets production deployment using IBM Cloud Trusted Profile and Secrets Manager, see [`docs/automation-setup.md`](docs/automation-setup.md).

---

## Project structure

```
sps-pipeline-bot/
├── src/sps_pipeline_bot/
│   ├── __main__.py          Entry point — routes CLI flags
│   ├── main.py              MCP server — all tools Bob calls
│   ├── monitor.py           Announcement runner + failure watcher (automated)
│   ├── slack_client.py      Slack I/O: read channels, search, post webhooks
│   ├── github_client.py     GitHub I/O: scan repos, create PRs
│   ├── ibmcloud_client.py   IBM Cloud Tekton log fetching
│   ├── slack_token_refresh.py  macOS Slack token auto-refresh
│   ├── config.py            Channel IDs, repo list, state paths
│   └── repos.json           Watched repos list (team-local, commit this)
├── scripts/
│   ├── daily-run.sh         Shell wrapper for launchd scheduling
│   └── com.sps-pipeline-bot.daily-run.plist  macOS launchd plist
├── docs/
│   ├── automation-setup.md  Zero-secrets production deployment guide
│   └── pipeline_monitor_flow.md  Full flow diagrams (Mermaid)
├── pyproject.toml           Python package definition + dependencies
├── .env.example             Template for standalone environment variables
├── README.md                This file
└── SETUP.md                 Condensed quick-start guide
```
