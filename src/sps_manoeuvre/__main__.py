"""Allow running as: python -m sps_manoeuvre [--setup | --doctor | --run | --monitor]

  --setup       Interactive setup wizard for first-time configuration.
  --doctor      Diagnostic health check verifying tokens, packages, and connectivity.
  --run         Fetch announcements → scan repos → post alerts (runs once).
  --monitor     Watch pipeline notifications for failures, fetch logs, and post findings.
  (no flag)     Start the MCP server (for use inside Bob).
"""
import json
import os
import sys
from pathlib import Path


def _load_env_from_mcp_json() -> None:
    """Inject credentials from .bob/mcp.json into os.environ if not already set.

    The setup wizard stores all tokens inside the ``env`` block of
    .bob/mcp.json so that Bob's MCP runner can inject them automatically.
    When the CLI is invoked directly (--run, --monitor, --doctor) those
    environment variables are not present, so we read them back here.
    Only variables that are absent from the environment are set — existing
    values (e.g. set by the user's shell) always take precedence.
    """
    mcp_json = Path(__file__).resolve().parent.parent.parent / ".bob" / "mcp.json"
    if not mcp_json.exists():
        return
    try:
        with mcp_json.open() as fh:
            data = json.load(fh)
        env = data.get("mcpServers", {}).get("sps-manoeuvre", {}).get("env", {})
        for key, value in env.items():
            if key not in os.environ and value:
                os.environ[key] = value
    except Exception:
        pass


def main() -> None:
    """CLI entry point dispatching based on command line arguments."""
    if "--setup" in sys.argv:
        from .setup_wizard import run as run_setup
        sys.exit(run_setup())
    elif "--doctor" in sys.argv:
        _load_env_from_mcp_json()
        from .doctor import run as run_doctor
        sys.exit(run_doctor())
    elif "--bootstrap" in sys.argv:
        from .slack_token_refresh import bootstrap
        bootstrap()
    elif "--run" in sys.argv:
        _load_env_from_mcp_json()
        from .monitor import run_pipeline
        run_pipeline(verbose=True)
    elif "--monitor" in sys.argv:
        _load_env_from_mcp_json()
        from .monitor import run_monitor
        run_monitor()
    else:
        from .main import run
        run()


if __name__ == "__main__":
    main()
