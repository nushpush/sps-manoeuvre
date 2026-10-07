# SPS Manoeuvre — Quick-Start Setup

Full documentation is in [README.md](README.md). This page is a condensed checklist for getting up and running quickly.

---

## Checklist

- [ ] Python 3.10+ installed (`python3 --version`)
- [ ] Bob installed (https://bob.ibm.com)
- [ ] GitHub PAT for `github.ibm.com` with `repo` scope
- [ ] Slack incoming webhook URL for your output channel
- [ ] Slack user token (`xoxc-...`) and cookie (`xoxd-...`) — see [Getting credentials](#getting-credentials) below
- [ ] IBM Cloud API key (for pipeline failure log fetching — optional)

---

## 1. Install

```bash
git clone https://github.ibm.com/anushka-p/sps-manoeuvre.git
cd sps-manoeuvre
pip3 install -e .
```

## 2. Run the setup wizard

```bash
sps-manoeuvre --setup
```

The wizard will prompt for the following values:

| Prompt | Where to get it |
|---|---|
| **GitHub Personal Access Token** | [github.ibm.com/settings/tokens](https://github.ibm.com/settings/tokens) → Generate new token (classic) → scope: `repo` |
| **Slack Incoming Webhook URL** | [api.slack.com/apps](https://api.slack.com/apps) → your app → Incoming Webhooks → Add New Webhook → copy the `https://hooks.slack.com/services/...` URL |
| **Slack User Token (`xoxc-...`)** | Open [app.slack.com](https://app.slack.com) in Chrome → DevTools (`F12`) → Network tab → click any channel → filter `api.slack.com` → click any request → Request Headers → `Authorization` → copy the value **after** `Bearer ` |
| **Slack Cookie (`xoxd-...`)** | Same request as above → `Cookie` header → find `d=xoxd-...` → copy the value **after** `d=` |
| **IBM Cloud API Key** *(optional)* | [cloud.ibm.com/iam/apikeys](https://cloud.ibm.com/iam/apikeys) → Create → copy the key |

## 3. Add repos to the watchlist

Edit `src/sps_manoeuvre/repos.json`:

```json
{
  "repos": [
    { "repo": "CICS/my-repo", "description": "My repo" }
  ]
}
```

## 4. Reload Bob and smoke-test

1. Bob → **Settings → MCP Servers → Reload**
2. Ask Bob: *"ping the sps output channel"* → should return `pong`
3. Ask Bob: *"fetch the latest SPS announcements"*


---

For full documentation, advanced usage, and troubleshooting: **[README.md](README.md)**
