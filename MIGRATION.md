# Migration Guide: Local Setup to Hardened Multi-Team Version

Hi Nush,

This guide summarizes all updates made in the hardening release and provides step-by-step instructions for updating your current local working environment.

---

## What Changed

1. **CLI Commands & Entry Points:**
   - The CLI script `sps-manoeuvre` now routes through `__main__.py` instead of directly launching the server.
   - Added `--setup` for guided interactive configuration.
   - Added `--doctor` for diagnostic verification and connectivity testing.

2. **Team Config Overrides (`config.yaml`):**
   - Channel targets and IDs are no longer locked exclusively inside `config.py`.
   - You or other teams can customize notification channel destinations or add new channels via an optional `config.yaml` (see `src/sps_manoeuvre/config.yaml.example`).
   - If `config.yaml` is absent, all existing default channels and IDs remain identical.

3. **Production Hardening:**
   - GitHub multi-repo scans isolate exceptions per repository; a rate limit or 404 in one repository will not crash the entire scan loop.
   - Slack history scanning handles permalink/user metadata lookups defensively to prevent unexpected message formatting failures.

4. **Testing Suite:**
   - Added `tests/test_setup.py` and `tests/test_doctor.py` covering setup wizard idempotency, doctor check validations, and YAML parsing.

---

## Migration Steps for Your Existing Environment

Your existing tokens in `.bob/mcp.json`, your cached AES key in `.bob/slack-key.bin`, and your repo watchlist in `src/sps_manoeuvre/repos.json` remain 100% compatible. No credentials need to be re-entered.

### 1. Re-install the package in editable mode
To register the updated CLI entrypoint:
```bash
cd /Users/anushka/.bob/playground/sps-manoeuvre
pip3 install -e .
```

### 2. Run the diagnostic doctor
Verify that all your existing credentials and configurations pass:
```bash
sps-manoeuvre --doctor
```
You should see all green `[PASS]` checks for your Python version, packages, MCP configuration, Slack key, repos watchlist, and GitHub/Slack connectivity.

### 3. Verify normal MCP server & standalone execution
- Run a standalone announcement scan:
  ```bash
  sps-manoeuvre --run
  ```
- In Bob: No changes required in Bob MCP settings. The server will start with identical tool definitions (`ping`, `fetch_announcements`, `scan_repos_tool`, etc.).

---

## Summary of New Files Added

- `src/sps_manoeuvre/setup_wizard.py` — Setup wizard logic (`--setup`)
- `src/sps_manoeuvre/doctor.py` — Diagnostic health checker (`--doctor`)
- `src/sps_manoeuvre/config.yaml.example` — Documentation of all team config overrides
- `PRODUCTION_READINESS.md` — Formal audit report and security review
- `tests/test_setup.py` — Unit tests for setup wizard
- `tests/test_doctor.py` — Unit tests for doctor command and config parser
- `MIGRATION.md` — This migration guide
