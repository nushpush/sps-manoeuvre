"""Allow running as: python -m sps_pipeline_bot [--bootstrap | --run | --monitor]

  --bootstrap   One-time setup: derive and cache the Slack AES key from Keychain.
                Run this once in a terminal before using the bot.

  --run         Fetch announcements → scan repos → post alerts (runs once).

  --monitor     Watch #cics-sps-notifications for pipeline failures, fetch logs,
                and post findings. Runs continuously (polls every 5 minutes).

  (no flag)     Start the MCP server (for use inside Bob).
"""
import sys

if "--bootstrap" in sys.argv:
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
