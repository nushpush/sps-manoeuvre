"""Interactive setup wizard for SPS Pipeline Bot.

Run as:
    python -m sps_pipeline_bot --setup
    sps-pipeline-bot --setup

Performs idempotent initial environment checks, configuration scaffolding,
and optional token bootstrapping.
"""

from __future__ import annotations

import importlib
import json
import os
import shutil
import sys
from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_BOB_DIR = _PROJECT_ROOT / ".bob"
_MCP_JSON = _BOB_DIR / "mcp.json"
_SLACK_KEY = _BOB_DIR / "slack-key.bin"
_REPOS_FILE = Path(__file__).resolve().parent / "repos.json"
_REPOS_EXAMPLE = Path(__file__).resolve().parent / "repos.json.example"

_REQUIRED_PACKAGES = [
    ("mcp", "mcp"),
    ("slack_sdk", "slack-sdk"),
    ("github", "PyGithub"),
    ("httpx", "httpx"),
    ("Crypto", "pycryptodome"),
]


def _mask_secret(secret: str) -> str:
    """Mask secret value showing first 4 and last 4 characters."""
    if not secret:
        return "<not set>"
    if len(secret) <= 8:
        return "***"
    return f"{secret[:4]}...{secret[-4:]}"


def check_python_version() -> bool:
    """Check Python version >= 3.10."""
    print(f"🐍 Python version: {sys.version.split()[0]}", end=" ")
    if sys.version_info >= (3, 10):
        print("✓ (>= 3.10)")
        return True
    print("❌ (Requires Python 3.10 or later)")
    return False


def check_packages() -> bool:
    """Check required dependencies are installed."""
    print("\n📦 Checking dependencies:")
    all_ok = True
    for mod_name, pkg_name in _REQUIRED_PACKAGES:
        try:
            importlib.import_module(mod_name)
            print(f"  ✓ {pkg_name}")
        except ImportError:
            print(f"  ❌ {pkg_name} is missing (run: pip install -e .)")
            all_ok = True
    return all_ok


def setup_bob_dir() -> Path:
    """Ensure .bob directory exists."""
    _BOB_DIR.mkdir(parents=True, exist_ok=True)
    return _BOB_DIR


