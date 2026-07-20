# SPS Pipeline Bot — Setup Guide

This bot has two jobs:

1. **Announcement watcher** — monitors IBM Cloud SPS announcement channels, identifies which of your repos are affected, and posts a change notice to your team's Slack channel.
2. **Failure monitor** — watches your pipeline notifications channel for failures, fetches the real error from IBM Cloud logs, and either shows the BUILD FAILURE context or searches SPS troubleshooting channels for a fix.

Both modes run inside Bob as an MCP server, or standalone from the command line.

---

## What you need before starting

| Requirement | Notes |
|---|---|
| macOS | Token auto-refresh reads from the Slack desktop app. Linux/Windows need manual token steps — see [below](#manual-token-setup-non-macos). |
| [Bob](https://bob.ibm.com) installed | The bot runs as a Bob MCP server. |
| Slack desktop app installed and logged in | Required for automatic token refresh. |
| Python 3.10+ | Check with `python3 --version`. |
| A GitHub PAT for `github.ibm.com` | Needs `repo` scope. |
| An incoming Slack webhook URL | From any existing Slack app pointed at your output channel — or create one (see [Step 4](#step-4--slack-incoming-webhook)). |
| IBM Cloud API key | Needed for log fetching in the failure monitor. Create one at https://cloud.ibm.com/iam/apikeys. |

---

## Step 1 — Clone the repo

```bash
git clone https://github.ibm.com/anushka-p/sps-pipeline-bot.git
cd sps-pipeline-bot
```

---

## Step 2 — Install Python dependencies

```bash
pip3 install -e ./src
```

Installs: `mcp`, `slack-sdk`, `PyGithub`, `httpx`, `pycryptodome`.

---

## Step 3 — GitHub Personal Access Token

1. Go to **https://github.ibm.com/settings/tokens**
2. Click **Generate new token (classic)**
3. Name: `sps-pipeline-bot`, scopes: tick **`repo`** (full)
4. Copy the `ghp_...` value

> For `github.com` repos (e.g. `IBM/...`), the same token is used — make sure it has access to both hosts if needed.

---

## Step 4 — Slack incoming webhook

The bot **reads** Slack using your personal session (no app needed).
For **posting** alerts it uses an incoming webhook:

1. Go to **https://api.slack.com/apps** → open or create an app → **Incoming Webhooks**
2. Add a webhook for your output channel (e.g. `#sps-updates-modernization`)
3. Copy the webhook URL: `https://hooks.slack.com/services/T.../B.../...`

---

## Step 5 — Bootstrap Slack token auto-refresh (macOS only)

Run once — caches the AES key needed to decrypt your Slack session cookie:

```bash
cd sps-pipeline-bot/src
python3 -m sps_pipeline_bot --bootstrap
```

macOS will show a **"python3 wants to access Slack Safe Storage"** dialog — click **Allow**.
The key is cached to `.bob/slack-key.bin` inside the project (gitignored).

---

## Step 6 — Configure Bob MCP server

Edit **`.bob/mcp.json`** inside the project directory:

```json
{
  "mcpServers": {
    "sps-pipeline-bot": {
      "command": "python3",
      "args": ["-m", "sps_pipeline_bot"],
      "cwd": "/path/to/sps-pipeline-bot/src",
      "env": {
        "GITHUB_TOKEN": "ghp_your-token-here",
        "SLACK_WEBHOOK_URL": "https://hooks.slack.com/services/T.../B.../...",
        "IBM_CLOUD_API_KEY": "your-ibm-cloud-api-key"
      }
    }
  }
}
```

> `SLACK_USER_TOKEN` and `SLACK_COOKIE` are **not** needed here — the bot reads them
> automatically from your Slack desktop app at runtime.

---

## Step 7 — Add your repositories to the watchlist

Ask Bob:
> *"add repo CICS/my-repo to the sps pipeline bot watchlist"*

Or edit `src/sps_pipeline_bot/repos.json` directly:

```json
{
  "repos": [
    { "repo": "CICS/my-repo", "description": "My CICS plugin" },
    { "repo": "IBM/cics-bundle-maven", "description": "CICS Bundle Maven" }
  ]
}
```

---

## Step 8 — Reload Bob and test

1. In Bob: **Settings → MCP Servers → Reload**
2. > *ping the sps pipeline bot* → should respond `pong`
3. > *fetch the latest SPS announcements*
4. > *start monitoring pipeline failures*

---

## Day-to-day usage

| What you want | What to say to Bob |
|---|---|
| Check for new SPS announcements | *"fetch the latest SPS announcements"* |
| See which repos are affected | *"scan my repos for pipeline config files"* |
| Post alert to Slack | *"post an alert to Slack for affected repos"* |
| Search for a fix | *"troubleshoot: GaraSign loader path not found"* |
| Raise a PR | *"create a PR in CICS/my-repo to update the image tag"* |
| Monitor failures (continuous) | `python3 -m sps_pipeline_bot --monitor` |
| Manage watchlist | *"list my watched repos"* / *"add repo CICS/new-repo"* |

---

## Running standalone (no Bob)

```bash
cd sps-pipeline-bot/src

# One-time: cache the Slack key
python3 -m sps_pipeline_bot --bootstrap

# Fetch announcements → scan repos → post Slack alerts (runs once)
python3 -m sps_pipeline_bot --run

# Watch for pipeline failures (runs continuously, polls every 5 min)
python3 -m sps_pipeline_bot --monitor
```

---

## How the bot reads Slack without a Slack app

The bot uses your **personal Slack session** to call the Slack API:

- ✅ No Slack app registration or admin approval needed for reading
- ✅ Works on IBM enterprise Slack where `conversations.list` is blocked
- ✅ Tokens refresh automatically from the Slack desktop app on disk
- ⚠️ Reading is done as *you* — the bot sees what you see

The session token (`xoxc-`) lives in `~/Library/Application Support/Slack/Local Storage/leveldb/`
and the cookie (`xoxd`) in `~/Library/Application Support/Slack/Cookies`.

---

## Manual token setup (non-macOS)

On Linux or Windows, set tokens manually in `.bob/mcp.json`:

```json
"env": {
  "SLACK_USER_TOKEN": "xoxc-...",
  "SLACK_COOKIE": "xoxd-...",
  "GITHUB_TOKEN": "ghp_...",
  "SLACK_WEBHOOK_URL": "https://hooks.slack.com/services/...",
  "IBM_CLOUD_API_KEY": "..."
}
```

To get the token and cookie: open Slack in Chrome → DevTools → Network tab → any `api.slack.com` request → Headers → copy `Authorization: Bearer xoxc-...` and `Cookie: d=...`.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ping` returns nothing | Check `cwd` path in `mcp.json`, reload Bob MCP servers |
| `SLACK_USER_TOKEN not set` | Run `--bootstrap` (macOS) or set tokens manually |
| `enterprise_is_restricted` | Already handled — channel IDs are hardcoded |
| GitHub 404 on a repo | Check format is `ORG/NAME` and PAT has `repo` scope |
| Webhook POST fails | Verify `SLACK_WEBHOOK_URL` is correct and active |
| `Slack AES key not found` | Run `--bootstrap` again — `.bob/slack-key.bin` may be missing |
| Log fetch times out | IBM Cloud API times out on runs older than ~3 weeks — expected |

---

## Security notes

- `.bob/slack-key.bin` is `chmod 600` and gitignored — do not commit it
- `.bob/mcp.json` contains tokens — do not commit it (already in `.gitignore`)
- The bot never writes to Slack channels directly — only via the webhook URL you configure
