"""Unit tests for SPS Pipeline Bot setup wizard."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sps_pipeline_bot import setup_wizard


class TestSetupWizard(unittest.TestCase):
    """Test suite for setup_wizard module."""

    def test_check_python_version(self) -> None:
        """Python check should pass on standard test environments (>= 3.10)."""
        self.assertTrue(setup_wizard.check_python_version())

    def test_check_packages(self) -> None:
        """Required installed packages should be importable."""
        self.assertTrue(setup_wizard.check_packages())

    def test_setup_idempotency_non_interactive(self) -> None:
        """Running setup in non-interactive mode should safely scaffold without errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_root = Path(tmpdir)
            tmp_bob = tmp_root / ".bob"
            tmp_mcp = tmp_bob / "mcp.json"

            with patch.object(setup_wizard, "_PROJECT_ROOT", tmp_root), \
                 patch.object(setup_wizard, "_BOB_DIR", tmp_bob), \
                 patch.object(setup_wizard, "_MCP_JSON", tmp_mcp), \
                 patch.object(setup_wizard, "_SLACK_KEY", tmp_bob / "slack-key.bin"):

                # First run
                res1 = setup_wizard.setup_mcp_config(interactive=False)
                self.assertTrue(res1)
                self.assertTrue(tmp_mcp.exists())

                with tmp_mcp.open() as fh:
                    data1 = json.load(fh)
                self.assertIn("mcpServers", data1)
                self.assertIn("sps-pipeline-bot", data1["mcpServers"])

                # Second run (idempotency check)
                res2 = setup_wizard.setup_mcp_config(interactive=False)
                self.assertTrue(res2)

                with tmp_mcp.open() as fh:
                    data2 = json.load(fh)
                self.assertEqual(data1, data2)

    def test_mask_secret(self) -> None:
        """Test secret masking helper."""
        self.assertEqual(setup_wizard._mask_secret(""), "<not set>")
        self.assertEqual(setup_wizard._mask_secret("short"), "***")
        self.assertEqual(setup_wizard._mask_secret("ghp_1234567890abcdef"), "ghp_...cdef")


if __name__ == "__main__":
    unittest.main()
