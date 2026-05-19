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
    get_project_issue_types,
    is_account_id,
    resolve_assignee,
    resolve_status,
    resolve_subtask_type,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Tests: is_account_id()
# ═══════════════════════════════════════════════════════════════════════════════


class TestIsAccountId:
    """is_account_id() must correctly identify Jira Cloud account IDs."""

    def test_cloud_account_id_with_colon(self):
        assert is_account_id("5b10ac8d:82e05b22cc7d4ef5") is True

    def test_atlassian_account_id_format(self):
        assert is_account_id("557058:d5765ebc-27de-4ce3-b520-a77a87e5e99a") is True

    def test_legacy_hex_account_id(self):
        assert is_account_id("5b10ac8d82e05b22cc7d4ef5") is True

    def test_legacy_hex_account_id_not_starting_with_5(self):
        """Legacy hex IDs may start with any hex char, not just '5'."""
        assert is_account_id("ab10ac8d82e05b22cc7d4ef5") is True

    def test_email_is_not_account_id(self):
        assert is_account_id("user@example.com") is False

    def test_username_is_not_account_id(self):
        assert is_account_id("john.doe") is False

    def test_empty_string_is_not_account_id(self):
        assert is_account_id("") is False


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: LazyJiraClient
# ═══════════════════════════════════════════════════════════════════════════════


class TestLazyJiraClient:
    """LazyJiraClient must defer client creation and pass issue_key/url context."""

    def test_defers_creation_until_first_access(self):
        """No Jira client is created until an attribute is accessed."""
        with mock.patch("lib.client.get_jira_client") as mock_get:
            LazyJiraClient(env_file="test.env")
            mock_get.assert_not_called()

    def test_creates_client_on_first_attribute_access(self):
        """Client is created when a Jira method is first accessed."""
        mock_client = mock.Mock()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client) as mock_get:
            lazy = LazyJiraClient(env_file="test.env", profile="myprof")
            lazy.myself()
            mock_get.assert_called_once_with(env_file="test.env", profile="myprof", issue_key=None, url=None)

    def test_passes_issue_key_from_with_context(self):
        """issue_key set via with_context() is forwarded to get_jira_client."""
        mock_client = mock.Mock()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client) as mock_get:
            lazy = LazyJiraClient(profile="default")
            lazy.with_context(issue_key="WEB-123")
            lazy.myself()
            mock_get.assert_called_once_with(env_file=None, profile="default", issue_key="WEB-123", url=None)

    def test_passes_url_from_with_context(self):
        """url set via with_context() is forwarded to get_jira_client."""
        mock_client = mock.Mock()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client) as mock_get:
            lazy = LazyJiraClient()
            lazy.with_context(url="https://jira.example.com/browse/X-1")
            lazy.myself()
            mock_get.assert_called_once_with(
                env_file=None, profile=None, issue_key=None, url="https://jira.example.com/browse/X-1"
            )

    def test_url_as_issue_key_enables_host_resolution(self):
        """A full URL passed as issue_key also sets _url for host-based resolution."""
        mock_client = mock.Mock()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client) as mock_get:
            lazy = LazyJiraClient()
            lazy.with_context(issue_key="https://jira.example.com/browse/WEB-99")
            lazy.myself()
            mock_get.assert_called_once_with(
                env_file=None,
                profile=None,
                issue_key="https://jira.example.com/browse/WEB-99",
                url="https://jira.example.com/browse/WEB-99",
            )

    def test_url_as_issue_key_does_not_override_explicit_url(self):
        """Explicit url parameter takes precedence over URL-like issue_key."""
        mock_client = mock.Mock()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client) as mock_get:
            lazy = LazyJiraClient()
            lazy.with_context(issue_key="https://jira.a.com/browse/X-1", url="https://jira.b.com")
            lazy.myself()
            mock_get.assert_called_once_with(
                env_file=None, profile=None, issue_key="https://jira.a.com/browse/X-1", url="https://jira.b.com"
            )

    def test_caches_client_after_first_access(self):
        """get_jira_client is called only once, subsequent accesses reuse the client."""
        mock_client = mock.Mock()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client) as mock_get:
            lazy = LazyJiraClient()
            lazy.myself()
            lazy.issue("KEY-1")
            lazy.project("PROJ")
            mock_get.assert_called_once()

    def test_with_context_ignored_after_init(self):
        """with_context() has no effect after the client is already created."""
        mock_client = mock.Mock()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client) as mock_get:
            lazy = LazyJiraClient()
            lazy.myself()  # Creates client
            lazy.with_context(issue_key="NEW-1")  # Should be ignored
            mock_get.assert_called_once_with(env_file=None, profile=None, issue_key=None, url=None)

    def test_propagates_exceptions(self):
        """Exceptions from get_jira_client propagate through attribute access."""
        with mock.patch("lib.client.get_jira_client", side_effect=ValueError("bad config")):
            lazy = LazyJiraClient()
            try:
                lazy.myself()
                raise AssertionError("Should have raised ValueError")
            except ValueError as e:
                assert "bad config" in str(e)

    def test_delegates_to_real_client(self):
        """Method calls and return values are delegated to the real client."""
        mock_client = mock.Mock()
        mock_client.myself.return_value = {"displayName": "Test User"}
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            lazy = LazyJiraClient()
            result = lazy.myself()
            assert result == {"displayName": "Test User"}
            mock_client.myself.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: LazyJiraClient.jql() override for Cloud (CHANGE-2046)
