# Production Readiness & Operational Audit Report

**Service / Component:** SPS Pipeline Bot  
**Target Audience:** Engineering Leads, Multi-team Adopters, DevOps Operations  
**Evaluation Standard:** Enterprise Production Readiness & Multi-Team Portability  

---

## 1. Audit Findings Summary

Prior to this hardening cycle, the repository was configured for single-developer local operations on macOS. While core business logic (classification rules, MCP tools, and log parsers) functioned well, adoption across other teams encountered several friction points:

1. **Manual File & Path Configuration:**
   - `.bob/mcp.json` required manual JSON authoring with absolute system paths (`/Users/anushka/...`).
   - Launchd scripts and daily runner scripts contained hardcoded user workspace paths.
   - Channel names (`sps-updates-modernization`, `cics-sps-notifications`) and IDs were fixed in Python code with no team override mechanism.

2. **Lack of Automated Onboarding & Verification:**
   - No interactive CLI wizard or preflight health check (`--setup` / `--doctor`).
   - Entry points were ununified (`main.py` vs `__main__.py` vs standalone flags).

3. **Error Isolation & Resilience:**
   - A single repository failure during GitHub code scanning or Slack permalink extraction could fail or interrupt wider batch execution.
   - Non-ASCII Slack session tokens previously raised `UnicodeEncodeError` in Python's HTTP header transport (addressed by ASCII sanitation).

---

## 2. Issues Found and Remediated

| Component | Issue Identified | Resolution Implemented |
|---|---|---|
| **CLI & Packaging** | `pyproject.toml` pointed CLI binary to `main:run` (server only) | Updated `[project.scripts]` to `sps_pipeline_bot.__main__:main` supporting `--setup`, `--doctor`, `--bootstrap`, `--run`, `--monitor`. |
| **Onboarding** | No automated configuration scaffolding | Created [`setup_wizard.py`](src/sps_pipeline_bot/setup_wizard.py) (`--setup`) with idempotent `.bob/` creation, credential prompting, and auto-bootstrapping. |
| **Health Checks** | No way to test if credentials and permissions worked before running | Created [`doctor.py`](src/sps_pipeline_bot/doctor.py) (`--doctor`) testing 9 distinct subsystems with PASS/WARN/FAIL reporting and actionable remediation instructions. |
| **Configuration** | Channel IDs and notification targets were hardcoded | Introduced [`config.yaml.example`](src/sps_pipeline_bot/config.yaml.example) and backward-compatible optional `config.yaml` override loading in [`config.py`](src/sps_pipeline_bot/config.py). |
| **GitHub Scanner** | Exception during threaded repo scan crashed thread pool loop | Hardened error handling in [`scan_repos()`](src/sps_pipeline_bot/github_client.py:146) to isolate failures per repo and log warnings. |
| **Slack History** | Permalinks / user info lookups could fail on unusual channel messages | Broadened exception handling in [`slack_client.py`](src/sps_pipeline_bot/slack_client.py:74) to guarantee uninterrupted message processing. |

---

## 3. Remaining Manual Steps & Why They Cannot Be Automated

While configuration generation is now automated via `sps-pipeline-bot --setup`, the following manual actions remain necessary due to security and identity constraints:

1. **Generating a GitHub Personal Access Token (PAT):**
   - *Why:* GitHub Enterprise requires personal authentication and explicit user consent to issue tokens with `repo` scopes.
2. **Slack Keychain Prompt Approval (macOS):**
   - *Why:* macOS Security Framework (`/usr/bin/security`) requires interactive GUI consent when `python3` requests access to the "Slack Safe Storage" Keychain entry.
3. **Slack Incoming Webhook URL Creation:**
   - *Why:* Webhook URLs are provisioned within specific Slack apps and bound to specific workspace channels by team administrators.
4. **IBM Cloud API Key Generation (Optional):**
   - *Why:* Required only if continuous Tekton log analysis (`--monitor`) is enabled; must be provisioned by the IAM account owner.

---

## 4. Security & Compliance Checklist

- [x] **Zero Plaintext Secrets in Git:** `.gitignore` actively ignores `.bob/mcp.json`, `.bob/slack-key.bin`, `.env`, and `config.yaml`.
- [x] **File Permission Hardening:** Derived Slack AES key file (`.bob/slack-key.bin`) is created with strict POSIX mode `0600` (read/write by owner only).
- [x] **Masked Diagnostic Output:** Neither `--setup`, `--doctor`, nor log runners ever display unmasked tokens or secrets in terminal output or logs.
- [x] **Least-Privilege GitHub Scope:** Requires only `repo` scope (no organization administrative or webhook permissions required).
- [x] **Outbound-Only Webhook Posting:** The bot never requires broad write access tokens to Slack; outbound notifications use scoped Incoming Webhooks.
- [x] **State Isolation:** Processed message state (`.bob/sps-state.json`) and watched repositories (`repos.json`) are stored locally per workspace.

---

## 5. Known Limitations

1. **Enterprise Slack Restrictions (`conversations.list`):**
   - IBM Enterprise Slack disables directory listing of public channels via API (`conversations.list` returns `enterprise_is_restricted`).
   - Consequently, channel names must map to explicit channel IDs (configured by default in `config.py` and customizable via `config.yaml`).
2. **Platform Specifics for Slack Reading:**
   - Automatic live token extraction from desktop LevelDB / SQLite storage is currently implemented for macOS. Linux and Windows environments must provide `SLACK_USER_TOKEN` (`xoxc-`) and `SLACK_COOKIE` (`xoxd-`) in `.bob/mcp.json` or `.env`.
3. **Tekton Log Retention:**
   - IBM Cloud Tekton pipeline run logs are typically retained for 21–30 days. For older runs, log retrieval will time out and the bot will automatically fall back to troubleshooting search.

---

## 6. Recommended Next Steps for Production Deployment

For enterprise-wide unattended deployment (e.g. running inside IBM Cloud Code Engine or Kubernetes):
1. **Adopt Trusted Profiles & Workload Identity:** Deploy the container under an IBM Cloud IAM Trusted Profile to eliminate the static `IBM_CLOUD_API_KEY`.
2. **Secrets Manager Integration:** Retrieve GitHub PAT and Slack Webhook endpoints dynamically at runtime from IBM Cloud Secrets Manager as documented in [`docs/automation-setup.md`](docs/automation-setup.md).
3. **CI/CD Validation:** Run unit tests (`test_setup.py`, `test_doctor.py`) on pull requests to ensure stability across Python 3.10, 3.11, and 3.12 environments.
