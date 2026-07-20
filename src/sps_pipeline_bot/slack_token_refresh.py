"""Extract the current Slack session token (xoxc-) and cookie (xoxd-)
directly from the Slack desktop app's on-disk storage.

No browser interaction or manual copy-paste needed. Works as long as:
  - The Slack desktop app is installed (macOS only)
  - The user is logged in to Slack

On first run, requires the AES key to be bootstrapped via:
    python3 -m sps_pipeline_bot.slack_token_refresh --bootstrap
which calls `security` once in a terminal context (where Keychain access is
already granted) and caches the derived AES key to ~/.bob/slack-key.bin.
Subsequent runs read the cached key — no Keychain or subprocess needed.

Usage:
    from sps_pipeline_bot.slack_token_refresh import refresh_slack_env
    refresh_slack_env()   # injects SLACK_USER_TOKEN + SLACK_COOKIE into os.environ
"""

from __future__ import annotations

import hashlib
import hmac
import os
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path


_LEVELDB_DIR = Path.home() / "Library/Application Support/Slack/Local Storage/leveldb"
_COOKIES_DB  = Path.home() / "Library/Application Support/Slack/Cookies"
_KEY_CACHE   = Path(__file__).parent.parent.parent / ".bob" / "slack-key.bin"


def _keychain_password() -> bytes:
    """Fetch the Slack Safe Storage key from macOS Keychain via subprocess.

    Only works when called from a terminal/shell with existing Keychain access.
    Use bootstrap() to cache the derived key so this is only called once.
    """
    result = subprocess.run(
        ["security", "find-generic-password", "-w", "-s", "Slack Safe Storage", "-a", "Slack Key"],
        capture_output=True,
        text=True,
        # No timeout — macOS may show a Keychain access dialog that requires user interaction
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Could not read Slack Safe Storage from Keychain.\n"
            f"security error: {result.stderr.strip()}"
        )
    return result.stdout.strip().encode()


def _derive_key(password: bytes) -> bytes:
    """Derive the AES key using the same PBKDF2 parameters as Chromium/Electron."""
    try:
        from Crypto.Protocol.KDF import PBKDF2
    except ImportError:
        raise RuntimeError("pycryptodome is required: pip install pycryptodome")

    def prf(p: bytes, s: bytes) -> bytes:
        return hmac.new(p, s, hashlib.sha1).digest()

    return PBKDF2(password, b"saltysalt", dkLen=16, count=1003, prf=prf)


def _load_cached_key() -> bytes | None:
    """Load the cached AES key from disk (written by bootstrap())."""
    if _KEY_CACHE.exists():
        return _KEY_CACHE.read_bytes()
    return None


def _save_cached_key(key: bytes) -> None:
    """Persist the derived AES key to disk for future runs."""
    _KEY_CACHE.parent.mkdir(parents=True, exist_ok=True)
    _KEY_CACHE.write_bytes(key)
    _KEY_CACHE.chmod(0o600)  # owner read/write only


def bootstrap() -> None:
    """One-time setup: derive and cache the AES key from Keychain.

    Run this once from a terminal where Keychain access is already granted:
        python3 -m sps_pipeline_bot.slack_token_refresh --bootstrap
    """
    password = _keychain_password()
    key = _derive_key(password)
    _save_cached_key(key)
    print(f"✓ Slack AES key cached to {_KEY_CACHE}")


def _decrypt_cookie(encrypted_value: bytes, key: bytes) -> str:
    """Decrypt a Chromium AES-CBC encrypted cookie value (v10 prefix)."""
    try:
        from Crypto.Cipher import AES
    except ImportError:
        raise RuntimeError("pycryptodome is required: pip install pycryptodome")

    iv = b" " * 16
    ciphertext = encrypted_value[3:]  # strip 'v10' prefix
    cipher = AES.new(key, AES.MODE_CBC, iv)
    decrypted = cipher.decrypt(ciphertext)
    pad = decrypted[-1]
    value = decrypted[:-pad].decode("utf-8", errors="replace")
    # Strip any leading garbage before xoxd-
    idx = value.find("xoxd-")
    return value[idx:] if idx >= 0 else value


