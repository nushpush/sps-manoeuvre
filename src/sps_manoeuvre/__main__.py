"""Allow running as: python -m sps_manoeuvre [--setup | --doctor | --run | --monitor]

  --setup       Interactive setup wizard for first-time configuration.
  --doctor      Diagnostic health check verifying tokens, packages, and connectivity.
  --run         Fetch announcements → scan repos → post alerts (runs once).
  --monitor     Watch pipeline notifications for failures, fetch logs, and post findings.
  (no flag)     Start the MCP server (for use inside Bob).
"""
import sys


def main() -> None:
    """CLI entry point dispatching based on command line arguments."""
    if "--setup" in sys.argv:
        from .setup_wizard import run as run_setup
        sys.exit(run_setup())
    elif "--doctor" in sys.argv:
        from .doctor import run as run_doctor
        sys.exit(run_doctor())
    elif "--bootstrap" in sys.argv:
        from .slack_token_refresh import bootstrap
        bootstrap()
    elif "--run" in sys.argv:
        from .monitor import run_pipeline
        run_pipeline(verbose=True)
    elif "--monitor" in sys.argv:
        from .monitor import run_monitor
        run_monitor()
    else:
        from .main import run
        run()


if __name__ == "__main__":
    main()
