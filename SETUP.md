# SPS Manoeuvre — Quick-Start Setup

Full documentation is in [README.md](README.md). This page is a condensed checklist for getting up and running quickly.

---

## Checklist

- [ ] Python 3.10+ installed (`python3 --version`)
- [ ] Slack desktop app installed and logged in to your IBM workspace
- [ ] Bob installed (https://bob.ibm.com)
- [ ] GitHub PAT for `github.ibm.com` with `repo` scope
- [ ] Slack incoming webhook URL for your output channel
- [ ] IBM Cloud API key (for pipeline failure log fetching — optional)

---

## 1. Install

```bash
git clone https://github.ibm.com/anushka-p/sps-manoeuvre.git
cd sps-manoeuvre
pip3 install -e .
```

## 2. Bootstrap Slack tokens (macOS only — run once)

```bash
cd src
python3 -m sps_manoeuvre --bootstrap
```

Click **Allow** in the macOS Keychain dialog.

## 3. Configure `.bob/mcp.json`

```json
{
  "mcpServers": {
    "sps-manoeuvre": {
      "command": "python3",
      "args": ["-m", "sps_manoeuvre"],
      "cwd": "/absolute/path/to/sps-manoeuvre/src",
      "env": {
        "GITHUB_TOKEN": "ghp_your-token-here",
        "SLACK_WEBHOOK_URL": "https://hooks.slack.com/services/T.../B.../...",
        "IBM_CLOUD_API_KEY": "your-ibm-cloud-api-key"
      }
    }
  }
}
```

> **Linux/Windows:** also add `SLACK_USER_TOKEN` and `SLACK_COOKIE` — see [README.md#manual-token-setup-non-macos](README.md#manual-token-setup-non-macos).

## 4. Add repos to the watchlist

Edit `src/sps_manoeuvre/repos.json`:

```json
{
  "repos": [
    { "repo": "CICS/my-repo", "description": "My repo" }
  ]
}
```

## 5. Reload Bob and smoke-test

1. Bob → **Settings → MCP Servers → Reload**
2. Ask Bob: *"ping the sps pipeline bot"* → should return `pong`
3. Ask Bob: *"fetch the latest SPS announcements"*

---

## Getting credentials

### GitHub PAT
1. https://github.ibm.com/settings/tokens → Generate new token (classic)
2. Scopes: tick `repo` (full)
3. Copy the `ghp_...` value

### Slack webhook URL
1. https://api.slack.com/apps → open or create your app → Incoming Webhooks
2. Add webhook → choose your output channel
3. Copy the `https://hooks.slack.com/services/...` URL

### Slack user token (Linux/Windows manual method)
1. Open Slack in Chrome → DevTools (`F12`) → Network tab
2. Click any channel → filter for `api.slack.com` requests
3. Click a request → Headers:
   - `Authorization: Bearer xoxc-...` → `SLACK_USER_TOKEN`
   - `Cookie: d=xoxd-...` (just the `xoxd-...` part) → `SLACK_COOKIE`

### IBM Cloud API key
https://cloud.ibm.com/iam/apikeys → Create

---

For full documentation, advanced usage, and troubleshooting: **[README.md](README.md)**
