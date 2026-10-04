---
name: sps-manoeuvre
description: Use when the user wants to troubleshoot IBM Cloud SPS (Secure Pipeline Service) pipeline failures, understand the impact of SPS announcements on their repositories, create or review SPS pipeline config files (.pipeline-config-ci.yaml, .pipeline-config-pr.yaml, .pipeline-scan-config.yaml), migrate a repository from Jenkins or Travis CI to SPS, manage an automated pipeline monitor, or understand what any /opt/commons/ script does inside an SPS pipeline. Source repository at github.ibm.com/anushka-p/sps-manoeuvre.
---

# SPS Manoeuvre

This skill guides you through IBM Cloud Secure Pipeline Service (SPS) operations: announcement impact analysis, pipeline failure diagnosis, pipeline config authoring, Jenkins migration, Travis CI migration, and full understanding of the `/opt/commons/` compliance scripts that power every SPS pipeline.

**Source repository:** [github.ibm.com/anushka-p/sps-manoeuvre](https://github.ibm.com/anushka-p/sps-manoeuvre)
**Install guide:** [`README.md`](./README.md)
**Commons internals reference:** [`references/commons-internals.md`](./references/commons-internals.md)

---

## When This Skill Activates

- "My SPS pipeline failed — what's wrong?"
- "There's a new SPS announcement — which of my repos are affected?"
- "Help me write a `.pipeline-config-ci.yaml` for my repo."
- "I need to migrate this Jenkins / Travis CI pipeline to SPS."
- "Why is my Tekton step failing with `get_env: command not found`?"
- "Check the SPS announcement channels for me."
- "Is the bot watching my pipelines for failures?"
- "What does `/opt/commons/ciso/sign_artifacts.sh` do?"
- "What `get_env` properties does the compliance-checks step need?"
- "Why is my Mend scan not running?"
- "What secrets does the signing step need?"

---

## Step 1 — Identify the Task

Ask the user (using `ask_followup_question`) which workflow applies:

1. **Announcement impact** — a new SPS Slack announcement has been posted; scan repos and raise PRs.
2. **Failure diagnosis** — a Tekton pipeline run has failed and they need the root cause.
3. **Pipeline config authoring** — write or review an SPS pipeline YAML from scratch.
4. **Jenkins migration** — migrate from a `Jenkinsfile` to SPS.
5. **Travis CI migration** — migrate from `.travis.yml` to SPS.
6. **Commons internals** — understand what an `/opt/commons/` script does, what properties it needs, or why a scan/sign step isn't working.

---

## Workflow A — Announcement Impact Analysis

This is the primary automated workflow. The `sps-manoeuvre` MCP tools power it when available.

### A1. Capture the announcement

Ask the user to paste the announcement text **or** call `fetch_announcements()` to pull unprocessed messages from the monitored channels:
- `#one-pipeline-announce`
- `#devops-compliance`
- `#secure-pipelines-service`
- `#ciso-security-scanning-pipeline`

If the result is empty, tell the user there are no new announcements.

### A2. Classify the announcement

For each message, determine:
- **Is action required**, or is it purely informational (e.g. release notes, support reminders)?
- **What category** does it fall into?
- **What file patterns** need to be searched across repos?
- **What specific change** is needed?

Use this table of known categories:

| Keywords in message | Category | File patterns to search | What to change |
|---|---|---|---|
| `get_env cli will no longer`, `no longer support secure values`, `breaking change: get_env` | `get-env-breaking-change` | `.pipeline-config*.yaml`, `.pipeline-scan-config.yaml`, `scripts/` | Replace `get_env <key>` for secrets with `get_secret <key>`. Deadline: 31 Aug 2026. |
| `mend sca`, `opt-in-mend-sca`, `mend sca cli`, `cra deprecation`, `cra is deprecated` | `mend-migration` | `.pipeline-scan-config.yaml`, `.pipeline-config*.yaml` | Add `opt-in-mend-sca: 1` and `mend-user-email` to the `compliance-checks` step; remove CRA config. |
| `versioned base image`, `pipeline-base-ubi:` followed by a version tag | `image-update` | `.pipeline-config*.yaml`, `.pipeline-scan-config.yaml` | Update pinned version tag if used; repos already on `:latest` need no change. |
| `detect-secrets`, `secrets baseline`, `.secrets.baseline` | `detect-secrets` | `.pipeline-config*.yaml`, `.secrets.baseline` | Update the detect-secrets step or regenerate the baseline file as described in the announcement. |
| `garasign`, `code sign`, `csso-image-sign`, `ciso-sign`, `sign_artifacts` | `code-signing` | `.pipeline-config*.yaml`, `GaraSign`, `sign` | Update code signing step or GaraSign path configuration. |
| `zap v1`, `dast-zap`, `zap scan` | `tekton` | `.pipeline-config*.yaml` | Remove dast-zap v1 config; migrate to ZAP v2. |
| `pipeline release:`, `release notes`, `backout plan`, `please do not post` | informational | — | No action needed — summarise and inform the user. |

**Deduplication:** multiple Slack messages about the same topic (e.g. several posts all mentioning "mend sca") must be collapsed into **one action item per topic**. Keep the most informative permalink from the group.

### A3. Scan repositories

For announcements that require action, call `scan_repos_tool(file_patterns=[...])` to identify which repos in the watchlist are affected.

For each affected repo, call `get_repo_files(repo="ORG/NAME", file_patterns=[...])` to fetch the current file contents.

### A4. Produce a diff

**Read the file contents yourself** and produce a minimal diff — show the user exactly what lines would change and why. Present clearly before doing anything.

### A5. Raise PRs (with confirmation)

Ask the user: *"Should I raise a PR for [repo]?"*

If confirmed, call `create_pr(...)` with:
- `branch_name`: `sps-bot/<short-description>` (e.g. `sps-bot/update-get-secret`)
- `pr_title`: concise title referencing the announcement
- `pr_body`: include the Slack announcement permalink, what changed, and why
- `file_changes`: dict of `{path: complete_new_file_content}`

Optionally call `post_webhook_alert(...)` to notify the team. If the user declines a PR, still post the alert so the team is informed and can act manually.

**Safety rule:** Never call `create_pr` without explicit user confirmation. Always show the diff first.

---

## Workflow B — Failure Diagnosis

### B1. Gather context

Ask for:
- The failing pipeline run URL or Tekton namespace.
- The error message or log snippet (if available).
- The repository name and branch.

If the `search_troubleshoot_channels` MCP tool is available, call it with the error keyword:

```
search_troubleshoot_channels(query="<error or keyword>")
```

This searches five specialist channels: `#scs_code-signing`, `#scs-opensource-scan`, `#scs-sast`, `#cd-tekton-users-shared`, `#ciso-security-scanning-pipeline`.

Read the matching threads and find where the problem was resolved.

### B2. Inspect pipeline config files

Use `grep` or `read_file` to examine:
- `.pipeline-config-ci.yaml`
- `.pipeline-config-pr.yaml`
- `scripts/setup.sh`
- `scripts/build.sh`

Look for:

| Symptom | Likely cause | Fix |
|---|---|---|
| `get_env: command not found` | Wrong base image — `get_env` is a helper only present in `pipeline-base-ubi` and `csso-image-sign` | Change image to `icr.io/continuous-delivery/pipeline/pipeline-base-ubi:latest` |
| Artifactory 401 | Secrets not fetched or wrong key name | Verify `get_env` calls in `setup.sh`; check secret key names in Secrets Manager |
| `No such file or directory: build.sh` | Script not executable or wrong path | Add `chmod +x scripts/*.sh` to setup step |
| `unknown task` / `unknown stage` | Wrong key name in YAML | v1 uses top-level stage names; v2 uses `tasks:` key — check which version the toolchain expects |
| Build passes but no artifact published | Branch condition or publish logic missing | Verify branch with `get_env branch`; check pipeline_namespace logic |
| `load_repo app-repo path` fails | Not running in SPS context | This helper is only available inside SPS Tekton steps |
| Signing step fails | Wrong image or missing GaraSign config | Signing requires `csso-image-sign:latest` image + `/opt/commons/ciso/sign_artifacts.sh` |
| Mend scan not running | Missing `opt-in-mend-sca` flag | Add `opt-in-mend-sca: 1` to `compliance-checks` step env |

### B3. Why `pipeline-base-ubi` instead of `csso-image-sign` for most steps

This is a common source of confusion. The `csso-image-sign` image is a **signing-specific** image — it bundles GaraSign and CISO tooling but does NOT include the full SPS helper functions that `pipeline-base-ubi` has. Teams sometimes start with `csso-image-sign` everywhere (because the toolchain template uses it) and then find that build steps fail because standard helpers are missing.

**Rule:** Use `csso-image-sign:latest` **only** for the step that actually performs artifact signing (typically the `deploy` step or a dedicated `sign-artifact` step). All other steps — setup, build, test, detect-secrets, compliance-checks — should use `pipeline-base-ubi:latest`.

### B4. Report findings

Present a concise root cause analysis with:
- What failed and why.
- The specific file and line to fix.
- The corrected snippet as a diff.
- A link to the Slack thread that resolved it (if found via `search_troubleshoot_channels`).

**Safety rule:** Show the diff and wait for explicit confirmation before any `git` operation.

---

## Workflow C — Pipeline Config Authoring

### C1. Gather requirements

Ask:
- CI pipeline, PR pipeline, or scan-only pipeline?
- Build tool: Maven (`./mvnw`), Gradle, npm, or other?
- Does the build require **artifact signing**? (Signing requires `csso-image-sign` — ask explicitly, do not assume.)
- Which branches trigger CI builds?
- Does it publish to Artifactory?
- Is there an acceptance test or upload step?

### C2. YAML version

SPS supports two config versions. Ask which the team's toolchain uses, or check an existing config:

| Version | `tasks:` key | Stage key style | Notes |
|---|---|---|---|
| `version: '1'` | No — uses top-level stage names directly | `setup:`, `test:`, `deploy:` | Older toolchains |
| `version: '2'` | Yes — all stages nested under `tasks:` | `code-build:`, `deploy-checks:`, etc. | Current standard; use this for new migrations |

### C3. Image selection

| Step purpose | Image |
|---|---|
| Setup, build, test, scans | `icr.io/continuous-delivery/pipeline/pipeline-base-ubi:latest` |
| Artifact signing step only | `icr.io/continuous-delivery/pipeline/csso-image-sign:latest` |

Never use version-pinned tags (e.g. `:3.61`) — always `:latest`.

### C4. Naming conventions

- Use `goals` (not `tasks`) for Gradle variable names — ZSW CICS standard.
- Use `get_env branch` (not `$GIT_BRANCH`) to detect the current branch.
- Use `get_env pipeline_namespace` to detect CI vs PR context.
- Use `$STAGE_WORKSPACE` instead of `$WORKSPACE` for file I/O inside steps — disk access is ~3× faster.
- Use `load_repo app-repo path` to get the checked-out repo path inside a Tekton step.

### C5. Standard v2 CI structure

```yaml
version: '2'
tasks:
  code-checks:
    steps:
      - name: detect-secrets
        image: icr.io/continuous-delivery/pipeline/pipeline-base-ubi:latest
        abort_on_failure: true
        script: |
          #!/bin/sh
          /opt/commons/detect-secrets/run_scan.sh

      - name: compliance-checks
        image: icr.io/continuous-delivery/pipeline/pipeline-base-ubi:latest
        abort_on_failure: true
        script: |
          #!/usr/bin/env bash
          /opt/commons/compliance-checks/run.sh

  code-build:
    steps:
      - name: build-artifact
        image: icr.io/continuous-delivery/pipeline/pipeline-base-ubi:latest
        script: |
          #!/usr/bin/env bash
          cd "$WORKSPACE/$(load_repo app-repo path)"
          source scripts/setup.sh
          source scripts/build.sh deploy

  deploy-checks:
    steps:
      - name: deploy
        image: icr.io/continuous-delivery/toolchains/devsecops/csso-image-sign:latest
        script: |
          #!/usr/bin/env bash
          cd "$WORKSPACE/$(load_repo app-repo path)"
          source scripts/setup.sh
          /opt/commons/ciso/sign_artifacts.sh
          source scripts/sign_file.sh
```

### C6. Review with the user

Present the generated config and wait for confirmation before saving with `write_file`.

---

## Workflow D — Jenkins to SPS Migration

### D1. Read the existing Jenkinsfile

Use `read_file` or `grep` to locate and read the `Jenkinsfile`.

### D2. Map Jenkins concepts to SPS

| Jenkins | SPS equivalent |
|---|---|
| `sh` step | `script` block in pipeline YAML |
| `withCredentials` / credential binding | `get_env <key>` in `scripts/setup.sh` |
| `publishArtifacts` / Artifactory plugin | `artifactoryPublish` in Gradle `goals`, or `mvn deploy` with `settings.xml` |
| Multibranch pipeline (branch conditions) | Separate `.pipeline-config-ci.yaml` and `.pipeline-config-pr.yaml` files |
| `GIT_BRANCH` env var | `get_env branch` |
| Jenkins secrets manager / credential store | IBM Secrets Manager via `get_env <secret-key>` |
| Build-only stage (no publish) | PR pipeline — `verify` goal / no deploy step |
| Build + publish stage (main branch) | CI pipeline — `deploy` goal / deploy step |

### D3. Map secrets

For every credential in the Jenkinsfile, document:
- The Jenkins credential ID
- The IBM Secrets Manager key name it maps to
- The `get_env` call in `scripts/setup.sh`

### D4. Create the five standard SPS files

Use `write_file` to generate:
- `.pipeline-config-ci.yaml` — for protected branches (build + publish + sign if needed)
- `.pipeline-config-pr.yaml` — for PR validation (build + test only, no publish)
- `.pipeline-scan-config.yaml` — security and compliance scanning (detect-secrets, static-scan, compliance-checks)
- `scripts/setup.sh` — fetches secrets via `get_env`; configures Java, Maven, Gradle, etc.
- `scripts/build.sh` — runs the build; accepts a goal/phase argument so CI and PR can call it with different args

### D5. Validate

Advise the user to run `sps-manoeuvre --doctor` and verify:
- All `get_env` calls reference valid secret keys
- Scripts are executable (`chmod +x scripts/*.sh`)
- Image selection matches signing requirements

---

## Workflow E — Travis CI to SPS Migration

This is the most common migration path for CICS Java/Maven repositories.

### E1. Read the existing `.travis.yml`

Use `read_file` to examine the Travis config. Key things to extract:
- **Language and runtime** (`language: java`, `jdk:`)
- **Branch conditions** (the `if [[ -n "$TRAVIS_TAG" || ... ]]` pattern)
- **Build commands** (`mvn`, `gradle`, etc.)
- **Secret fetching** (`.travis/secretsmanagercli.sh`, `.travis/get_artifactory_creds.sh`, or encrypted env vars)
- **Signing** (Docker-based or direct — look for `docker run`, `sign_file.sh`, `SIGNING_CERTIF_SECRET_ID`)
- **Artifact publish** (`deploy`, `artifactoryPublish`, `mvn deploy`)

### E2. Understand what `.travis/secretsmanagercli.sh` was doing

Travis repos commonly have a custom `secretsmanagercli.sh` that:
1. Accepts an `API_KEY` and `SECRET_ID` as arguments
2. POSTs to IAM to get a bearer token
3. GETs the secret from IBM Secrets Manager
4. Returns JSON piped through `jq`

**In SPS this entire script is replaced by a single `get_env` call.** SPS injects secrets from the linked Secrets Manager instance automatically. The migration is:

```bash
# Travis (.travis/get_artifactory_creds.sh)
export ARTIFACTORY_USER=$(.travis/secretsmanagercli.sh $API_KEY $SECRET_ID | jq -r ".user")
export ARTIFACTORY_TOKEN=$(.travis/secretsmanagercli.sh $API_KEY $SECRET_ID | jq -r ".token")

# SPS (scripts/setup.sh)
export ARTIFACTORY_USER=$(get_env artif_user_value)
export ARTIFACTORY_TOKEN=$(get_env artif_token_value)
```

The secret key names (`artif_user_value`, `artif_token_value`) must match what is configured in the SPS toolchain's linked Secrets Manager instance.

### E3. Map Travis concepts to SPS

| Travis CI | SPS equivalent |
|---|---|
| `before_install: source .travis/get_artifactory_creds.sh` | `source scripts/setup.sh` at the start of any step that needs credentials |
| `if [[ "$TRAVIS_PULL_REQUEST" = "false" ]]; then mvn deploy` | CI pipeline (`deploy-checks` step) |
| `else mvn verify` | PR pipeline (`pr-code-build` step with `verify` goal) |
| `$TRAVIS_BRANCH` / `$TRAVIS_TAG` | `get_env branch` / `get_env git-tag` |
| `.travis/secretsmanagercli.sh` | `get_env <key>` — delete the script entirely |
| `docker run ... sign_file.sh` (Docker-based signing) | `csso-image-sign:latest` image + `/opt/commons/ciso/sign_artifacts.sh` + `source scripts/sign_file.sh` |
| `mvn --settings travis-settings.xml` | `./mvnw --settings settings.xml` (Maven wrapper; rename settings file) |
| `cache: directories: ["$HOME/.m2"]` | Not needed — SPS handles caching via `$STAGE_WORKSPACE` |
| `services: [docker]` | `include: [dind]` in the task, plus `include: [docker-socket]` on steps that need Docker |

### E4. Understand the signing migration

Travis signing typically ran Maven inside a Docker container with signing credentials injected as env vars. SPS provides a dedicated signing image and CISO commons scripts:

**Travis pattern:**
```bash
docker run --rm -it -v $(pwd):/workspace \
  -e IBM_SM_API_KEY="$API_KEY" \
  -e SIGNING_CERTIF_SECRET_ID="<secret-id>" \
  $DOCKER_REGISTRY/$IMAGE_NAME \
  bash -c "cd /workspace && bash .travis/sign_file.sh"
```

**SPS equivalent** (in `deploy-checks` → `deploy` step):
```yaml
- name: deploy
  image: icr.io/continuous-delivery/toolchains/devsecops/csso-image-sign:latest
  script: |
    #!/usr/bin/env bash
    cd "$WORKSPACE/$(load_repo app-repo path)"
    source scripts/setup.sh
    source scripts/build.sh deploy
    /opt/commons/ciso/sign_artifacts.sh   # sets up GaraSign environment
    source scripts/sign_file.sh           # your existing signing script — keep it
```

The key insight: **`sign_file.sh` itself usually does not need to change** — it was already written to sign artifacts. The only thing that changes is how the signing environment is set up (GaraSign via `/opt/commons/ciso/sign_artifacts.sh` instead of Docker with injected secrets).

### E5. Understand why `csso-image-sign` is used — and only for signing

`csso-image-sign` bundles GaraSign and CISO signing tooling. It does **not** contain `get_env`, standard build tools, or most SPS helpers. Do not use it for setup, build, or scan steps — only for the step that calls `/opt/commons/ciso/sign_artifacts.sh` and runs `sign_file.sh`.

### E6. `$STAGE_WORKSPACE` vs `$WORKSPACE`

In SPS Tekton steps, `$WORKSPACE` is a network-mounted PVC. `$STAGE_WORKSPACE` is a local disk within the same stage — approximately **3× faster** for file I/O. The pattern in `setup.sh` is:

```bash
mkdir -p $STAGE_WORKSPACE/my-repo
cp -a $WORKSPACE/$APP_REPO_FOLDER/. $STAGE_WORKSPACE/my-repo/
```

Then `build.sh` runs from `$STAGE_WORKSPACE/my-repo`. This matters for Maven/Gradle builds that do heavy file I/O.

### E7. Create the five SPS files

Generate (using `write_file`):

**`scripts/setup.sh`** — fetch secrets, install Java/runtime, copy repo to `$STAGE_WORKSPACE`:
```bash
#!/usr/bin/env bash
set -e
export ARTIFACTORY_USER=$(get_env artif_user_value)
export ARTIFACTORY_TOKEN=$(get_env artif_token_value)

# Install Java (example: IBM Semeru 17)
curl -sSL -o /tmp/jdk.tar.gz "<semeru-download-url>"
mkdir -p /opt/java/openjdk17
tar zxf /tmp/jdk.tar.gz --strip-components=1 -C /opt/java/openjdk17
export JAVA_HOME=/opt/java/openjdk17
export PATH=$PATH:$JAVA_HOME/bin

# Copy to fast local disk
mkdir -p $STAGE_WORKSPACE/$APP_REPO_FOLDER
cp -a $WORKSPACE/$APP_REPO_FOLDER/. $STAGE_WORKSPACE/$APP_REPO_FOLDER/
```

**`scripts/build.sh`** — accepts a Maven goal (`deploy`, `verify`, etc.):
```bash
#!/usr/bin/env bash
if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <maven-goal>"
  exit 2
fi
cd $STAGE_WORKSPACE/$APP_REPO_FOLDER
./mvnw -B -U --settings settings.xml $1
```

**`.pipeline-config-ci.yaml`** — CI (main/protected branch): build + deploy + sign  
**`.pipeline-config-pr.yaml`** — PR validation: build + verify only, no signing, no publish  
**`.pipeline-scan-config.yaml`** — Scan only: detect-secrets, static-scan, compliance-checks

### E8. Files to delete

Remove from the repository:
- `.travis.yml`
- `.travis/get_artifactory_creds.sh`
- `.travis/secretsmanagercli.sh`
- `travis-settings.xml` (rename to `settings.xml` if it was used for Maven server config)

### E9. Validate

- Run `sps-manoeuvre --doctor` if installed
- Verify all `get_env` key names match those configured in the SPS toolchain's Secrets Manager
- Confirm `scripts/*.sh` are executable (`chmod +x`)
- Confirm signing step uses `csso-image-sign` and all other steps use `pipeline-base-ubi`

**Safety rule:** Present a full summary of all file changes and deletions before raising any PR. Wait for explicit approval.

---

## Workflow F — Automated Pipeline Failure Monitor

**Trigger:** User asks about pipeline failures, wants to check if the bot is watching, or asks about `--monitor` mode.

| Mode | What it does |
|---|---|
| `--run` | One-shot: fetch new announcements → classify → scan repos → post Slack alerts. Safe to schedule via cron or launchd. |
| `--monitor` | Continuous: polls `#cics-sps-notifications` every 5 minutes for failure notifications → fetches IBM Cloud Tekton logs → classifies failure → posts findings. |

**How `--monitor` determines root cause:**
- Looks for failure messages (red attachment `#E01E5A` or text containing "has failed" / "pipeline failed")
- If `IBM_CLOUD_API_KEY` is set and a run URL is present, fetches Tekton step logs
- **Build failure** (user's own code/Maven/Gradle broke) → posts the error snippet directly; does NOT search SPS channels
- **SPS/infra issue** (scan timeout, signing failure, image pull error) → searches troubleshooting channels and surfaces relevant threads

---

## Workflow G — Commons Internals: What Does This `/opt/commons/` Call Do?

Use this workflow when the user sees a script path in their `.pipeline-config.yaml` and wants to understand what it does, what properties to configure, or why a scan or signing step is failing.

### G1. Identify the script

Extract the script path from the pipeline config. The format is always:
```
/opt/commons/<folder>/<script.sh>
```

Consult [`references/commons-internals.md`](./references/commons-internals.md) for the full mapping. Quick reference:

| Script path | What it does |
|---|---|
| `/opt/commons/detect-secrets/run_scan.sh` | Scans repo for committed secrets; uses `.secrets.baseline` for whitelisting |
| `/opt/commons/static-scan/run.sh` | Dispatcher for static analysis — does nothing unless opt-in properties are set |
| `/opt/commons/compliance-checks/run.sh` | Mend SCA dependency scan — requires `opt-in-mend-sca: 1` to actually run |
| `/opt/commons/scan-artifact/scan.sh` | CVE scanning of container image artifacts (CIMS, VA, Sysdig, Xray) |
| `/opt/commons/ciso/sign_artifacts.sh` | Signs non-image artifacts (tar, zip, JAR) using GaraSign |
| `/opt/commons/ciso/sign_icr.sh` | Signs container images on IBM Container Registry using GaraSign + Skopeo/Cosign |
| `/opt/commons/ciso/sign_artifactory.sh` | Signs images on TaaS Artifactory using GaraSign + Skopeo |
| `/opt/commons/ciso/sign_jar_jarsigner.sh` | Signs JAR files using GaraSign + jarsigner |
| `/opt/commons/verify-artifact/verify_artifact_sign.sh` | Verifies artifact signatures (Artifactory) |
| `/opt/commons/verify-artifact/verify_icr_sign.sh` | Verifies ICR image signatures |

### G2. Where these scripts come from

These scripts are cloned from [`compliance-commons-internal`](https://github.ibm.com/one-pipeline/compliance-commons-internal) into `/opt/commons/` inside the SPS image at **build time**. They are not fetched at pipeline runtime — they are baked in at a pinned commit SHA defined in [`compliance-pipelines/defaults/defaults.yaml`](https://github.ibm.com/one-pipeline/compliance-pipelines).

The pipeline Tekton task and pipeline YAMLs live in [`compliance-pipelines`](https://github.ibm.com/one-pipeline/compliance-pipelines). Your `.pipeline-config.yaml` is the adopter customisation layer that overrides or extends those defaults — it is read by SPS and merged with `defaults/defaults.yaml` at runtime.

### G3. Diagnose why a script isn't doing what's expected

**Mend SCA not running (compliance-checks step completes with no scan output):**
- `opt-in-mend-sca` must be set to `1` in pipeline properties or the step `env:` block
- Also required: `mend-user-email`, `mend-product-name`, and secrets `mend-org-token`, `mend-user-key`

**Static scan step runs but no tools execute:**
- None of the opt-in properties are set. Add at least one: `opt-in-sonar`, `opt-in-gosec`, `opt-in-mend-sast`, `opt-in-fips-scan`

**detect-secrets fails with "unaudited secrets found":**
- `.secrets.baseline` is missing or has unreviewed entries
- Fix: `detect-secrets scan > .secrets.baseline` then `detect-secrets audit .secrets.baseline`

**Signing step fails with "GaraSign not found" or certificate error:**
- Signing steps **must** use `icr.io/continuous-delivery/toolchains/devsecops/csso-image-sign:latest` — GaraSign is not in `pipeline-base-ubi`
- Verify secrets `gara-signing-key` (base64 cert `.pfx`) and `gara-signing-credential` (P12 password) are in Secrets Manager

**`COMMONS_PATH` undefined:**
- Only available inside SPS Tekton steps. When running locally: `export COMMONS_PATH=/opt/commons`

### G4. Key environment variables

| Variable | Value in SPS | Description |
|---|---|---|
| `COMMONS_PATH` | `/opt/commons` | Prefix for all commons script calls |
| `ONE_PIPELINE_PATH` | SPS-managed | Path to pipelinectl tools (`get_env`, `get_secret`, etc.) |
| `WORKSPACE` | Network PVC | Persistent across stages — slower |
| `STAGE_WORKSPACE` | Local disk | Fast I/O — ~3× faster than `$WORKSPACE`, use for build/compile |
| `APP_REPO_FOLDER` | SPS-managed | Checked-out repo folder name inside `$WORKSPACE` |
| `PIPELINE_DEBUG` | User-set | Set to `1` to enable `set -x` in commons scripts |

### G5. pipelinectl API

| Function | Description |
|---|---|
| `get_env <key> [default]` | Read a pipeline property (non-secret config) |
| `get_secret <key>` | Read a secret from linked Secrets Manager — **use this for secrets, not `get_env`** |
| `set_env <key> <value>` | Write a property for use in later steps |
| `load_repo app-repo path` | Get the checked-out repo path inside `$WORKSPACE` |
| `save_artifact <name> type=<type>` | Register an artifact for scan/sign steps |
| `load_artifact <name> <property>` | Read a property of a registered artifact |

> **Breaking change deadline 31 Aug 2026:** `get_env` will stop working for secrets. All secret access must migrate to `get_secret <key>`.

---


## Key Rules (Always Apply)

1. **Read before editing.** Always read existing pipeline files and CI config before proposing changes.
2. **No production operations without approval.** Any `git push`, `create_pr`, pipeline trigger, or Secrets Manager write requires explicit user confirmation.
3. **Diagnose before changing.** Check logs, configs, and Slack troubleshooting threads before suggesting edits.
4. **Never hardcode credentials.** All secrets must come from `get_env` — never inline env vars, never committed to files.
5. **One change at a time.** Propose each change as a diff and confirm before applying.
6. **Deduplicate announcements.** Multiple Slack messages about the same topic → one action item per topic per repo.
7. **Image discipline.** `csso-image-sign` only for signing steps. `pipeline-base-ubi` everywhere else.
