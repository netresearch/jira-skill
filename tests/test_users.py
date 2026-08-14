"""Tests for lib.users (mention verification) and the shared CLI mention gate."""

from unittest import mock

import pytest
from conftest import load_script, make_mock_client, run_cli
from lib.client import AuthenticationError, resolve_assignee
from lib.users import extract_mentions, find_users, mention_token, person_label, verify_mentions

WILHELM = {"name": "thomas.wilhelm", "displayName": "Thomas Wilhelm", "emailAddress": "t.w@example.com", "active": True}
CLOUD_JANE = {"accountId": "5b10ac8d82e05b22cc7d4ef5", "displayName": "Jane Doe"}
CLOUD_URL = "https://example.atlassian.net"


# ─── extract_mentions ────────────────────────────────────────────────────────


def test_extract_mentions_dedupes_and_preserves_order():
    text = "[~jane.doe] and [~john.roe], again [~jane.doe]"
    assert extract_mentions(text) == ["jane.doe", "john.roe"]


def test_extract_mentions_handles_accountid_and_empty():
    assert extract_mentions("[~accountid:5b10ac8d82e05b22cc7d4ef5] hi") == ["accountid:5b10ac8d82e05b22cc7d4ef5"]
    assert extract_mentions("no mentions here") == []
    assert extract_mentions("") == []


def test_extract_mentions_skips_literal_blocks_and_escapes():
    assert extract_mentions("{code}log [~olduser]{code} but [~real.user]") == ["real.user"]
    assert extract_mentions("{noformat}ERROR notifying [~offboarded]{noformat}") == []
    assert extract_mentions("write \\[~jane.fake] to mention someone") == []


# ─── person_label / mention_token ────────────────────────────────────────────


def test_person_label_appends_username():
    assert person_label(WILHELM) == "Thomas Wilhelm (thomas.wilhelm)"


def test_person_label_fallbacks_and_cloud():
    assert person_label(None) == "Unknown"
    assert person_label(None, fallback="Unassigned") == "Unassigned"
    assert person_label({"displayName": "Nameless"}) == "Nameless"
    assert person_label(CLOUD_JANE) == "Jane Doe (accountid:5b10ac8d82e05b22cc7d4ef5)"


def test_mention_token_prefers_name_then_accountid():
    assert mention_token(WILHELM) == "[~thomas.wilhelm]"
    assert mention_token(CLOUD_JANE) == "[~accountid:5b10ac8d82e05b22cc7d4ef5]"
    assert mention_token({"displayName": "No Id"}) is None


# ─── find_users (Server vs Cloud kwarg) ──────────────────────────────────────


def test_find_users_uses_username_on_server_and_query_on_cloud():
    mc = make_mock_client()  # url defaults to https://jira.example.com → Server
    mc.user_find_by_user_string = mock.Mock(return_value=[WILHELM])
    assert find_users(mc, "wilhelm") == [WILHELM]
    assert mc.user_find_by_user_string.call_args.kwargs.get("username") == "wilhelm"

    mc = make_mock_client(url=CLOUD_URL)
    mc.user_find_by_user_string = mock.Mock(return_value=[CLOUD_JANE])
    assert find_users(mc, "jane") == [CLOUD_JANE]
    assert mc.user_find_by_user_string.call_args.kwargs.get("query") == "jane"


# ─── verify_mentions ─────────────────────────────────────────────────────────


def test_verify_mentions_all_known():
    mc = make_mock_client()
    mc.user = mock.Mock(return_value=WILHELM)
    assert verify_mentions(mc, "ping [~thomas.wilhelm]") == {}
    mc.user.assert_called_once_with(username="thomas.wilhelm")


def test_verify_mentions_unknown_collects_suggestions():
    mc = make_mock_client()
    mc.user = mock.Mock(side_effect=Exception("404"))
    mc.user_find_by_user_string = mock.Mock(return_value=[WILHELM])
    unknown = verify_mentions(mc, "ping [~thomas.wilhem]")
    assert unknown == {"thomas.wilhem": [WILHELM]}
    # Server/DC path must search via username=, not query= (silent empty there)
    assert mc.user_find_by_user_string.call_args.kwargs.get("username") == "thomas.wilhem"


def test_verify_mentions_skips_accountid():
    mc = make_mock_client()
    mc.user = mock.Mock(side_effect=AssertionError("must not be called"))
    assert verify_mentions(mc, "[~accountid:5b10ac8d82e05b22cc7d4ef5]") == {}


def test_verify_mentions_cloud_flags_plain_usernames_with_accountid_suggestions():
    mc = make_mock_client(url=CLOUD_URL)
    mc.user = mock.Mock(side_effect=AssertionError("username lookup impossible on Cloud"))
    mc.user_find_by_user_string = mock.Mock(return_value=[CLOUD_JANE])
    unknown = verify_mentions(mc, "ping [~jane.doe]")
    assert unknown == {"jane.doe": [CLOUD_JANE]}