# ═══════════════════════════════════════════════════════════════════════════════


class TestLazyJiraClientJqlOverride:
    """jql() must route Cloud calls to /rest/api/3/search/jql and delegate on Server/DC."""

    SERVER_URL = "https://jira.example.com"
    CLOUD_URL = "https://acme.atlassian.net"

    def _make_lazy(self, *, cloud: bool, pages: list[dict] | None = None):
        """Build a LazyJiraClient backed by a mock client.

        Cloud detection in the override uses ``is_cloud_url(client.url)``,
        so we set ``client.url`` rather than ``client.cloud``.

        If *pages* is provided it becomes the ``client.get`` side-effect, one
        response per cursor request. Otherwise ``client.get`` returns a single
        empty page (``isLast=True``).
        """
        mock_client = mock.Mock()
        mock_client.url = self.CLOUD_URL if cloud else self.SERVER_URL
        if pages is None:
            mock_client.get.return_value = {"issues": [], "isLast": True}
        else:
            mock_client.get.side_effect = pages
        mock_client.jql.return_value = {"issues": [], "total": 0}
        patcher = mock.patch("lib.client.get_jira_client", return_value=mock_client)
        patcher.start()
        return LazyJiraClient(), mock_client, patcher

    def test_server_path_delegates_to_library_jql(self):
        """On Server/DC the library's jql() is called with the same arguments."""
        lazy, mock_client, patcher = self._make_lazy(cloud=False)
        try:
            lazy.jql("project = FOO", limit=25, start=10, fields="summary,status")
            mock_client.jql.assert_called_once_with("project = FOO", fields="summary,status", start=10, limit=25)
            mock_client.get.assert_not_called()
        finally:
            patcher.stop()

    def test_cloud_path_calls_new_search_jql_endpoint(self):
        """On Cloud the new /rest/api/3/search/jql endpoint is called with cursor-style params."""
        lazy, mock_client, patcher = self._make_lazy(
            cloud=True,
            pages=[{"issues": [{"key": "X-1"}], "isLast": True}],
        )
        try:
            lazy.jql("project = FOO", limit=25, start=0, fields="summary")
            mock_client.get.assert_called_once_with(
                "rest/api/3/search/jql",
                params={"jql": "project = FOO", "maxResults": 25, "fields": "summary"},
            )
            mock_client.jql.assert_not_called()
        finally:
            patcher.stop()

    def test_cloud_path_defaults_fields_to_all(self):
        """fields=None on Cloud defaults to '*all'."""
        lazy, mock_client, patcher = self._make_lazy(cloud=True)
        try:
            lazy.jql("KEY = X-1")
            params = mock_client.get.call_args.kwargs["params"]
            assert params["fields"] == "*all"
        finally:
            patcher.stop()

    def test_cloud_path_joins_list_fields(self):
        """fields as a list/tuple/set is joined with commas."""
        lazy, mock_client, patcher = self._make_lazy(cloud=True)
        try:
            lazy.jql("KEY = X-1", fields=["key", "summary"])
            params = mock_client.get.call_args.kwargs["params"]
            assert params["fields"] == "key,summary"
        finally:
            patcher.stop()

    def test_cloud_path_forwards_expand(self):
        """expand kwarg is forwarded to the new endpoint when non-None."""
        lazy, mock_client, patcher = self._make_lazy(cloud=True)
        try:
            lazy.jql("KEY = X-1", expand="changelog")
            params = mock_client.get.call_args.kwargs["params"]
            assert params["expand"] == "changelog"
        finally:
            patcher.stop()

    def test_cloud_path_returns_synthesized_shape_when_get_returns_none(self):
        """Defensive: client.get() returning None yields an empty offset-style result."""
        lazy, mock_client, patcher = self._make_lazy(cloud=True)
        try:
            mock_client.get.return_value = None
            result = lazy.jql("KEY = X-1", limit=10, start=0)
            assert result == {"issues": [], "startAt": 0, "maxResults": 10, "total": 0, "isLast": True}
        finally:
            patcher.stop()

    def test_cloud_drains_multiple_pages_via_next_page_token(self):
        """When isLast=False the override fetches further pages until the window is filled."""
        lazy, mock_client, patcher = self._make_lazy(
            cloud=True,
            pages=[
                {"issues": [{"key": f"X-{i}"} for i in range(50)], "isLast": False, "nextPageToken": "tok-1"},
                {"issues": [{"key": f"X-{i}"} for i in range(50, 100)], "isLast": True},
            ],
        )
        try:
            result = lazy.jql("project = FOO", limit=100, start=0)
            assert mock_client.get.call_count == 2
            second_call_params = mock_client.get.call_args_list[1].kwargs["params"]
            assert second_call_params["nextPageToken"] == "tok-1"
            assert len(result["issues"]) == 100
            assert result["total"] == 100  # accurate when isLast=True
            assert result["isLast"] is True
        finally:
            patcher.stop()

    def test_cloud_synthesizes_sentinel_total_when_more_pages_exist(self):
        """When the drain stops at the window with isLast=False, total signals 'more exist'."""
        lazy, mock_client, patcher = self._make_lazy(
            cloud=True,
            pages=[
                {
                    "issues": [{"key": f"X-{i}"} for i in range(50)],
                    "isLast": False,
                    "nextPageToken": "tok-1",
                },
            ],
        )
        try:
            result = lazy.jql("project = FOO", limit=50, start=0)
            assert len(result["issues"]) == 50
            # Sentinel: start + len(sliced) + 1 → 0 + 50 + 1 = 51
            assert result["total"] == 51
            assert result["isLast"] is False
        finally:
            patcher.stop()

    def test_cloud_slices_window_with_start_offset(self):
        """start>0 returns the [start:start+limit] slice from the drained pages."""
        lazy, mock_client, patcher = self._make_lazy(
            cloud=True,
            pages=[
                {"issues": [{"key": f"X-{i}"} for i in range(50)], "isLast": False, "nextPageToken": "tok-1"},
                {"issues": [{"key": f"X-{i}"} for i in range(50, 100)], "isLast": True},
            ],
        )
        try:
            result = lazy.jql("project = FOO", limit=25, start=50)
            assert mock_client.get.call_count == 2
            keys = [i["key"] for i in result["issues"]]
            assert keys == [f"X-{i}" for i in range(50, 75)]
            assert result["startAt"] == 50
            assert result["total"] == 100
        finally:
            patcher.stop()

    def test_cloud_pagination_loop_terminates_on_caller_total_check(self):
        """The synthesized total lets a startAt/total paginating caller terminate cleanly."""
        # Simulates jira-worklog-query.py's loop against a 75-issue result set.
        # Iter 1 (start=0, limit=50) drains 1 page to fill the window. Iter 2
        # (start=50, limit=50) replays from cursor start — needs page 1 + page 2.
        page1 = {"issues": [{"key": f"X-{i}"} for i in range(50)], "isLast": False, "nextPageToken": "p1"}
        page2 = {"issues": [{"key": f"X-{i}"} for i in range(50, 75)], "isLast": True}
        lazy, mock_client, patcher = self._make_lazy(cloud=True, pages=[page1, page1, page2])
        try:
            collected, start_at = [], 0
            for _ in range(5):  # safety bound; real loop terminates earlier
                result = lazy.jql("project = FOO", limit=50, start=start_at)
                issues = result["issues"]
                if not issues:
                    break
                collected.extend(issues)
                start_at += len(issues)
                if start_at >= result["total"]:
                    break
            assert len(collected) == 75
            # Iter 1: 1 cursor call. Iter 2: 2 cursor calls (replays from cursor=None).
            assert mock_client.get.call_count == 3
        finally:
            patcher.stop()

    def test_cloud_error_carries_endpoint_hint_on_modern_python(self):
        """On Python 3.11+ a failing client.get() gets an add_note with the Cloud endpoint hint."""
        from requests.exceptions import HTTPError

        lazy, mock_client, patcher = self._make_lazy(cloud=True)
        try:
            mock_client.get.side_effect = HTTPError("410 Gone")
            try:
                lazy.jql("project = FOO")
            except HTTPError as exc:
                if hasattr(exc, "__notes__"):  # Python 3.11+
                    assert any("rest/api/3/search/jql" in n for n in exc.__notes__)
                    assert any("CHANGE-2046" in n for n in exc.__notes__)
            else:
                raise AssertionError("expected HTTPError to propagate")
        finally:
            patcher.stop()

    def test_jql_triggers_lazy_creation(self):
        """Calling jql() before any other attribute still initialises the client."""
        mock_client = mock.Mock()
        mock_client.url = "https://jira.example.com"  # Server/DC
        mock_client.jql.return_value = {"issues": []}
        with mock.patch("lib.client.get_jira_client", return_value=mock_client) as mock_get:
            lazy = LazyJiraClient(env_file="x.env", profile="p")
            lazy.jql("project = FOO")
            mock_get.assert_called_once_with(env_file="x.env", profile="p", issue_key=None, url=None)

    def test_missing_url_attr_treated_as_server(self):
        """A client without a parseable URL falls back to Server/DC (library jql()) — fail-closed."""
        mock_client = mock.Mock()
        mock_client.url = None  # is_cloud_url("") → False
        mock_client.jql.return_value = {"issues": []}
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            lazy = LazyJiraClient()
            lazy.jql("project = FOO")
            mock_client.jql.assert_called_once()


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
            "JIRA_URL": "https://jira.example.com",
            "JIRA_PERSONAL_TOKEN": "test-token",
        }
        with mock.patch("lib.client.load_config", return_value=config), mock.patch("lib.client.Jira") as MockJira:
            MockJira.return_value = mock.Mock()
            MockJira.return_value._session = mock.Mock()
            get_jira_client()
            # Verify timeout was passed
            call_kwargs = MockJira.call_args[1]
            assert call_kwargs.get("timeout") == JIRA_TIMEOUT


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: Retry adapter is mounted (F13)
# ═══════════════════════════════════════════════════════════════════════════════


