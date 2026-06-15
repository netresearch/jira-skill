"""Tests for jira-attachment.py security controls (SSRF, Path Traversal, TLS)."""

import importlib.util
import sys
from pathlib import Path
from unittest import mock

import click.testing
import pytest

# Add scripts to path for lib imports
_test_dir = Path(__file__).parent
_scripts_path = _test_dir.parent / "skills" / "jira-communication" / "scripts"
sys.path.insert(0, str(_scripts_path))

import lib.client as _lib_client

# Import jira-attachment.py (hyphenated filename requires importlib)
_core_path = _scripts_path / "core"
_spec = importlib.util.spec_from_file_location("jira_attachment", _core_path / "jira-attachment.py")
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
        result = jira_attachment.validate_output_path(str(sub / "report.pdf"), str(tmp_path))
        assert result is not None

    def test_traversal_rejected(self, tmp_path):
        """Path traversal via ../ must be rejected."""
        result = jira_attachment.validate_output_path("../../etc/cron.d/evil", str(tmp_path))
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
        result = jira_attachment.validate_output_path(str(payload), str(tmp_path))
        assert result is None


class TestAttachmentUploadMimeType:
    def test_add_sets_mime_type_and_timeout(self, tmp_path):
        fpath = tmp_path / "report.pdf"
        fpath.write_bytes(b"%PDF-1.4\n")

        mc = mock.Mock()
        mc.url = "https://jira.example.com"
        mc.with_context = mock.Mock()

        response = mock.Mock()
        response.raise_for_status = mock.Mock()
        response.json.return_value = [{"id": "123"}]
        mc._session.post.return_value = response

        runner = click.testing.CliRunner()
        with mock.patch.object(jira_attachment, "LazyJiraClient", return_value=mc):
            result = runner.invoke(jira_attachment.cli, ["--json", "add", "TEST-1", str(fpath)])
        assert result.exit_code == 0, result.output

        mc._session.post.assert_called_once()
        _, kwargs = mc._session.post.call_args
        files = kwargs["files"]
        assert "file" in files
        name, _fh, mime = files["file"]
        assert name == "report.pdf"
        assert mime == "application/pdf"
        assert kwargs.get("timeout") == jira_attachment.UPLOAD_TIMEOUT
        assert kwargs.get("headers", {}).get("X-Atlassian-Token") == "nocheck"

    def test_add_falls_back_to_octet_stream(self, tmp_path):
        fpath = tmp_path / "blob.unknownext"
        fpath.write_bytes(b"data")

        mc = mock.Mock()
        mc.url = "https://jira.example.com"
        mc.with_context = mock.Mock()

        response = mock.Mock()
        response.raise_for_status = mock.Mock()
        response.json.return_value = [{"id": "123"}]
        mc._session.post.return_value = response

        runner = click.testing.CliRunner()
        with mock.patch.object(jira_attachment, "LazyJiraClient", return_value=mc):
            result = runner.invoke(jira_attachment.cli, ["--json", "add", "TEST-1", str(fpath)])
        assert result.exit_code == 0, result.output

        _, kwargs = mc._session.post.call_args
        _name, _fh, mime = kwargs["files"]["file"]
        assert mime == "application/octet-stream"


# ═══════════════════════════════════════════════════════════════════════════════
# Shared helpers for response-level tests
# ═══════════════════════════════════════════════════════════════════════════════


_FAKE_CONFIG = {
    "JIRA_URL": "https://jira.example.com",
    "JIRA_USERNAME": "user@example.com",
    "JIRA_API_TOKEN": "fake-token",
}

_JIRA_URL = "https://jira.example.com"


