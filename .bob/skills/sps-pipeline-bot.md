---
name: sps-pipeline-bot
description: >
  Use this skill when the user wants to check for SPS/One Pipeline announcements,
  troubleshoot a pipeline build failure, apply pipeline changes to repos, raise
  a PR for a pipeline-related fix, or manage the automated monitor. Activates the
  sps-pipeline-bot MCP tools.
---

# SPS Pipeline Bot Skill

You have access to the `sps-pipeline-bot` MCP server. Use the tools below to help
the user with three distinct workflows.

---

## Workflow 1 — Process Announcements

**Trigger:** User asks to check for new SPS announcements, pipeline changes, or says
something like "what's new in One Pipeline" or "check the announcement channels".

**Steps:**

1. Call `fetch_announcements()` to get unprocessed messages from the three announcement
   channels (`#one-pipeline-announce`, `#devops-complines`, `#secure-pipelines-service`).
   - If result is empty, tell the user there are no new announcements.

2. For each message returned, **analyse it yourself** and determine:
   - Is action required, or is it purely informational?
   - What **category** is the change? Choose from:
     `image-update`, `scan-config`, `code-signing`, `detect-secrets`, `sast`, `os-scan`,
     `tekton`, `mend-migration`, `get-env-breaking-change`, `general`
   - What **file patterns** should be searched in repos?
     (e.g. `.pipeline-config*.yaml`, `GaraSign`, `.secrets.baseline`, `scripts/`)
   - What specific **change is needed**?

3. **Deduplicate before acting:** multiple messages about the same topic (e.g. several
   posts all mentioning "mend sca") should be collapsed into one action item per topic.
   Keep the most useful permalink from the group.

4. For announcements that require action, call `scan_repos_tool(file_patterns=[...])` to
   find which repos in the watchlist are affected.

5. For each affected repo, call `get_repo_files(repo="ORG/NAME", file_patterns=[...])` to
   fetch the current file contents.

6. **Read the file contents yourself** and produce a minimal diff — show the user exactly
   what lines would change and why. Present this clearly before doing anything.

7. Ask the user: *"Should I raise a PR for [repo]?"*

8. If the user confirms, call `create_pr(...)` with:
   - `branch_name`: `sps-bot/<short-description>` (e.g. `sps-bot/update-garasign-path`)
   - `pr_title`: concise title referencing the announcement
   - `pr_body`: include the announcement permalink, what changed, and why
   - `file_changes`: dict of `{path: complete_new_file_content}`

9. Optionally call `post_webhook_alert(...)` to notify the team via the existing
   notification app. If the user declines a PR, still call `post_webhook_alert` with
   `pr_url=""` so the team is notified and can act manually.

### Known announcement categories and what to do

| Keywords in message | Category | File patterns | Suggested change |
|---|---|---|---|
| `get_env cli will no longer`, `no longer support secure values`, `breaking change: \`get_env\`` | `get-env-breaking-change` | `.pipeline-config*.yaml`, `.pipeline-scan-config.yaml`, `scripts/` | Replace `get_env` for secrets with `get_secret`. Deadline: 31 Aug 2026. |
| `mend sca`, `opt-in-mend-sca`, `mend sca cli` | `mend-migration` | `.pipeline-scan-config.yaml`, `.pipeline-config*.yaml` | Add `opt-in-mend-sca: 1` and `mend-user-email` to the compliance-checks step. |
| `versioned base image`, `pipeline-base-ubi:` | `image-update` | `.pipeline-config*.yaml`, `.pipeline-scan-config.yaml` | Update pinned version tag if used; `:latest` users need no change. |
| `detect-secrets`, `secrets baseline`, `.secrets.baseline` | `detect-secrets` | `.pipeline-config*.yaml`, `.secrets.baseline` | Update detect-secrets step or baseline file as described. |
| `garasign`, `code sign`, `csso-image-sign`, `ciso-sign` | `code-signing` | `.pipeline-config*.yaml`, `GaraSign`, `sign` | Update code signing step configuration. |
| `zap v1`, `dast-zap`, `zap scan` | `tekton` | `.pipeline-config*.yaml` | Remove dast-zap v1 config; use ZAP v2. |
| `cra deprecation`, `cra is deprecated` | `mend-migration` | `.pipeline-config*.yaml`, `.pipeline-scan-config.yaml` | Migrate to Mend SCA. |
| `pipeline release:`, `release notes`, `backout plan` | informational | — | No action needed. |
| support questions, `please do not post` | informational | — | No action needed. |