class TestJiraClientRetry:
    """get_jira_client() must mount a retry adapter for rate limiting."""

    def test_retry_adapter_mounted(self):
        """Session must have retry adapter for https:// URLs."""
        config = {
            "JIRA_URL": "https://jira.example.com",
            "JIRA_PERSONAL_TOKEN": "test-token",
        }
        with mock.patch("lib.client.load_config", return_value=config), mock.patch("lib.client.Jira") as MockJira:
            mock_session = mock.Mock()
            MockJira.return_value = mock.Mock()
            MockJira.return_value._session = mock_session
            get_jira_client()
            # Verify mount was called for https:// and http://
            mount_calls = [c[0][0] for c in mock_session.mount.call_args_list]
            assert "https://" in mount_calls
            assert "http://" in mount_calls


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
        resp = self._make_response("CAPTCHA_CHALLENGE; login-url=https://jira.example.com/login.jsp")
        try:
            _check_captcha_challenge(resp, "https://jira.example.com")
        except Exception as e:
            assert "jira.example.com/login.jsp" in str(e)

    def test_captcha_ignores_header_url_when_host_differs(self):
        """Login URL from header must be ignored when host doesn't match jira_url."""
        resp = self._make_response("CAPTCHA_CHALLENGE; login-url=https://evil.com/phish")
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


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: resolve_assignee()
# ═══════════════════════════════════════════════════════════════════════════════


