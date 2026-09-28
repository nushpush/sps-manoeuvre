# SPS Manoeuvre — Full Automation Setup & Prerequisites

> **Core principle:** The user grants *permissions*, not secrets.
> The bot authenticates using IBM Cloud Trusted Profile + workload identity — the compute environment *is* the credential.
> No API key is ever shared with, stored by, or visible to the service operator.

---

## Overview

```
User grants permissions
        │
        ├── IBM Cloud IAM Trusted Profile  →  bot reads Tekton logs (no API key)
        ├── Secrets Manager (user-owned)   →  bot fetches GitHub token + Slack tokens at runtime
        ├── GitHub App install             →  bot can read repos and raise PRs
        └── Slack webhook + bot token      →  bot can post and read Slack channels
```

The only things the user ever *gives* the service are non-secret identifiers: Secrets Manager instance ID, region, channel IDs, repo names.

---

## Phase 1 — One-time IBM Cloud admin setup

### Step 1 — Request a Functional ID for the bot
> **Who:** User + manager approval
> **When:** Once

- Request a non-personal w3 identity (e.g. `sps-manoeuvre@ibm.com`) via the IBM IAM Provisioning Tool
- Business justification: automated pipeline monitoring service
- This ID will own all IBM Cloud resources the bot uses

**What the user provides:** Filled IAM request form + manager approval  
**Is it a secret?** No

---

### Step 2 — Create a Trusted Profile in IBM Cloud IAM
> **Who:** IBM Cloud account admin
> **When:** Once

1. Go to **IBM Cloud → Manage → Access (IAM) → Trusted Profiles**
2. Create a new profile linked to the compute resource that will run the bot (Code Engine job, IKS pod, or VSI)
3. Assign policy: `Viewer` on the specific Tekton pipeline service instance only — nothing else

**No API key is created or stored anywhere.** The compute identity *is* the credential.

**What the user provides:** Admin action to grant a permission  
**Is it a secret?** No

---

### Step 3 — Point the bot at the right pipeline
> **Who:** User
> **When:** Once at deploy time

Provide these non-secret identifiers in the bot's config:

| Config value | Example | Secret? |
|---|---|---|
| IBM Cloud region | `eu-gb` | No |
| Pipeline service instance ID | From the IBM Cloud URL | No |

---

## Phase 2 — GitHub access

### Step 4 — Grant the bot read access to repos
> **Who:** GitHub org admin
> **When:** Once

**Option A — GitHub App (preferred, no PAT needed):**
1. Create a GitHub App on the org with scopes: `Contents: Read`, `Pull requests: Write`
2. Install it on the repos the bot needs to watch
3. Bot uses short-lived installation tokens — no PAT stored anywhere

**Option B — Fallback (if GitHub App not available):**
1. Generate a PAT under the functional ID
2. Store it in **your own IBM Secrets Manager instance** (you control this — the service operator never sees it)
3. Grant the bot's Trusted Profile `SecretsReader` access to that specific secret

**What the user provides:** GitHub App install (Option A) or PAT stored in their own SM (Option B)  
**Handed to service operator?** Never

---

## Phase 3 — Slack access

### Step 5 — Slack webhook for posting alerts
> **Who:** Slack workspace admin
> **When:** Once

1. Create or reuse a Slack app with an **incoming webhook** pointed at your output channel (e.g. `#sps-updates-modernization`)
2. Store the webhook URL in **your own IBM Secrets Manager** — not in any config file
3. Grant the bot's Trusted Profile `SecretsReader` access to that specific secret

**What the user provides:** Webhook URL stored in their own SM  
**Handed to service operator?** Never

---

### Step 6 — Slack bot token for reading channels
> **Who:** Slack workspace admin
> **When:** Once

**Option A — Fully automated (recommended):**
1. Register a Slack app with scopes: `channels:history`, `search:read`
2. Get workspace admin approval (one-time)
3. Store the `xoxb-` bot token in **your own IBM Secrets Manager**
4. Grant the bot's Trusted Profile `SecretsReader` access to it

**Option B — Developer Mac only (current approach):**
- Each developer runs `python3 -m sps_manoeuvre --bootstrap` once
- Token is extracted from the Slack desktop app and cached in macOS Keychain — never leaves the machine

**What the user provides:** Workspace admin approval + token stored in their own SM  
**Handed to service operator?** Never

---

## Phase 4 — Deploy the bot

### Step 7 — Deploy to IBM Cloud compute
> **Who:** Operator
> **When:** Once

Deploy to the compute resource linked to the Trusted Profile from Step 2.

Pass only **non-secret identifiers** as environment variables — no secrets in env or config files:

```bash
SM_INSTANCE_ID=<secrets-manager-instance-id>   # non-secret identifier
REGION=eu-gb
PIPELINE_CHANNEL_ID=C07LS8K2DTQ
REPOS=CICS/cics-explorer,IBM/cics-bundle-maven
```

At startup the bot:
1. Uses compute workload identity → gets short-lived IAM token (no API key ever needed)
2. Calls Secrets Manager → fetches Slack bot token, GitHub token, Slack webhook URL
3. All secrets live only in memory for the duration of the process — never on disk

**What the user provides:** Non-secret config values only  
**Any secrets?** Zero

---

### Step 8 — Add repos to the watchlist
> **Who:** User
> **When:** Ongoing

Either edit `repos.json` directly or ask Bob:
> *"add repo CICS/my-repo to the sps pipeline bot watchlist"*

Only repo names — no credentials needed.

---

## Phase 5 — Runtime (fully automated)

Once deployed, the bot:
- Polls `#cics-sps-notifications` every 5 minutes
- Fetches IBM Cloud Tekton logs for any failed runs
- Searches SPS troubleshooting channels if it's an SPS/infra issue
- Posts findings to the output channel

**User action required at runtime:** None

---

## Summary — what the user ever provides

| Step | What user does | Secret? | Handed to service operator? |
|---|---|---|---|
| Request functional ID | Fill form + manager approval | No | No |
| Create Trusted Profile | Grant IAM permission (admin action) | No | No |
| GitHub App install | Install app on org | No | No |
| GitHub PAT (fallback) | Store PAT in their own Secrets Manager | Yes, but… | Never — user controls SM |
| Slack webhook URL | Store in their own Secrets Manager | Sensitive, but… | Never — user controls SM |
| Slack bot token | Approve app + store in their own SM | Yes, but… | Never — user controls SM |
| Deploy config | SM instance ID, region, channel IDs, repos | No | Fine to share |

> **Result:** The service operator never sees any secret.
> Secrets live only in the user's own IBM Secrets Manager instance.
> The bot accesses them at runtime using workload identity — a permission granted by the user, not a secret handed to anyone.

---

## Least-privilege IAM policy for the Trusted Profile

The bot only needs to read Tekton pipeline run logs and fetch secrets it is explicitly allowed to read:

| Service | Resource | Role |
|---|---|---|
| Continuous Delivery | Specific pipeline service instance | Viewer |
| Secrets Manager | Specific SM instance | SecretsReader |

Do **not** assign Editor, Manager, or account-level roles. Always scope to the specific resource instance ID.

---

## Security review story

> *"We hold no secrets. Users grant permissions to their own resources. All credentials are fetched at runtime from the user's own Secrets Manager using IBM Cloud workload identity (Trusted Profile). No long-lived keys are stored anywhere by the service."*