def _make_mock_response(
    content_type: str,
    body: bytes = b"data",
    status_code: int = 200,
    content_disposition: str = "",
):
    resp = mock.Mock()
    resp.status_code = status_code
    resp.url = "https://jira.example.com/rest/api/2/attachment/content/1"
    headers = {"Content-Type": content_type}
    if content_disposition:
        headers["Content-Disposition"] = content_disposition
    resp.headers = headers
    resp.raise_for_status = mock.Mock()
    resp.iter_content = mock.Mock(return_value=iter([body]))
    return resp


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: _handle_response helper - pure function, no CliRunner needed
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleResponse:
    """_handle_response must raise typed exceptions for session-expiry and CAPTCHA."""

    def test_html_without_attachment_disposition_raises(self):
        """200 text/html with no Content-Disposition must raise SessionExpiredError."""
        resp = _make_mock_response("text/html; charset=utf-8")
        with pytest.raises(_lib_client.SessionExpiredError):
            _lib_client._handle_response(resp, _JIRA_URL)

    def test_html_with_attachment_disposition_allowed(self):
        """200 text/html with Content-Disposition: attachment must pass (real HTML file)."""
        resp = _make_mock_response(
            "text/html; charset=utf-8",
            content_disposition='attachment; filename="page.html"',
        )
        _lib_client._handle_response(resp, _JIRA_URL)  # must not raise

    def test_non_html_allowed(self):
        """200 application/pdf must pass without raising."""
        resp = _make_mock_response("application/pdf")
        _lib_client._handle_response(resp, _JIRA_URL)  # must not raise

    def test_captcha_header_still_raises(self):
        """X-Authentication-Denied-Reason: CAPTCHA_CHALLENGE must raise CaptchaError."""
        resp = _make_mock_response("application/json")
        resp.headers["X-Authentication-Denied-Reason"] = "CAPTCHA_CHALLENGE"
        with pytest.raises(_lib_client.CaptchaError):
            _lib_client._handle_response(resp, _JIRA_URL)

    def test_non_200_html_not_session_expiry(self):
        """401 text/html must raise AuthenticationError, not SessionExpiredError.

        Directly proves authentication handling runs before the 200-only session-expiry guard.
        """
        resp = _make_mock_response("text/html; charset=utf-8", status_code=401)
        with pytest.raises(_lib_client.AuthenticationError):
            _lib_client._handle_response(resp, _JIRA_URL)

    def test_401_raises_authentication_error(self):
        """401 response without CAPTCHA header must raise AuthenticationError."""
        resp = _make_mock_response("application/json", status_code=401)
        with pytest.raises(_lib_client.AuthenticationError):
            _lib_client._handle_response(resp, _JIRA_URL)

    def test_403_raises_authentication_error(self):
        """403 response must raise AuthenticationError."""
        resp = _make_mock_response("application/json", status_code=403)
        with pytest.raises(_lib_client.AuthenticationError):
            _lib_client._handle_response(resp, _JIRA_URL)

    def test_captcha_on_401_raises_captcha_not_auth_error(self):
        """401 with CAPTCHA header must raise CaptchaError, not AuthenticationError.

        Validates that _check_captcha_challenge runs before _check_authentication
        so CAPTCHA-flavoured 401s are attributed to the more specific exception.
        """
        resp = _make_mock_response("text/html", status_code=401)
        resp.headers["X-Authentication-Denied-Reason"] = "CAPTCHA_CHALLENGE"
        with pytest.raises(_lib_client.CaptchaError):
            _lib_client._handle_response(resp, _JIRA_URL)


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: CLI-level regression - HTML responses rejected before writing to disk
# ═══════════════════════════════════════════════════════════════════════════════


class TestDownloadContentTypeGuard:
    """End-to-end CLI regression: HTML session-expiry pages must not be written to disk."""

    def _run_download(self, tmp_path, content_type, content_disposition=""):
        out_file = str(tmp_path / "out.bin")
        runner = click.testing.CliRunner()
        with (
            mock.patch.object(jira_attachment, "load_config", return_value=_FAKE_CONFIG),
            mock.patch.object(
                jira_attachment.requests,
                "get",
                return_value=_make_mock_response(content_type, b"fake", content_disposition=content_disposition),
            ),
            mock.patch.object(jira_attachment.Path, "cwd", return_value=tmp_path),
        ):
            result = runner.invoke(
                jira_attachment.cli,
                ["download", "https://jira.example.com/rest/api/2/attachment/content/1", out_file],
            )
        return result, tmp_path / "out.bin"

    def test_html_content_type_rejected(self, tmp_path):
        """text/html with no Content-Disposition must be rejected; file must not be written."""
        result, out = self._run_download(tmp_path, "text/html; charset=utf-8")
        assert result.exit_code != 0
        assert "HTML" in result.output
        assert not out.exists()

    def test_html_content_type_case_insensitive(self, tmp_path):
        """Content-Type header matching must be case-insensitive (Text/Html, TEXT/HTML)."""
        result, out = self._run_download(tmp_path, "Text/Html")
        assert result.exit_code != 0
        assert "HTML" in result.output
        assert not out.exists()

    def test_html_attachment_disposition_accepted(self, tmp_path):
        """text/html with Content-Disposition: attachment must be accepted (real HTML file)."""
        result, out = self._run_download(
            tmp_path, "text/html; charset=utf-8", content_disposition='attachment; filename="report.html"'
        )
        assert result.exit_code == 0, result.output
        assert out.exists()
        assert out.read_bytes() == b"fake"

    def test_valid_content_type_accepted(self, tmp_path):
        """application/pdf response must be accepted and the file written."""
        result, out = self._run_download(tmp_path, "application/pdf")
        assert result.exit_code == 0, result.output
        assert out.exists()
        assert out.read_bytes() == b"fake"


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: _build_auth helper
# ═══════════════════════════════════════════════════════════════════════════════