def test_verify_mentions_propagates_infrastructure_errors():
    mc = make_mock_client()
    mc.user = mock.Mock(side_effect=AuthenticationError("401"))
    with pytest.raises(AuthenticationError):
        verify_mentions(mc, "ping [~thomas.wilhelm]")

    http_503 = Exception("boom")
    http_503.response = mock.Mock(status_code=503)
    mc = make_mock_client()
    mc.user = mock.Mock(side_effect=http_503)
    with pytest.raises(Exception, match="boom"):
        verify_mentions(mc, "ping [~thomas.wilhelm]")


# ─── resolve_assignee (exact-first, no silent fuzzy pick) ────────────────────


def _client_without_exact_user():
    mc = make_mock_client()
    mc.user = mock.Mock(side_effect=Exception("404"))
    return mc


def test_resolve_assignee_prefers_exact_username_lookup():
    mc = make_mock_client()
    mc.user = mock.Mock(return_value=WILHELM)
    mc.user_find_by_user_string = mock.Mock(side_effect=AssertionError("no search needed"))
    assert resolve_assignee(mc, "thomas.wilhelm") == {"name": "thomas.wilhelm"}


def test_resolve_assignee_exact_field_match_wins_over_order():
    mc = _client_without_exact_user()
    jana = {"name": "jana.mueller", "displayName": "Jana Mueller", "emailAddress": "jana@example.com"}
    mc.user_find_by_user_string = mock.Mock(return_value=[jana, WILHELM])
    assert resolve_assignee(mc, "t.w@example.com") == {"name": "thomas.wilhelm"}


def test_resolve_assignee_single_candidate_accepted():
    mc = _client_without_exact_user()
    mc.user_find_by_user_string = mock.Mock(return_value=[WILHELM])
    assert resolve_assignee(mc, "wilhel") == {"name": "thomas.wilhelm"}


def test_resolve_assignee_ambiguous_fragment_falls_back_to_raw():
    mc = _client_without_exact_user()
    other = {"name": "thomas.mueller", "displayName": "Thomas Mueller"}
    mc.user_find_by_user_string = mock.Mock(return_value=[other, WILHELM])
    # Two fuzzy candidates, none exact: never silently pick one
    assert resolve_assignee(mc, "thomas") == {"name": "thomas"}


# ─── CLI mention gate (jira-comment + jira-transition) ───────────────────────


def _comment_client(**attrs):
    mc = make_mock_client(**attrs)
    mc.issue_add_comment = mock.Mock(return_value={"id": "1"})
    return mc


def test_comment_add_blocks_unknown_mention():
    mod = load_script("jira-comment", "workflow")
    mc = _comment_client()
    mc.user = mock.Mock(side_effect=Exception("404"))
    mc.user_find_by_user_string = mock.Mock(return_value=[WILHELM])
    result, _ = run_cli(mod, ["add", "PROJ-1", "ping [~thomas.wilhem]"], mock_client=mc)
    assert result.exit_code == 1
    assert "did you mean" in result.output and "[~thomas.wilhelm]" in result.output
    mc.issue_add_comment.assert_not_called()


def test_comment_add_posts_verified_mention():
    mod = load_script("jira-comment", "workflow")
    mc = _comment_client()
    mc.user = mock.Mock(return_value=WILHELM)
    result, _ = run_cli(mod, ["add", "PROJ-1", "ping [~thomas.wilhelm]"], mock_client=mc)
    assert result.exit_code == 0
    mc.issue_add_comment.assert_called_once()


def test_comment_add_no_verify_flag_skips_lookup():
    mod = load_script("jira-comment", "workflow")
    mc = _comment_client()
    mc.user = mock.Mock(side_effect=AssertionError("must not be called"))
    result, _ = run_cli(mod, ["add", "--no-verify-mentions", "PROJ-1", "ping [~whoever]"], mock_client=mc)
    assert result.exit_code == 0
    mc.issue_add_comment.assert_called_once()


def test_comment_add_without_mentions_makes_no_user_calls():
    mod = load_script("jira-comment", "workflow")
    mc = _comment_client()
    mc.user = mock.Mock(side_effect=AssertionError("must not be called"))
    result, _ = run_cli(mod, ["add", "PROJ-1", "plain text"], mock_client=mc)
    assert result.exit_code == 0
    mc.issue_add_comment.assert_called_once()


def test_comment_add_reports_transport_error_as_such():
    mod = load_script("jira-comment", "workflow")
    mc = _comment_client()
    mc.user = mock.Mock(side_effect=AuthenticationError("401 Unauthorized"))
    result, _ = run_cli(mod, ["add", "PROJ-1", "ping [~thomas.wilhelm]"], mock_client=mc)
    assert result.exit_code == 1
    assert "transport/auth" in result.output
    assert "does not match" not in result.output
    mc.issue_add_comment.assert_not_called()


def test_transition_comment_runs_mention_gate():
    mod = load_script("jira-transition", "workflow")
    mc = make_mock_client()
    mc.user = mock.Mock(side_effect=Exception("404"))
    mc.user_find_by_user_string = mock.Mock(return_value=[])
    mc.get_issue_transitions = mock.Mock(return_value=[{"name": "Done", "to": {"name": "Done"}}])
    mc.set_issue_status = mock.Mock()
    result, _ = run_cli(mod, ["do", "PROJ-1", "Done", "--comment", "ping [~thomas.wilhem]"], mock_client=mc)
    assert result.exit_code == 1
    mc.set_issue_status.assert_not_called()