---

## Workflow 2 — Troubleshooting Assistant

**Trigger:** User pastes an error message, describes a build failure, or asks why
something isn't working in their SPS/One Pipeline build.

**Steps:**

1. Call `search_troubleshoot_channels(query="<error or keyword>")` to search the five
   specialist channels:
   (`#scs_code-signing`, `#scs-opensource-scan`, `#scs-sast`,
    `#cd-tekton-users-shared`, `#ciso-security-scanning-pipeline`)

2. You will receive matching threads including their replies. **Read them yourself** and:
   - Identify threads where the problem matches the user's issue
   - Find the reply that contains the accepted/working solution
   - Synthesise a clear, step-by-step answer

3. Present the answer to the user inline with:
   - The problem as understood
   - Root cause (if the thread explains it)
   - Step-by-step solution
   - Link to the source thread (`permalink`)
   - Confidence level based on how clearly the thread resolved it

4. If the user wants to apply the fix to a repo, continue into Workflow 1 steps 5–9.

---

## Workflow 3 — Automated Pipeline Failure Monitor

**Trigger:** User asks about pipeline failures, wants to know if the bot is watching
for failures, or asks about the `--monitor` mode.

The bot has two automated runner modes (invoked via `python3 -m sps_pipeline_bot`):

| Flag | What it does |
|---|---|
| `--run` | One-shot: fetch new announcements → classify → scan repos → post webhook alerts. Safe to schedule via cron or launchd. |
| `--monitor` | Continuous: polls `#cics-sps-notifications` every 5 minutes for pipeline failure notifications → fetches IBM Cloud Tekton logs → extracts `BUILD FAILURE` context → searches SPS channels if it's an SPS/infra issue → posts findings to the output channel. |

**How `--monitor` determines root cause:**
- It looks for failure Slack messages (by attachment colour `#E01E5A` or text containing
  "has failed"/"pipeline failed").
- If `IBM_CLOUD_API_KEY` is set and a run URL is present, it fetches Tekton step logs
  and checks whether the failure is a `BUILD FAILURE` (i.e. the user's own code/build
  broke) vs an SPS/infra issue (e.g. scan step timeout, signing failure).
- **Build failure** → posts the error snippet directly; does NOT search SPS channels.
- **SPS/infra issue** → searches troubleshooting channels and surfaces relevant threads.

**The `daily-run.sh` script** (`scripts/daily-run.sh`) wraps `--run` for launchd/cron
scheduling and writes output to `.bob/daily-run.log`.

---

## General Guidelines

- **Never call `create_pr` without explicit user confirmation** — always show the diff first.
- When calling `scan_repos_tool` or `get_repo_files`, use specific patterns from the
  announcement (e.g. for a GaraSign path change, use `GaraSign` or `.pipeline-config`).
- **Deduplicate announcements** before acting — collapse multiple messages about the same
  topic into one action item per topic, per repo.
- If `fetch_announcements` returns many messages, group them by category and summarise
  before asking the user which ones to action.
- If no matching threads are found for a troubleshooting query, suggest broadening the
  search terms and try again with `search_troubleshoot_channels`.
- Use `add_repo` / `remove_repo` / `list_repos` to manage the watchlist whenever the
  user wants to add or remove a repository.
