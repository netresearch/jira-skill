"""Tests for LazyJiraClient in client.py."""

import sys
from pathlib import Path
from unittest import mock

# Add scripts to path for lib imports
_test_dir = Path(__file__).parent
_scripts_path = _test_dir.parent / "skills" / "jira-communication" / "scripts"
sys.path.insert(0, str(_scripts_path))

from lib.client import (
    JIRA_TIMEOUT,
    LazyJiraClient,
    _check_captcha_challenge,
    _sanitize_error,
    get_jira_client,
    is_account_id,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Tests: is_account_id()
# ═══════════════════════════════════════════════════════════════════════════════

class TestIsAccountId:
    """is_account_id() must correctly identify Jira Cloud account IDs."""

    def test_cloud_account_id_with_colon(self):
        assert is_account_id('5b10ac8d:82e05b22cc7d4ef5') is True

    def test_atlassian_account_id_format(self):
        assert is_account_id('557058:d5765ebc-27de-4ce3-b520-a77a87e5e99a') is True

    def test_legacy_hex_account_id(self):
        assert is_account_id('5b10ac8d82e05b22cc7d4ef5') is True

    def test_legacy_hex_account_id_not_starting_with_5(self):
        """Legacy hex IDs may start with any hex char, not just '5'."""
        assert is_account_id('ab10ac8d82e05b22cc7d4ef5') is True

    def test_email_is_not_account_id(self):
        assert is_account_id('user@example.com') is False

    def test_username_is_not_account_id(self):
        assert is_account_id('john.doe') is False

    def test_empty_string_is_not_account_id(self):
        assert is_account_id('') is False


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: LazyJiraClient
# ═══════════════════════════════════════════════════════════════════════════════

class TestLazyJiraClient:
    """LazyJiraClient must defer client creation and pass issue_key/url context."""

    def test_defers_creation_until_first_access(self):
        """No Jira client is created until an attribute is accessed."""
        with mock.patch('lib.client.get_jira_client') as mock_get:
            LazyJiraClient(env_file='test.env')
            mock_get.assert_not_called()

    def test_creates_client_on_first_attribute_access(self):
        """Client is created when a Jira method is first accessed."""
        mock_client = mock.Mock()
        with mock.patch('lib.client.get_jira_client', return_value=mock_client) as mock_get:
            lazy = LazyJiraClient(env_file='test.env', profile='myprof')
            lazy.myself()
            mock_get.assert_called_once_with(
                env_file='test.env', profile='myprof', issue_key=None, url=None
            )

    def test_passes_issue_key_from_with_context(self):
        """issue_key set via with_context() is forwarded to get_jira_client."""
        mock_client = mock.Mock()
        with mock.patch('lib.client.get_jira_client', return_value=mock_client) as mock_get:
            lazy = LazyJiraClient(profile='default')
            lazy.with_context(issue_key='WEB-123')
            lazy.myself()
            mock_get.assert_called_once_with(
                env_file=None, profile='default', issue_key='WEB-123', url=None
            )

    def test_passes_url_from_with_context(self):
        """url set via with_context() is forwarded to get_jira_client."""
        mock_client = mock.Mock()
        with mock.patch('lib.client.get_jira_client', return_value=mock_client) as mock_get:
            lazy = LazyJiraClient()
            lazy.with_context(url='https://jira.example.com/browse/X-1')
            lazy.myself()
            mock_get.assert_called_once_with(
                env_file=None, profile=None, issue_key=None,
                url='https://jira.example.com/browse/X-1'
            )

    def test_url_as_issue_key_enables_host_resolution(self):
        """A full URL passed as issue_key also sets _url for host-based resolution."""
        mock_client = mock.Mock()
        with mock.patch('lib.client.get_jira_client', return_value=mock_client) as mock_get:
            lazy = LazyJiraClient()
            lazy.with_context(issue_key='https://jira.example.com/browse/WEB-99')
            lazy.myself()
            mock_get.assert_called_once_with(
                env_file=None, profile=None,
                issue_key='https://jira.example.com/browse/WEB-99',
                url='https://jira.example.com/browse/WEB-99'
            )

    def test_url_as_issue_key_does_not_override_explicit_url(self):
        """Explicit url parameter takes precedence over URL-like issue_key."""
        mock_client = mock.Mock()
        with mock.patch('lib.client.get_jira_client', return_value=mock_client) as mock_get:
            lazy = LazyJiraClient()
            lazy.with_context(
                issue_key='https://jira.a.com/browse/X-1',
                url='https://jira.b.com'
            )
            lazy.myself()
            mock_get.assert_called_once_with(
                env_file=None, profile=None,
                issue_key='https://jira.a.com/browse/X-1',
                url='https://jira.b.com'
            )

    def test_caches_client_after_first_access(self):
        """get_jira_client is called only once, subsequent accesses reuse the client."""
        mock_client = mock.Mock()
        with mock.patch('lib.client.get_jira_client', return_value=mock_client) as mock_get:
            lazy = LazyJiraClient()
            lazy.myself()
            lazy.issue('KEY-1')
            lazy.project('PROJ')
            mock_get.assert_called_once()

    def test_with_context_ignored_after_init(self):
        """with_context() has no effect after the client is already created."""
        mock_client = mock.Mock()
        with mock.patch('lib.client.get_jira_client', return_value=mock_client) as mock_get:
            lazy = LazyJiraClient()
            lazy.myself()  # Creates client
            lazy.with_context(issue_key='NEW-1')  # Should be ignored
            mock_get.assert_called_once_with(
                env_file=None, profile=None, issue_key=None, url=None
            )

    def test_propagates_exceptions(self):
        """Exceptions from get_jira_client propagate through attribute access."""
        with mock.patch('lib.client.get_jira_client', side_effect=ValueError("bad config")):
            lazy = LazyJiraClient()
            try:
                lazy.myself()
                raise AssertionError("Should have raised ValueError")
            except ValueError as e:
                assert "bad config" in str(e)

    def test_delegates_to_real_client(self):
        """Method calls and return values are delegated to the real client."""
        mock_client = mock.Mock()
        mock_client.myself.return_value = {'displayName': 'Test User'}
        with mock.patch('lib.client.get_jira_client', return_value=mock_client):
            lazy = LazyJiraClient()
            result = lazy.myself()
            assert result == {'displayName': 'Test User'}
            mock_client.myself.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: Timeout is set on Jira client (F2)
# ═══════════════════════════════════════════════════════════════════════════════

class TestJiraClientTimeout:
    """get_jira_client() must pass a timeout to the Jira constructor."""

    def test_timeout_constant_defined(self):
        """JIRA_TIMEOUT must be a positive number."""
        assert isinstance(JIRA_TIMEOUT, (int, float))
        assert JIRA_TIMEOUT > 0

    def test_timeout_passed_to_jira_constructor(self):
        """Jira() must be called with timeout=JIRA_TIMEOUT."""
        config = {
            'JIRA_URL': 'https://jira.example.com',
            'JIRA_PERSONAL_TOKEN': 'test-token',
        }
        with mock.patch('lib.client.load_config', return_value=config), \
             mock.patch('lib.client.Jira') as MockJira:
            MockJira.return_value = mock.Mock()
            MockJira.return_value._session = mock.Mock()
            get_jira_client()
            # Verify timeout was passed
            call_kwargs = MockJira.call_args[1]
            assert call_kwargs.get('timeout') == JIRA_TIMEOUT


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: Retry adapter is mounted (F13)
# ═══════════════════════════════════════════════════════════════════════════════

class TestJiraClientRetry:
    """get_jira_client() must mount a retry adapter for rate limiting."""

    def test_retry_adapter_mounted(self):
        """Session must have retry adapter for https:// URLs."""
        config = {
            'JIRA_URL': 'https://jira.example.com',
            'JIRA_PERSONAL_TOKEN': 'test-token',
        }
        with mock.patch('lib.client.load_config', return_value=config), \
             mock.patch('lib.client.Jira') as MockJira:
            mock_session = mock.Mock()
            MockJira.return_value = mock.Mock()
            MockJira.return_value._session = mock_session
            get_jira_client()
            # Verify mount was called for https:// and http://
            mount_calls = [c[0][0] for c in mock_session.mount.call_args_list]
            assert 'https://' in mount_calls
            assert 'http://' in mount_calls


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: CAPTCHA login_url validation (F5)
# ═══════════════════════════════════════════════════════════════════════════════

class TestCaptchaUrlValidation:
    """CAPTCHA login URL from headers must be validated against JIRA_URL host."""

    def _make_response(self, header_value):
        """Create a mock response with X-Authentication-Denied-Reason header."""
        resp = mock.Mock()
        resp.headers = {"X-Authentication-Denied-Reason": header_value}
        return resp

    def test_captcha_uses_header_url_when_host_matches(self):
        """Login URL from header should be used when it matches jira_url host."""
        resp = self._make_response(
            "CAPTCHA_CHALLENGE; login-url=https://jira.example.com/login.jsp"
        )
        try:
            _check_captcha_challenge(resp, "https://jira.example.com")
        except Exception as e:
            assert "jira.example.com/login.jsp" in str(e)

    def test_captcha_ignores_header_url_when_host_differs(self):
        """Login URL from header must be ignored when host doesn't match jira_url."""
        resp = self._make_response(
            "CAPTCHA_CHALLENGE; login-url=https://evil.com/phish"
        )
        try:
            _check_captcha_challenge(resp, "https://jira.example.com")
        except Exception as e:
            # Should fall back to constructed URL, not use evil.com
            assert "evil.com" not in str(e)
            assert "jira.example.com/login.jsp" in str(e)

    def test_captcha_no_header_url_uses_default(self):
        """When no login-url in header, use default jira_url/login.jsp."""
        resp = self._make_response("CAPTCHA_CHALLENGE")
        try:
            _check_captcha_challenge(resp, "https://jira.example.com")
        except Exception as e:
            assert "jira.example.com/login.jsp" in str(e)


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: _sanitize_error() credential redaction (F7)
# ═══════════════════════════════════════════════════════════════════════════════

class TestSanitizeError:
    """_sanitize_error() must redact credential values from error messages."""

    def test_redacts_bearer_token(self):
        result = _sanitize_error("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9")
        assert "eyJhbGciOiJIUzI1NiJ9" not in result
        assert "***" in result

    def test_redacts_basic_auth(self):
        result = _sanitize_error("Basic dXNlcjpwYXNz")
        assert "dXNlcjpwYXNz" not in result
        assert "***" in result

    def test_redacts_token_param(self):
        result = _sanitize_error("failed: token=secret123 is invalid")
        assert "secret123" not in result
        assert "***" in result

    def test_preserves_safe_messages(self):
        msg = "Connection refused: host unreachable"
        assert _sanitize_error(msg) == msg

    def test_redacts_password_param(self):
        result = _sanitize_error("password=hunter2")
        assert "hunter2" not in result
        assert "***" in result
