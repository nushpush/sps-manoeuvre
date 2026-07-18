# SPS Pipeline Bot — Socket Mode Setup

Socket Mode lets the bot **receive** messages from Slack (button clicks, slash commands,
mentions) over a persistent WebSocket — no public URL, no firewall issues.

Once set up, you can click a button in an alert message to raise a PR, or type
`/sps-troubleshoot GaraSign loader error` directly in Slack.

---

## What you need

- Access to **https://api.slack.com/apps** (IBM Slack workspace admin, or someone
  who can submit an app for approval)
- The bot process running somewhere (your laptop, a VM, or later via SPS container)

---

## Step 1 — Create the Slack app

1. Go to **https://api.slack.com/apps**
2. Click **Create New App → From an app manifest**
3. Select your **IBM Z Slack workspace**
4. Paste the manifest below (YAML tab) and click **Next → Create**

```yaml
display_information:
  name: SPS Pipeline Bot
  description: Monitors SPS pipeline announcements and helps teams stay up to date
  background_color: "#1f2328"

features:
  bot_user:
    display_name: sps-bot
    always_online: true
  slash_commands:
    - command: /sps-troubleshoot
      description: Search SPS troubleshooting channels for a fix
      usage_hint: "[error message or keyword]"
      should_escape: false
    - command: /sps-check
      description: Fetch latest SPS announcements and check your repos
      should_escape: false

oauth_config:
  scopes:
    bot:
      - channels:history       # read messages from public channels
      - channels:read          # resolve channel info and permalinks
      - chat:write             # post messages and reply in threads
      - commands               # handle slash commands
      - users:read             # resolve usernames in announcements

settings:
  socket_mode_enabled: true
  event_subscriptions:
    bot_events:
      - app_mention            # respond when someone @mentions the bot
  interactivity:
    is_enabled: true           # enables button clicks in messages
  org_deploy_enabled: false
  token_rotation_enabled: false
```

5. Click **Install to Workspace** → **Allow**
   (This is the one step that may need workspace admin approval on IBM Slack)

---

## Step 2 — Get your tokens

After installation, you need **two** tokens:

### Bot token (`xoxb-`)
1. In your app settings → **OAuth & Permissions**
2. Copy **Bot User OAuth Token** — starts with `xoxb-`

### App-level token (`xapp-`)  
Required specifically for Socket Mode.

1. In your app settings → **Basic Information** → scroll to **App-Level Tokens**
2. Click **Generate Token and Scopes**
3. Name: `socket-mode`
4. Add scope: `connections:write`
5. Click **Generate** → copy the token starting with `xapp-`

---

## Step 3 — Add tokens to mcp.json

Open `.bob/mcp.json` and add the two new tokens:

```json
{
  "mcpServers": {
    "sps-pipeline-bot": {
      "command": "python3",
      "args": ["-m", "sps_pipeline_bot"],
      "cwd": "/path/to/sps-pipeline-bot/src",
      "env": {
        "GITHUB_TOKEN": "ghp_your-token-here",
        "SLACK_WEBHOOK_URL": "https://hooks.slack.com/services/...",
        "SLACK_BOT_TOKEN": "xoxb-your-bot-token-here",
        "SLACK_APP_TOKEN": "xapp-your-app-token-here"
      }
    }
  }
}
```

> `SLACK_USER_TOKEN` and `SLACK_COOKIE` are still auto-refreshed from the desktop app
> for **reading** announcement channels. The new `SLACK_BOT_TOKEN` is used for
> **writing** (posting, replying) and receiving interactions.

---

## Step 4 — Install the Slack Bolt library

Socket Mode uses the **Slack Bolt for Python** SDK:

```bash
pip3 install slack-bolt
```

Or it will be installed automatically when you run `pip3 install -e ./src` after
we add it to `pyproject.toml`.

---

## Step 5 — Run the Socket Mode bot

```bash
cd sps-pipeline-bot/src
python3 -m sps_pipeline_bot.bot
```

You should see:
```
⚡️ Bolt app is running in Socket Mode!
```

The bot is now connected to Slack and listening. Keep this process running.

---

## What the bot will respond to

### Button clicks in alert messages

When the bot posts an alert like:

```
🔧 SPS Pipeline Change Required
Repository: CICS/my-repo
Change: Migrate to Mend SCA CLI scan

[Raise PR]  [View Announcement]
```

Clicking **Raise PR** → bot raises the PR on GitHub and replies in-thread:

```
✅ PR raised: https://github.ibm.com/CICS/my-repo/pull/42
```

### Slash command: `/sps-troubleshoot`

In any Slack channel, type:

```
/sps-troubleshoot GaraSign loader path not found
```

Bot searches `#scs_code-signing`, `#scs-sast`, and the other troubleshooting channels
and replies with the best matching threads and their solutions.

### Slash command: `/sps-check`

```
/sps-check
```

Bot fetches the latest unprocessed announcements, scans your watched repos, and posts
a summary of what needs updating.

### App mention: `@sps-bot`

```
@sps-bot what repos need updating for the Mend announcement?
```

Bot responds in-thread.

---

## What changes in the architecture

```
Before Socket Mode:
  Bob chat ──▶ MCP tools ──▶ Slack API (read via xoxc-)
                          └──▶ Webhook URL (write, one-way)

After Socket Mode:
  Bob chat ──▶ MCP tools ──▶ Slack API (read via xoxc-)
                          └──▶ Bot token (write, replies, threads)
                                    ↕ WebSocket (always-on)
  Slack ──────────────────▶ bot.py process
                                ├── button clicks → GitHub PR → thread reply
                                ├── /sps-troubleshoot → search → thread reply
                                └── /sps-check → fetch + scan → post alerts
```

The `bot.py` and the MCP server share all the same underlying logic
(`github_client.py`, `slack_client.py`, etc.) — no duplication.

---

## Invite the bot to channels

After installation, invite `@sps-bot` to the channels where you want it to respond:

```
/invite @sps-bot
```

Required channels:
- `#sps-updates-modernization` — where alerts are posted (bot needs to write here)
- Any channel where you want to use `/sps-troubleshoot` or `/sps-check`

The announcement channels (`#one-pipeline-announce` etc.) are read via your personal
token — the bot does **not** need to be invited there.

---

## Running continuously (until SPS container)

For now, run the bot in a persistent terminal session:

```bash
# In a dedicated terminal window or tmux pane
cd sps-pipeline-bot/src
SLACK_BOT_TOKEN=xoxb-... SLACK_APP_TOKEN=xapp-... GITHUB_TOKEN=ghp_... \
  python3 -m sps_pipeline_bot.bot
```

Or use `nohup` to keep it running after you close the terminal:

```bash
nohup python3 -m sps_pipeline_bot.bot > ~/sps-bot.log 2>&1 &
echo "Bot PID: $!"
```

Stop it with: `kill <PID>`

Later, this becomes a container image deployed via SPS — the same `python3 -m sps_pipeline_bot.bot`
command, with tokens injected as SPS secrets.

---

## Next steps after admin approval

Once the app is installed:

1. Run `pip3 install slack-bolt`
2. Add `SLACK_BOT_TOKEN` and `SLACK_APP_TOKEN` to `mcp.json`
3. Run `python3 -m sps_pipeline_bot.bot`
4. Invite `@sps-bot` to `#sps-updates-modernization`
5. Post a test alert and click the **Raise PR** button

That's it. I'll implement `bot.py` once you have the tokens.
