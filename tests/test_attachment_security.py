"""Tests for jira-attachment.py security controls (SSRF, Path Traversal, TLS)."""

import importlib.util
import sys
from pathlib import Path

# Add scripts to path for lib imports
_test_dir = Path(__file__).parent
_scripts_path = _test_dir.parent / "skills" / "jira-communication" / "scripts"
sys.path.insert(0, str(_scripts_path))

# Import jira-attachment.py (hyphenated filename requires importlib)
_core_path = _scripts_path / "core"
_spec = importlib.util.spec_from_file_location(
    "jira_attachment", _core_path / "jira-attachment.py"
)
jira_attachment = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(jira_attachment)


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: SSRF protection — validate_attachment_url()
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidateAttachmentUrl:
    """Attachment URLs must be validated against the configured JIRA_URL host."""

    def test_same_host_accepted(self):
        """URL with same host as JIRA_URL should pass validation."""
        jira_url = "https://jira.example.com"
        att_url = "https://jira.example.com/rest/api/2/attachment/content/12345"
        assert jira_attachment.validate_attachment_url(att_url, jira_url) is True

    def test_different_host_rejected(self):
        """URL pointing to a different host must be rejected (SSRF prevention)."""
        jira_url = "https://jira.example.com"
        att_url = "https://evil.com/steal-credentials"
        assert jira_attachment.validate_attachment_url(att_url, jira_url) is False

    def test_subdomain_mismatch_rejected(self):
        """Subdomain differences must be rejected."""
        jira_url = "https://jira.example.com"
        att_url = "https://jira.evil.com/rest/api/2/attachment/content/1"
        assert jira_attachment.validate_attachment_url(att_url, jira_url) is False

    def test_relative_path_always_accepted(self):
        """Relative paths (no host) are always safe — they'll be prefixed with JIRA_URL."""
        jira_url = "https://jira.example.com"
        att_url = "/rest/api/2/attachment/content/12345"
        assert jira_attachment.validate_attachment_url(att_url, jira_url) is True

    def test_case_insensitive_host_match(self):
        """Host comparison must be case-insensitive."""
        jira_url = "https://Jira.Example.COM"
        att_url = "https://jira.example.com/rest/api/2/attachment/content/1"
        assert jira_attachment.validate_attachment_url(att_url, jira_url) is True

    def test_port_mismatch_rejected(self):
        """Different ports on same host must be rejected."""
        jira_url = "https://jira.example.com:443"
        att_url = "https://jira.example.com:8080/rest/api/2/attachment/content/1"
        assert jira_attachment.validate_attachment_url(att_url, jira_url) is False

    def test_default_https_port_normalized(self):
        """Default port :443 on HTTPS should match host without port."""
        jira_url = "https://jira.example.com:443"
        att_url = "https://jira.example.com/rest/api/2/attachment/content/1"
        assert jira_attachment.validate_attachment_url(att_url, jira_url) is True

    def test_default_https_port_normalized_reverse(self):
        """Host without port should match :443 on attachment URL."""
        jira_url = "https://jira.example.com"
        att_url = "https://jira.example.com:443/rest/api/2/attachment/content/1"
        assert jira_attachment.validate_attachment_url(att_url, jira_url) is True

    def test_default_http_port_normalized(self):
        """Default port :80 on HTTP should match host without port."""
        jira_url = "http://jira.example.com:80"
        att_url = "http://jira.example.com/rest/api/2/attachment/content/1"
        assert jira_attachment.validate_attachment_url(att_url, jira_url) is True


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: Path traversal protection — validate_output_path()
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidateOutputPath:
    """Output path must be validated against path traversal attacks."""

    def test_simple_filename_accepted(self, tmp_path):
        """Simple filename in cwd should be accepted."""
        result = jira_attachment.validate_output_path("report.pdf", str(tmp_path))
        assert result is not None

    def test_subdirectory_accepted(self, tmp_path):
        sub = tmp_path / "downloads"
        sub.mkdir()
        result = jira_attachment.validate_output_path(
            str(sub / "report.pdf"), str(tmp_path)
        )
        assert result is not None

    def test_traversal_rejected(self, tmp_path):
        """Path traversal via ../ must be rejected."""
        result = jira_attachment.validate_output_path(
            "../../etc/cron.d/evil", str(tmp_path)
        )
        assert result is None

    def test_absolute_path_outside_cwd_rejected(self, tmp_path):
        """Absolute path outside working directory must be rejected."""
        result = jira_attachment.validate_output_path("/tmp/evil", str(tmp_path))
        assert result is None

    def test_sibling_directory_prefix_bypass_rejected(self, tmp_path):
        """Sibling directory whose name starts with cwd name must be rejected.

        Regression test: str.startswith() is vulnerable when work="/a/work" and
        output resolves to "/a/work-evil/payload" because
        "/a/work-evil/payload".startswith("/a/work") == True.
        Path.relative_to() correctly rejects this.
        """
        # Create sibling directory whose name is a prefix extension of tmp_path
        sibling = tmp_path.parent / (tmp_path.name + "-evil")
        sibling.mkdir(exist_ok=True)
        payload = sibling / "payload.txt"
        payload.touch()

        # The output path resolves to sibling dir — must be rejected
        result = jira_attachment.validate_output_path(
            str(payload), str(tmp_path)
        )
        assert result is None