def _read_xoxd() -> str | None:
    """Read and decrypt the 'd' cookie from Slack's Cookies SQLite database.

    Requires the AES key to have been cached by bootstrap() first.
    """
    key = _load_cached_key()
    if key is None:
        raise RuntimeError(
            "Slack AES key not found. Run bootstrap first:\n"
            "  python3 -m sps_pipeline_bot.slack_token_refresh --bootstrap"
        )
    if not _COOKIES_DB.exists():
        return None
    tmp = tempfile.mktemp(suffix=".db")
    try:
        shutil.copy2(_COOKIES_DB, tmp)
        conn = sqlite3.connect(tmp)
        rows = conn.execute(
            "SELECT encrypted_value FROM cookies WHERE name='d' AND host_key='.slack.com'"
        ).fetchall()
        conn.close()
        if not rows:
            return None
        return _decrypt_cookie(rows[0][0], key)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _read_xoxc() -> str | None:
    """Extract the xoxc- token from Slack's LevelDB local storage.

    Scans .log (write-ahead log, freshest) then the 5 most-recent .ldb files.
    Uses a pure-Python byte scan — no subprocess needed, no permission prompts.
    """
    import re
    if not _LEVELDB_DIR.exists():
        return None
    log_files = sorted(_LEVELDB_DIR.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    ldb_files = sorted(_LEVELDB_DIR.glob("*.ldb"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]
    candidates = log_files + ldb_files
    if not candidates:
        return None

    tokens: list[str] = []
    pattern = re.compile(rb"xoxc-[A-Za-z0-9\-]{20,}")
    for path in candidates:
        try:
            data = path.read_bytes()
            for m in pattern.finditer(data):
                tok = m.group(0).decode("ascii", errors="ignore")
                if len(tok) > 20:
                    tokens.append(tok)
        except OSError:
            continue
    if not tokens:
        return None
    return max(tokens, key=len)


def get_slack_tokens() -> tuple[str, str]:
    """Return (xoxc_token, xoxd_cookie) read live from the Slack desktop app.

    Raises RuntimeError if either token cannot be found or key is not bootstrapped.
    """
    xoxc = _read_xoxc()
    if not xoxc:
        raise RuntimeError(
            "Could not find xoxc- token in Slack LevelDB.\n"
            "Make sure the Slack desktop app is installed and you are logged in."
        )

    xoxd = _read_xoxd()
    if not xoxd:
        raise RuntimeError(
            "Could not decrypt xoxd cookie from Slack Cookies database.\n"
            "Make sure the Slack desktop app is installed and you are logged in."
        )

    return xoxc, xoxd


_refreshed = False


def refresh_slack_env() -> None:
    """Inject fresh SLACK_USER_TOKEN and SLACK_COOKIE into os.environ.

    Called once at MCP server startup and lazily on first _get_client() call.
    If tokens are explicitly set in the environment (e.g. for testing), they
    take precedence and no extraction is attempted.
    Falls back silently if extraction fails (e.g. on Linux/CI without Slack).
    """
    global _refreshed
    if _refreshed:
        return

    # If both tokens are already explicitly provided, respect them as-is
    if os.environ.get("SLACK_USER_TOKEN") and os.environ.get("SLACK_COOKIE"):
        _refreshed = True
        return

    try:
        xoxc, xoxd = get_slack_tokens()
        os.environ["SLACK_USER_TOKEN"] = xoxc
        os.environ["SLACK_COOKIE"] = xoxd
        _refreshed = True
    except Exception as exc:
        # Non-fatal on non-macOS or if Slack isn't installed
        import warnings
        warnings.warn(f"Slack token auto-refresh failed: {exc}", stacklevel=2)
