# SPS Pipeline Bot — Setup Guide

This bot monitors IBM Cloud SPS pipeline announcement channels, identifies which of your
repositories are affected by each announcement, and posts a change notice to your team's
Slack channel — all automatically from inside Bob.

---

## What you need before starting

| Requirement | Notes |
|---|---|
| macOS | Token auto-refresh reads from the Slack desktop app. Linux/Windows need manual token steps (see [Manual token setup](#manual-token-setup-non-macos)). |
| [Bob](https://bob.ibm.com) installed | The bot runs as a Bob MCP server. |
| Slack desktop app installed and logged in | Required for automatic token refresh. |
| Python 3.10+ | Check with `python3 --version`. |
| A GitHub PAT for `github.ibm.com` | Needs `repo` scope. |
| An incoming webhook URL | From any existing Slack app pointed at your output channel — or create one (see [Step 4](#step-4--slack-incoming-webhook)). |

---

## Step 1 — Clone the repo

```bash
git clone https://github.ibm.com/CICS/sps-pipeline-bot.git
cd sps-pipeline-bot
```

---

## Step 2 — Install Python dependencies

```bash
pip3 install -e ./src
```

This installs: `mcp`, `slack-sdk`, `PyGithub`, `httpx`, `pycryptodome`.

---

## Step 3 — GitHub Personal Access Token

1. Go to **https://github.ibm.com/settings/tokens**
2. Click **Generate new token (classic)**
3. Name: `sps-pipeline-bot`
4. Scopes: tick **`repo`** (full) — needed to search files and open PRs
5. Click **Generate token**, copy the `ghp_...` value

> For **public GitHub** repos (`github.com`), create a separate token at
> https://github.com/settings/tokens with the same `repo` scope. The bot uses
> the same `GITHUB_TOKEN` for both hosts — make sure it has access to both if needed.

---

## Step 4 — Slack incoming webhook

The bot **reads** Slack channels using your personal session (no app needed).
For **posting** alerts to your team channel, it uses an incoming webhook from any
Slack app you already have, or you can create a new one:

### Option A — Use an existing Slack app's webhook
1. Go to **https://api.slack.com/apps** → open your app → **Incoming Webhooks**
2. Find or add a webhook for your output channel (e.g. `#sps-updates-modernization`)
3. Copy the webhook URL: `https://hooks.slack.com/services/T.../B.../...`

### Option B — Create a new minimal Slack app (no scopes needed)
1. Go to **https://api.slack.com/apps** → **Create New App** → **From scratch**
2. Name it `SPS Pipeline Alerts`, pick your IBM Z workspace
3. Go to **Incoming Webhooks** → toggle **Activate Incoming Webhooks** → ON
4. Click **Add New Webhook to Workspace** → pick your output channel
5. Copy the webhook URL

> **Note:** Incoming webhooks only need admin approval if your workspace requires it.
> If you already have a notification app with a webhook, just reuse that URL — no new
> app needed.

---

## Step 5 — Bootstrap Slack token auto-refresh (macOS only)

The bot reads your Slack session token and cookie directly from the Slack desktop app
on disk. The cookie is encrypted with a key stored in macOS Keychain. You only need to
run this **once** — it caches the key so future runs never touch Keychain again.

```bash
cd sps-pipeline-bot/src
python3 -m sps_pipeline_bot --bootstrap
```

macOS will show a **"python3 wants to access Slack Safe Storage"** dialog.
Click **Allow**. That's it — the key is cached to `~/.bob/slack-key.bin`.

> If you see `command not found` make sure you're running `python3 -m ...` not just `--bootstrap` on its own.

---

## Step 6 — Configure Bob MCP server

Create or edit **`.bob/mcp.json`** inside the cloned project directory:

```json
{
  "mcpServers": {
    "sps-pipeline-bot": {
      "command": "python3",
      "args": ["-m", "sps_pipeline_bot"],
      "cwd": "/path/to/sps-pipeline-bot/src",
      "env": {
        "GITHUB_TOKEN": "ghp_your-token-here",
        "SLACK_WEBHOOK_URL": "https://hooks.slack.com/services/T.../B.../..."
      }
    }
  }
}
```

Replace:
- `/path/to/sps-pipeline-bot/src` — the absolute path to the `src` folder you cloned
- `GITHUB_TOKEN` — your PAT from Step 3
- `SLACK_WEBHOOK_URL` — your webhook URL from Step 4

> `SLACK_USER_TOKEN` and `SLACK_COOKIE` are **not** needed here — the bot reads them
> automatically from your Slack desktop app (Step 5).

---

## Step 7 — Add your repositories to the watchlist

Open Bob and ask:

> *add repo CICS/my-repo to the sps pipeline bot watchlist*

Or edit [`src/sps_pipeline_bot/repos.json`](src/sps_pipeline_bot/repos.json) directly:

```json
{
  "repos": [
    { "repo": "CICS/my-repo", "description": "My CICS plugin" },
    { "repo": "IBM/cics-bundle-maven", "description": "CICS Bundle Maven" }
  ]
}
```

Supported hosts:
- `CICS/...` and other orgs → `github.ibm.com`
- `IBM/...` → `github.com` (public GitHub)

---

## Step 8 — Reload Bob and test

1. In Bob: **Settings → MCP Servers → Reload** (or restart Bob)
2. Test connectivity:
   > *ping the sps pipeline bot*

   Bob should respond with `pong`.

3. Test Slack reading:
   > *fetch the latest SPS announcements*

4. Test Slack posting:
   > *send a test alert to the output channel for repo CICS/my-repo*

---

## Day-to-day usage

Ask Bob naturally:

| What you want | What to say |
|---|---|
| Check for new announcements | *"fetch the latest SPS announcements"* |
| See which repos are affected | *"scan my repos for pipeline config files"* |
| Post alert to Slack | *"post an alert to Slack for affected repos"* |
| Search for a fix | *"troubleshoot: GaraSign loader path not found"* |
| Raise a PR | *"create a PR in CICS/my-repo to update the image tag"* |
| Manage watchlist | *"list my watched repos"* / *"add repo CICS/new-repo"* |

The full automated workflow (fetch → analyse → post alert → optionally raise PRs) is
orchestrated by Bob — the MCP server provides the data and action tools, Bob does the reasoning.

---

## How the bot reads Slack without a Slack app

The bot uses your **personal Slack session** (the same one your desktop app uses) to
call the Slack API. This means:

- ✅ No Slack app registration or admin approval needed for reading
- ✅ No OAuth scopes to configure
- ✅ Works on IBM enterprise Slack where `conversations.list` is blocked
- ✅ Tokens refresh automatically from the Slack desktop app on disk
- ⚠️ Reading is done as *you* — the bot sees what you see in Slack

The session token (`xoxc-`) lives in `~/Library/Application Support/Slack/Local Storage/leveldb/`
and the cookie (`xoxd`) in `~/Library/Application Support/Slack/Cookies` — both are read
directly at startup, no browser interaction needed.

---

## Manual token setup (non-macOS)

On Linux or Windows, the auto-refresh from disk isn't available. Set tokens manually:

1. Open **Slack in Chrome** → DevTools (`F12`) → **Network** tab
2. Click any channel to trigger a request
3. Filter by `api.slack.com` → click any request → **Headers**
4. Copy:
   - `Authorization: Bearer xoxc-...` → `SLACK_USER_TOKEN`
   - `Cookie: d=...` → `SLACK_COOKIE` (just the value after `d=`, before the next `;`)
5. Add both to the `env` block in `.bob/mcp.json`:

```json
"env": {
  "SLACK_USER_TOKEN": "xoxc-...",
  "SLACK_COOKIE": "xoxd-...",
  "GITHUB_TOKEN": "ghp_...",
  "SLACK_WEBHOOK_URL": "https://hooks.slack.com/services/..."
}
```

Tokens expire when you log out of Slack. Re-extract when the bot stops reading channels.

---

## Re-bootstrap after Keychain password change (macOS)

If your macOS login password changes, the cached key becomes invalid. Re-run:

```bash
cd sps-pipeline-bot/src
python3 -m sps_pipeline_bot --bootstrap
```

Click Allow in the macOS dialog. Done.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ping` returns nothing / MCP server not found | Check `cwd` path in `mcp.json`, reload Bob MCP servers |
| `SLACK_USER_TOKEN not set` | Run `--bootstrap` (macOS) or set tokens manually |
| `enterprise_is_restricted` error | Already handled — channel IDs are hardcoded, `conversations.list` is not used |
| GitHub 404 on a repo | Check the repo name format (`ORG/NAME`) and that your PAT has `repo` scope |
| Webhook POST fails | Verify `SLACK_WEBHOOK_URL` is correct and the webhook is still active |
| `Slack AES key not found` | Run `--bootstrap` again — `~/.bob/slack-key.bin` may have been deleted |

---

## What gets posted to Slack

Each alert looks like this:

```
🔧 SPS Pipeline Change Required
────────────────────────────────
Repository:           Change:
CICS/my-repo          Migrate to Mend SCA CLI scan

What to do: Add opt-in-mend-sca: 1 to .pipeline-scan-config.yaml
Applied change: PR raised to update compliance config
PR: https://github.ibm.com/CICS/my-repo/pull/42

View original announcement ↗
```

The **PR link** is live when Bob has already raised one. If not, you can ask Bob to
raise it after reviewing the proposed changes.

---

## Security notes

- `~/.bob/slack-key.bin` is `chmod 600` — owner read-only. Do not commit it.
- `GITHUB_TOKEN` in `mcp.json` is local to your machine. Do not commit `mcp.json`.
- The bot never writes to Slack channels directly — only via an incoming webhook URL
  that you explicitly configure.
- Add to `.gitignore`:
  ```
  .bob/mcp.json
  .bob/slack-key.bin
  ~/.bob/sps-state.json
  ```