class TestResolveAssignee:
    """resolve_assignee() must handle 'me', account IDs, and user search."""

    def test_me_returns_account_id_on_cloud(self):
        """'me' resolves to accountId from client.myself() on Cloud."""
        mock_client = mock.Mock()
        mock_client.myself.return_value = {
            "accountId": "557058:abc-123",
            "displayName": "Test User",
        }
        result = resolve_assignee(mock_client, "me")
        assert result == {"accountId": "557058:abc-123"}
        mock_client.myself.assert_called_once()

    def test_me_returns_name_on_server(self):
        """'me' resolves to name from client.myself() on Server/DC (no accountId)."""
        mock_client = mock.Mock()
        mock_client.myself.return_value = {
            "name": "john.doe",
            "key": "john.doe",
            "displayName": "John Doe",
        }
        result = resolve_assignee(mock_client, "me")
        assert result == {"name": "john.doe"}
        mock_client.myself.assert_called_once()

    def test_me_case_insensitive(self):
        """'ME', 'Me', 'mE' all resolve as 'me'."""
        mock_client = mock.Mock()
        mock_client.myself.return_value = {"accountId": "abc:123"}
        for variant in ("ME", "Me", "mE"):
            result = resolve_assignee(mock_client, variant)
            assert "accountId" in result

    def test_account_id_passed_through(self):
        """Account IDs are returned directly without API calls."""
        mock_client = mock.Mock()
        result = resolve_assignee(mock_client, "557058:d5765ebc-27de-4ce3-b520-a77a87e5e99a")
        assert result == {"accountId": "557058:d5765ebc-27de-4ce3-b520-a77a87e5e99a"}
        mock_client.myself.assert_not_called()
        mock_client.user_find_by_user_string.assert_not_called()

    def test_username_searched_and_resolved_cloud(self):
        """Non-me, non-account-ID strings are searched via user_find_by_user_string."""
        mock_client = mock.Mock()
        mock_client.user_find_by_user_string.return_value = [
            {"accountId": "found:user-id", "displayName": "Found User"}
        ]
        result = resolve_assignee(mock_client, "found.user")
        assert result == {"accountId": "found:user-id"}

    def test_username_searched_and_resolved_server(self):
        """Server/DC user without accountId returns name."""
        mock_client = mock.Mock()
        mock_client.user_find_by_user_string.return_value = [{"name": "jdoe", "key": "jdoe", "displayName": "J Doe"}]
        result = resolve_assignee(mock_client, "jdoe")
        assert result == {"name": "jdoe"}

    def test_user_not_found_returns_raw_name(self):
        """When user search returns empty, fall back to raw identifier."""
        mock_client = mock.Mock()
        mock_client.user_find_by_user_string.return_value = []
        result = resolve_assignee(mock_client, "unknown.user")
        assert result == {"name": "unknown.user"}

    def test_user_search_returns_string_fallback(self):
        """Server/DC may return a string instead of list — fall back to name."""
        mock_client = mock.Mock()
        mock_client.user_find_by_user_string.return_value = "some-string"
        result = resolve_assignee(mock_client, "some.user")
        assert result == {"name": "some.user"}


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: get_project_issue_types() and resolve_subtask_type()
# ═══════════════════════════════════════════════════════════════════════════════

