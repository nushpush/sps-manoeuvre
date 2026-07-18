# SPS Pipeline Bot — Setup Guide

No Slack app registration required. The bot reads channels using your existing
browser session credentials, and sends alerts via your existing notification app's webhook.

---

## Credentials needed

| Variable | What it is | How to get it |
|----------|-----------|---------------|
| `SLACK_USER_TOKEN` | Your personal Slack session token (`xoxc-`) | Extract from browser — see Step 1 |
| `SLACK_COOKIE` | Your Slack session cookie (`d=`) | Extract from browser — see Step 1 |
| `GITHUB_TOKEN` | PAT for github.ibm.com | See Step 2 |
| `SLACK_WEBHOOK_URL` | Incoming webhook URL from your existing notification app | See Step 3 |

---

## Step 1 — Extract your Slack user token and cookie

Your browser already has a valid Slack session. Extract it like this:

1. Open **Slack in Chrome/Firefox** — go to your IBM Z workspace
2. Open **DevTools** (`Cmd+Option+I` on Mac) → **Network** tab
3. In Slack, click into any channel to trigger a network request
4. In DevTools, filter by **`conversations.history`** or **`api.slack.com`**
5. Click any request to `api.slack.com` → **Headers** tab
6. Find the **Request Headers** — look for:
   - `Authorization: Bearer xoxc-...` → this is your `SLACK_USER_TOKEN`
   - `Cookie: d=...` → copy just the value after `d=` up to the next `;` — this is your `SLACK_COOKIE`

**Alternative (Local Storage):**
1. DevTools → **Application** tab → **Local Storage** → select your Slack workspace URL
2. Search for `xoxc-` — the token is stored there directly

> **Note:** The `xoxc-` token expires when you log out of Slack. If the bot stops working,
> re-extract the token from your browser.

---

## Step 2 — GitHub Personal Access Token

You likely already have one. If not:

1. Go to https://github.ibm.com/settings/tokens
2. Click **Generate new token (classic)**
3. Name it `sps-pipeline-bot`
4. Select scopes: **`repo`** (full) — this includes reading files and creating PRs
5. Click **Generate token** and copy the `ghp_...` value

---

## Step 3 — Webhook URL from your existing notification app

1. Open your existing Slack notification app's configuration
2. Go to **Incoming Webhooks** → find or create a webhook for the channel where
   you want pipeline change alerts to be posted
3. Copy the webhook URL — it looks like:
   `https://hooks.slack.com/services/T.../B.../...`

---

## Step 4 — Set credentials in Bob MCP config

Open [`.bob/mcp.json`](.bob/mcp.json) inside this project directory and fill in the four values:

```json
{
  "mcpServers": {
    "sps-pipeline-bot": {
      "command": "python3",
      "args": ["-m", "sps_pipeline_bot"],
      "cwd": "/Users/anushka/.bob/playground/sps-pipeline-bot/src",
      "env": {
        "SLACK_USER_TOKEN": "xoxc-your-token-here",
        "SLACK_COOKIE": "your-d-cookie-value-here",
        "GITHUB_TOKEN": "ghp_your-pat-here",
        "SLACK_WEBHOOK_URL": "https://hooks.slack.com/services/..."
      }
    }
  }
}
```

---

## Step 5 — Reload Bob and test

1. In Bob Settings → **MCP Servers** → click reconnect / reload
2. In a Bob chat, type:

   > *ping the sps pipeline bot*

   Bob should call the `ping` tool and return `pong`.

3. Test announcement fetching:

   > *check for new SPS announcements*

4. Test troubleshooting:

   > *troubleshoot: GaraSign loader path not found*

---

## Updating your token

The `xoxc-` token is tied to your browser session. It will expire if you:
- Log out of Slack in your browser
- Your session times out (typically after weeks of inactivity)

When that happens, repeat Step 1 and update the token in `mcp.json`.

---

## Channels accessed

**Read (announcements — polled when you ask):**
- `#one-pipeline-announce`
- `#devops-complines`
- `#secure-pipelines-service`

**Read (troubleshooting — searched on demand):**
- `#scs_code-signing`
- `#scs-opensource-scan`
- `#scs-sast`
- `#cd-tekton-users-shared`
- `#ciso-security-scanning-pipeline`

**Write (via your existing notification app webhook):**
- Whatever channel your webhook is configured for
