"""Allow running as: python -m sps_pipeline_bot [--bootstrap]"""
import sys

if "--bootstrap" in sys.argv:
    from .slack_token_refresh import bootstrap
    bootstrap()
else:
    from .main import run
    run()