def setup_mcp_config(interactive: bool = True) -> bool:
    """Scaffold or update .bob/mcp.json."""
    setup_bob_dir()
    existing_env: dict[str, str] = {}
    python_path = sys.executable
    src_dir = str((_PROJECT_ROOT / "src").resolve())

    if _MCP_JSON.exists():
        try:
            with _MCP_JSON.open() as fh:
                data = json.load(fh)
                server_cfg = data.get("mcpServers", {}).get("sps-pipeline-bot", {})
                existing_env = server_cfg.get("env", {})
        except Exception:
            existing_env = {}

    if existing_env:
        print(f"\n⚙️  Found existing MCP configuration ({_MCP_JSON}):")
        print(f"  GITHUB_TOKEN:      {_mask_secret(existing_env.get('GITHUB_TOKEN', ''))}")
        print(f"  SLACK_WEBHOOK_URL: {_mask_secret(existing_env.get('SLACK_WEBHOOK_URL', ''))}")
        print(f"  IBM_CLOUD_API_KEY: {_mask_secret(existing_env.get('IBM_CLOUD_API_KEY', ''))}")

        if interactive and sys.stdin.isatty():
            try:
                ans = input("\nDo you want to update these credentials? [y/N]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                ans = "n"
            if ans != "y":
                print("  Keeping existing MCP configuration.")
                return True
        else:
            return True

    print("\n🔑 Configuring credentials in .bob/mcp.json:")
    github_token = existing_env.get("GITHUB_TOKEN", "")
    slack_webhook = existing_env.get("SLACK_WEBHOOK_URL", "")
    ibmcloud_key = existing_env.get("IBM_CLOUD_API_KEY", "")

    if interactive and sys.stdin.isatty():
        try:
            prompt_gh = f"GitHub Personal Access Token [{_mask_secret(github_token)}]: " if github_token else "GitHub Personal Access Token (repo scope): "
            val = input(prompt_gh).strip()
            if val:
                github_token = val

            prompt_slack = f"Slack Incoming Webhook URL [{_mask_secret(slack_webhook)}]: " if slack_webhook else "Slack Incoming Webhook URL: "
            val = input(prompt_slack).strip()
            if val:
                slack_webhook = val

            prompt_ibm = f"IBM Cloud API Key (optional) [{_mask_secret(ibmcloud_key)}]: " if ibmcloud_key else "IBM Cloud API Key (optional): "
            val = input(prompt_ibm).strip()
            if val:
                ibmcloud_key = val
        except (EOFError, KeyboardInterrupt):
            print("\nSetup cancelled.")
            return False

    env_config: dict[str, str] = {
        "GITHUB_TOKEN": github_token,
        "SLACK_WEBHOOK_URL": slack_webhook,
    }
    if ibmcloud_key:
        env_config["IBM_CLOUD_API_KEY"] = ibmcloud_key

    mcp_data = {
        "mcpServers": {
            "sps-pipeline-bot": {
                "command": python_path,
                "args": ["-m", "sps_pipeline_bot"],
                "cwd": src_dir,
                "env": env_config,
            }
        }
    }

    with _MCP_JSON.open("w") as fh:
        json.dump(mcp_data, fh, indent=2)
    print(f"✓ Saved configuration to {_MCP_JSON}")
    return True


def setup_repos_json() -> bool:
    """Ensure repos.json exists."""
    print("\n📋 Checking repos watchlist:")
    if _REPOS_FILE.exists():
        print(f"  ✓ {_REPOS_FILE} exists.")
        return True

    if _REPOS_EXAMPLE.exists():
        shutil.copy(_REPOS_EXAMPLE, _REPOS_FILE)
        print(f"  ✓ Created {_REPOS_FILE} from template.")
        editor = os.environ.get("EDITOR")
        if editor and sys.stdin.isatty():
            try:
                ans = input(f"Open {_REPOS_FILE} in $EDITOR ({editor}) now? [Y/n]: ").strip().lower()
                if ans != "n":
                    import subprocess
                    subprocess.call([editor, str(_REPOS_FILE)])
            except Exception:
                pass
        else:
            print(f"  👉 Please edit {_REPOS_FILE} to add your repositories.")
        return True

    print(f"  ❌ Template {_REPOS_EXAMPLE} not found.")
    return False


def setup_slack_bootstrap() -> bool:
    """Bootstrap Slack token auto-refresh on macOS if needed."""
    if sys.platform != "darwin":
        print("\nℹ️  Non-macOS platform detected: Slack desktop auto-refresh is macOS only.")
        print("   If you need Slack channel reading, add SLACK_USER_TOKEN and SLACK_COOKIE to .bob/mcp.json.")
        return True

    print("\n🔐 Slack token caching (macOS):")
    if _SLACK_KEY.exists():
        print(f"  ✓ Cached Slack AES key exists ({_SLACK_KEY}).")
        return True

    print("  Bootstrapping Slack AES key from Keychain...")
    try:
        from .slack_token_refresh import bootstrap
        bootstrap()
        return True
    except Exception as exc:
        print(f"  ⚠️  Slack bootstrap failed: {exc}")
        print("  You can run 'python -m sps_pipeline_bot --bootstrap' in terminal later.")
        return False


def run(interactive: bool = True) -> int:
    """Run the complete setup wizard."""
    print("=" * 60)
    print("🤖 SPS Pipeline Bot — Setup Wizard")
    print("=" * 60)

    py_ok = check_python_version()
    check_packages()
    setup_mcp_config(interactive=interactive)
    setup_repos_json()
    setup_slack_bootstrap()

    print("\n" + "=" * 60)
    print("🎉 Setup Wizard Complete!")
    print("=" * 60)
    print("Summary & Next Steps:")
    print(" 1. Verify/edit your watched repos in src/sps_pipeline_bot/repos.json")
    print(" 2. Run diagnostic health check: sps-pipeline-bot --doctor")
    print(" 3. Run announcement scan:       sps-pipeline-bot --run")
    print("=" * 60)
    return 0 if py_ok else 1


if __name__ == "__main__":
    sys.exit(run())