class TestBuildAuth:
    """Auth selection: PAT → Bearer header; Cloud → basic auth tuple."""

    def test_personal_token_uses_bearer_header(self):
        auth, headers = jira_attachment._build_auth(
            {"JIRA_URL": "https://jira.example.com", "JIRA_PERSONAL_TOKEN": "pat-123"}
        )
        assert auth is None
        assert headers == {"Authorization": "Bearer pat-123"}

    def test_cloud_uses_basic_auth(self):
        auth, headers = jira_attachment._build_auth(_FAKE_CONFIG)
        assert auth == ("user@example.com", "fake-token")
        assert headers == {}


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: download-all command
# ═══════════════════════════════════════════════════════════════════════════════


def _make_meta_response(attachments: list[dict]):
    """Mock issue-metadata response carrying fields.attachment."""
    resp = mock.Mock()
    resp.status_code = 200
    resp.url = "https://jira.example.com/rest/api/2/issue/TEST-1"
    resp.headers = {"Content-Type": "application/json"}
    resp.raise_for_status = mock.Mock()
    resp.json.return_value = {"fields": {"attachment": attachments}}
    return resp


def _att(att_id: str, filename: str, size: int = 4):
    return {
        "id": att_id,
        "filename": filename,
        "size": size,
        "content": f"https://jira.example.com/rest/api/2/attachment/content/{att_id}",
    }


class TestDownloadAll:
    """download-all fetches issue metadata then streams each attachment."""

    def _run(self, tmp_path, attachments, extra_args=None):
        runner = click.testing.CliRunner()

        def fake_get(url, *args, **kwargs):
            if "/rest/api/2/issue/" in url:
                return _make_meta_response(attachments)
            return _make_mock_response("application/octet-stream", b"data")

        with (
            mock.patch.object(jira_attachment, "load_config", return_value=_FAKE_CONFIG),
            mock.patch.object(jira_attachment.requests, "get", side_effect=fake_get),
            mock.patch.object(jira_attachment.Path, "cwd", return_value=tmp_path),
        ):
            result = runner.invoke(jira_attachment.cli, ["download-all", "TEST-1", *(extra_args or [])])
        return result

    def test_downloads_all_attachments(self, tmp_path):
        result = self._run(tmp_path, [_att("1", "a.pdf"), _att("2", "b.txt")])
        assert result.exit_code == 0, result.output
        assert (tmp_path / "a.pdf").read_bytes() == b"data"
        assert (tmp_path / "b.txt").read_bytes() == b"data"

    def test_no_attachments_is_success(self, tmp_path):
        result = self._run(tmp_path, [])
        assert result.exit_code == 0, result.output
        assert "No attachments" in result.output

    def test_dry_run_writes_nothing(self, tmp_path):
        result = self._run(tmp_path, [_att("1", "a.pdf")], extra_args=["--dry-run"])
        assert result.exit_code == 0, result.output
        assert "DRY RUN" in result.output
        assert not (tmp_path / "a.pdf").exists()

    def test_filename_path_components_stripped(self, tmp_path):
        """A Jira filename with path components must be saved by basename, never escape --dir."""
        result = self._run(tmp_path, [_att("1", "../../etc/passwd")])
        assert result.exit_code == 0, result.output
        assert (tmp_path / "passwd").exists()
        assert not (tmp_path.parent / "passwd").exists()

    def test_duplicate_filenames_disambiguated(self, tmp_path):
        """Two attachments with the same name must not overwrite each other."""
        result = self._run(tmp_path, [_att("1", "dup.txt"), _att("2", "dup.txt")])
        assert result.exit_code == 0, result.output
        assert (tmp_path / "dup.txt").exists()
        assert (tmp_path / "2_dup.txt").exists()

    def test_dir_outside_cwd_rejected(self, tmp_path):
        """--dir resolving outside cwd must be rejected (path traversal guard)."""
        result = self._run(tmp_path, [_att("1", "a.pdf")], extra_args=["--dir", "../escape"])
        assert result.exit_code != 0
        assert "escape" in result.output.lower()