# Sample issue types returned by Jira API for a project
SAMPLE_ISSUE_TYPES = [
    {"id": "1", "name": "Bug", "subtask": False},
    {"id": "2", "name": "Task", "subtask": False},
    {"id": "3", "name": "Story", "subtask": False},
    {"id": "4", "name": "Sub: Task", "subtask": True},
    {"id": "5", "name": "Sub: Bug", "subtask": True},
    {"id": "6", "name": "Epic", "subtask": False},
]

# Alternative: instance where subtask types use different naming
SAMPLE_ISSUE_TYPES_ALT = [
    {"id": "1", "name": "Bug", "subtask": False},
    {"id": "2", "name": "Task", "subtask": False},
    {"id": "10", "name": "Sub-task", "subtask": True},
    {"id": "11", "name": "Technical Sub-task", "subtask": True},
]


def _mock_client_with_types(issue_types):
    """Helper: create a mock client that returns given issue types."""
    mock_client = mock.Mock()
    mock_client.project.return_value = {"issueTypes": issue_types}
    return mock_client


class TestGetProjectIssueTypes:
    """get_project_issue_types() must return issue types from API."""

    def test_returns_issue_types_from_project(self):
        client = _mock_client_with_types(SAMPLE_ISSUE_TYPES)
        result = get_project_issue_types(client, "PROJ")
        assert len(result) == 6
        assert result[0]["name"] == "Bug"
        client.project.assert_called_once_with("PROJ", expand="issueTypes")

    def test_filters_subtask_types(self):
        client = _mock_client_with_types(SAMPLE_ISSUE_TYPES)
        result = get_project_issue_types(client, "PROJ", subtask_only=True)
        assert len(result) == 2
        assert all(t["subtask"] for t in result)

    def test_filters_non_subtask_types(self):
        client = _mock_client_with_types(SAMPLE_ISSUE_TYPES)
        result = get_project_issue_types(client, "PROJ", subtask_only=False)
        assert len(result) == 4
        assert not any(t["subtask"] for t in result)

    def test_empty_issue_types(self):
        """Handles project with no issueTypes key gracefully."""
        mock_client = mock.Mock()
        mock_client.project.return_value = {}
        result = get_project_issue_types(mock_client, "PROJ")
        assert result == []


