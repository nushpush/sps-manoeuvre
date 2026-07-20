"""Allow running as: python -m sps_pipeline_bot [--bootstrap | --run | --monitor]

  --bootstrap   One-time setup: derive and cache the Slack AES key from Keychain.
                Run this once in a terminal before using the bot.

  --run         Full automated pipeline: fetch announcements → scan repos → post alerts.
                Safe to run on a schedule (cron, launchd, SPS).

  --monitor     Watch #cics-sps-notifications for pipeline failures, fetch the actual
                error from IBM Cloud logs, search for a fix, and post to output channel.
                Runs continuously (polls every 5 minutes).

  (no flag)     Start the MCP server (for use inside Bob).
"""
import sys

if "--bootstrap" in sys.argv:
    from .slack_token_refresh import bootstrap
    bootstrap()
elif "--run" in sys.argv:
    from .runner import run_pipeline
    run_pipeline(verbose=True)
elif "--monitor" in sys.argv:
    from .pipeline_monitor import run_monitor
    run_monitor()
else:
    from .main import run
    run()
