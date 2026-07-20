---
name: sps-pipeline-bot
description: >
  Use this skill when the user wants to check for SPS/One Pipeline announcements,
  troubleshoot a pipeline build failure, apply pipeline changes to repos, or raise
  a PR for a pipeline-related fix. Activates the sps-pipeline-bot MCP tools.
---

# SPS Pipeline Bot Skill

You have access to the `sps-pipeline-bot` MCP server. Use the tools below to help
the user with two distinct workflows.

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
     `image-update`, `scan-config`, `code-signing`, `detect-secrets`, `sast`, `os-scan`, `tekton`, `general`
   - What **file patterns** should be searched in repos?
     (e.g. `.pipeline-config*.yaml`, `GaraSign`, `.secrets.baseline`, `Dockerfile`)
   - What specific **change is needed**?

3. For announcements that require action, call `scan_repos_tool(file_patterns=[...])` to
   find which repos in the watchlist are affected.

4. For each affected repo, call `get_repo_files(repo="ORG/NAME", file_patterns=[...])` to
   fetch the current file contents.

5. **Read the file contents yourself** and produce a minimal diff — show the user exactly
   what lines would change and why. Present this clearly before doing anything.

6. Ask the user: *"Should I raise a PR for [repo]?"*

7. If the user confirms, call `create_pr(...)` with:
   - `branch_name`: `sps-bot/<short-description>` (e.g. `sps-bot/update-garasign-path`)
   - `pr_title`: concise title referencing the announcement
   - `pr_body`: include the announcement permalink, what changed, and why
   - `file_changes`: dict of `{path: complete_new_file_content}`

8. Optionally call `post_webhook_alert(...)` to notify the team via the existing
   notification app.

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

4. If the user wants to apply the fix to a repo, continue into Workflow 1 steps 4–8.

---

## General Guidelines

- **Never call `create_pr` without explicit user confirmation** — always show the diff first.
- When calling `scan_repos_tool` or `get_repo_files`, use specific patterns from the
  announcement (e.g. for a GaraSign path change, use `GaraSign` or `.pipeline-config`).
- If `fetch_announcements` returns many messages, group them by category and summarise
  before asking the user which ones to action.
- If no matching threads are found for a troubleshooting query, suggest broadening the
  search terms and try again with `search_troubleshoot_channels`.