class TestResolveSubtaskType:
    """resolve_subtask_type() must find the correct subtask type from API."""

    def test_exact_match_subtask(self):
        """Exact name match among subtask types returns that type."""
        client = _mock_client_with_types(SAMPLE_ISSUE_TYPES)
        result = resolve_subtask_type(client, "PROJ", "Sub: Task")
        assert result == "Sub: Task"

    def test_case_insensitive_match(self):
        """Matching is case-insensitive."""
        client = _mock_client_with_types(SAMPLE_ISSUE_TYPES)
        result = resolve_subtask_type(client, "PROJ", "sub: task")
        assert result == "Sub: Task"

    def test_non_subtask_name_resolved_to_subtask(self):
        """'Task' with --parent resolves to 'Sub: Task' if that subtask contains 'Task'."""
        client = _mock_client_with_types(SAMPLE_ISSUE_TYPES)
        result = resolve_subtask_type(client, "PROJ", "Task")
        assert result == "Sub: Task"

    def test_bug_resolved_to_sub_bug(self):
        """'Bug' with --parent resolves to 'Sub: Bug'."""
        client = _mock_client_with_types(SAMPLE_ISSUE_TYPES)
        result = resolve_subtask_type(client, "PROJ", "Bug")
        assert result == "Sub: Bug"

    def test_subtask_keyword_resolved(self):
        """'Subtask' or 'Sub-task' resolves to first available subtask type."""
        client = _mock_client_with_types(SAMPLE_ISSUE_TYPES)
        result = resolve_subtask_type(client, "PROJ", "Subtask")
        assert result in ("Sub: Task", "Sub: Bug")

    def test_different_naming_convention(self):
        """Works with instances that name subtasks differently."""
        client = _mock_client_with_types(SAMPLE_ISSUE_TYPES_ALT)
        result = resolve_subtask_type(client, "PROJ", "Sub-task")
        assert result == "Sub-task"

    def test_only_one_subtask_type_returns_it(self):
        """When only one subtask type exists and no match, return it."""
        client = _mock_client_with_types(
            [
                {"id": "1", "name": "Task", "subtask": False},
                {"id": "2", "name": "Teilaufgabe", "subtask": True},
            ]
        )
        result = resolve_subtask_type(client, "PROJ", "Task")
        assert result == "Teilaufgabe"

    def test_no_subtask_types_returns_none(self):
        """When project has no subtask types, returns None."""
        client = _mock_client_with_types(
            [
                {"id": "1", "name": "Task", "subtask": False},
                {"id": "2", "name": "Bug", "subtask": False},
            ]
        )
        result = resolve_subtask_type(client, "PROJ", "Task")
        assert result is None

    def test_no_match_multiple_subtask_types_returns_none(self):
        """No match + multiple subtask types → None (ambiguous)."""
        client = _mock_client_with_types(SAMPLE_ISSUE_TYPES)
        result = resolve_subtask_type(client, "PROJ", "Epic")
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: resolve_status()
# ═══════════════════════════════════════════════════════════════════════════════


