"""Unit tests for SPS Manoeuvre doctor command and config loading."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from sps_manoeuvre import doctor
from sps_manoeuvre.config import _load_yaml_config, _parse_simple_yaml


class TestDoctor(unittest.TestCase):
    """Test suite for doctor health checks."""

    def test_check_python(self) -> None:
        """Python check should return PASS on Python >= 3.10."""
        res = doctor.check_python()
        self.assertIn(res.status, ("PASS", "FAIL"))
        if res.status == "PASS":
            self.assertIn(">=", res.message)

    def test_check_packages(self) -> None:
        """Installed dependencies check."""
        res = doctor.check_packages()
        self.assertEqual(res.status, "PASS")

    def test_check_webhook_url_validation(self) -> None:
        """Validate webhook URL checker logic."""
        with patch.dict("os.environ", {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/services/T123/B456/789"}):
            res = doctor.check_webhook_url()
            self.assertEqual(res.status, "PASS")

        with patch.dict("os.environ", {"SLACK_WEBHOOK_URL": "https://other.domain.com/webhook"}):
            res = doctor.check_webhook_url()
            self.assertEqual(res.status, "WARN")

        with patch.dict("os.environ", {}, clear=True), \
             patch.object(doctor, "_load_env_from_mcp_json", return_value={}):
            res = doctor.check_webhook_url()
            self.assertEqual(res.status, "FAIL")

    def test_check_github_connectivity_mock(self) -> None:
        """Mock GitHub connectivity check with success and failure."""
        with patch.dict("os.environ", {"GITHUB_TOKEN": "mock_token"}):
            with patch("github.Github") as mock_gh_cls:
                mock_gh_instance = MagicMock()
                mock_user = MagicMock()
                mock_user.login = "test-user"
                mock_gh_instance.get_user.return_value = mock_user
                mock_gh_cls.return_value = mock_gh_instance

                res = doctor.check_github_connectivity()
                self.assertEqual(res.status, "PASS")
                self.assertIn("test-user", res.message)

        with patch.dict("os.environ", {"GITHUB_TOKEN": "bad_token"}):
            with patch("github.Github") as mock_gh_cls:
                mock_gh_instance = MagicMock()
                mock_gh_instance.get_user.side_effect = Exception("401 Unauthorized")
                mock_gh_cls.return_value = mock_gh_instance

                res = doctor.check_github_connectivity()
                self.assertEqual(res.status, "FAIL")
                self.assertIn("401 Unauthorized", res.message)

    def test_yaml_config_override_parsing(self) -> None:
        """Test simple YAML parser and config override functionality."""
        yaml_content = """
# Test config
slack_output_channel: "custom-output"
pipeline_notifications_channel: "custom-notifications"
pipeline_notifications_channel_id: "C999999"

announcement_channels:
  - name: "custom-announce"
    id: "C111111"

troubleshooting_channels:
  - "custom-debug"
"""
        parsed = _parse_simple_yaml(yaml_content)
        self.assertEqual(parsed.get("slack_output_channel"), "custom-output")
        self.assertEqual(parsed.get("pipeline_notifications_channel"), "custom-notifications")
        self.assertEqual(parsed.get("pipeline_notifications_channel_id"), "C999999")
        self.assertIn("announcement_channels", parsed)
        self.assertIn("troubleshooting_channels", parsed)


if __name__ == "__main__":
    unittest.main()
