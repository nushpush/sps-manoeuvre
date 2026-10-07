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

## Getting credentials

### GitHub PAT
1. https://github.ibm.com/settings/tokens → Generate new token (classic)
2. Scopes: tick `repo` (full)
3. Copy the `ghp_...` value

### Slack webhook URL
1. https://api.slack.com/apps → open or create your app → Incoming Webhooks
2. Add webhook → choose your output channel
3. Copy the `https://hooks.slack.com/services/...` URL

### Slack user token & cookie

These two values let SPS Manoeuvre read Slack channels on your behalf.

| What you copy | Looks like | Paste into |
|---|---|---|
| `Authorization` request header value | `xoxc-12345-67890-...` | **`SLACK_USER_TOKEN`** |
| `d=` portion of the `Cookie` request header | `xoxd-...` | **`SLACK_COOKIE`** |

**Step-by-step:**

1. Open **https://app.slack.com** in Chrome (not the desktop app).
2. Log in to your IBM workspace if prompted.
3. Open DevTools: **F12** (Windows/Linux) or **⌘ Option I** (macOS).
4. Go to the **Network** tab. Make sure recording is on (red circle).
5. Click any channel in the Slack sidebar to trigger a request.
6. In the Network tab filter box, type **`api.slack.com`** to narrow results.
7. Click any request in the list (e.g. one named `conversations.history`).
8. In the right panel, click **Headers** → scroll to **Request Headers**.
9. Find and copy:
   - **`Authorization`** header → value starts with `Bearer xoxc-` → copy everything **after** `Bearer ` (i.e. `xoxc-...`) → this is your **`SLACK_USER_TOKEN`**
   - **`Cookie`** header → find the `d=xoxd-...` segment → copy everything **after** `d=` (i.e. `xoxd-...`) → this is your **`SLACK_COOKIE`**
10. Run `sps-manoeuvre --setup` and paste each value when prompted.

> **Note:** these tokens expire when you log out of Slack. Re-run `sps-manoeuvre --setup` to refresh them.

### IBM Cloud API key
https://cloud.ibm.com/iam/apikeys → Create

---

For full documentation, advanced usage, and troubleshooting: **[README.md](README.md)**