SAMPLE_STATUSES = [
    {"id": "1", "name": "Open", "statusCategory": {"key": "new"}},
    {"id": "2", "name": "In Progress", "statusCategory": {"key": "indeterminate"}},
    {"id": "3", "name": "In Review", "statusCategory": {"key": "indeterminate"}},
    {"id": "4", "name": "Code Review", "statusCategory": {"key": "indeterminate"}},
    {"id": "5", "name": "Done", "statusCategory": {"key": "done"}},
    # Duplicate name (same status used in multiple workflows) — must be deduped
    {"id": "6", "name": "Open", "statusCategory": {"key": "new"}},
]


def _mock_client_with_statuses(statuses):
    """Helper: mock client whose .get('rest/api/2/status') returns statuses."""
    mock_client = mock.Mock()
    mock_client.get.return_value = statuses
    return mock_client


class TestResolveStatus:
    """resolve_status() must return canonical status name or raise ValueError."""

    def test_exact_match_case_insensitive(self):
        client = _mock_client_with_statuses(SAMPLE_STATUSES)
        assert resolve_status(client, "in progress") == "In Progress"

    def test_exact_match_preserves_canonical_casing(self):
        client = _mock_client_with_statuses(SAMPLE_STATUSES)
        assert resolve_status(client, "DONE") == "Done"

    def test_substring_match_unambiguous(self):
        """'Progress' matches only 'In Progress'."""
        client = _mock_client_with_statuses(SAMPLE_STATUSES)
        assert resolve_status(client, "Progress") == "In Progress"

    def test_substring_match_ambiguous_raises(self):
        """'review' substring matches both 'In Review' and 'Code Review'."""
        client = _mock_client_with_statuses(SAMPLE_STATUSES)
        try:
            resolve_status(client, "review")
        except ValueError as e:
            msg = str(e)
            assert "ambiguous" in msg.lower()
            assert "In Review" in msg
            assert "Code Review" in msg
        else:
            raise AssertionError("expected ValueError for ambiguous match")

    def test_no_match_raises_with_candidates(self):
        client = _mock_client_with_statuses(SAMPLE_STATUSES)
        try:
            resolve_status(client, "Closed")
        except ValueError as e:
            msg = str(e)
            assert "Closed" in msg
            # Candidates listed
            assert "Open" in msg and "Done" in msg
        else:
            raise AssertionError("expected ValueError for no match")

    def test_duplicate_names_deduplicated(self):
        """Same status name from multiple workflows must resolve cleanly."""
        client = _mock_client_with_statuses(SAMPLE_STATUSES)
        assert resolve_status(client, "Open") == "Open"

    def test_empty_status_list_raises(self):
        client = _mock_client_with_statuses([])
        try:
            resolve_status(client, "Open")
        except ValueError as e:
            assert "No statuses" in str(e) or "no statuses" in str(e).lower()
        else:
            raise AssertionError("expected ValueError for empty list")

    def test_api_returns_none_treated_as_empty(self):
        client = _mock_client_with_statuses(None)
        try:
            resolve_status(client, "Open")
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError when API returns None")
