"""Tests for lib.users (mention verification) and the jira-comment mention gate."""

from unittest import mock

from conftest import load_script, make_mock_client, run_cli
from lib.users import extract_mentions, person_label, verify_mentions

WILHELM = {"name": "thomas.wilhelm", "displayName": "Thomas Wilhelm", "emailAddress": "t.w@example.com", "active": True}


# ─── extract_mentions ────────────────────────────────────────────────────────


def test_extract_mentions_dedupes_and_preserves_order():
    text = "[~jane.doe] and [~john.roe], again [~jane.doe]"
    assert extract_mentions(text) == ["jane.doe", "john.roe"]


def test_extract_mentions_handles_accountid_and_empty():
    assert extract_mentions("[~accountid:5b10ac8d82e05b22cc7d4ef5] hi") == ["accountid:5b10ac8d82e05b22cc7d4ef5"]
    assert extract_mentions("no mentions here") == []
    assert extract_mentions("") == []


# ─── person_label ────────────────────────────────────────────────────────────


def test_person_label_appends_username():
    assert person_label(WILHELM) == "Thomas Wilhelm (thomas.wilhelm)"


def test_person_label_fallbacks():
    assert person_label(None) == "Unknown"
    assert person_label(None, fallback="Unassigned") == "Unassigned"
    assert person_label({"displayName": "Cloud User"}) == "Cloud User"


# ─── verify_mentions ─────────────────────────────────────────────────────────


def test_verify_mentions_all_known():
    mc = make_mock_client()
    mc.user = mock.Mock(return_value=WILHELM)
    assert verify_mentions(mc, "ping [~thomas.wilhelm]") == {}
    mc.user.assert_called_once_with(username="thomas.wilhelm")


def test_verify_mentions_unknown_collects_suggestions():
    mc = make_mock_client(cloud=False)
    mc.user = mock.Mock(side_effect=Exception("404"))
    mc.user_find_by_user_string = mock.Mock(return_value=[WILHELM])
    unknown = verify_mentions(mc, "ping [~thomas.wilhem]")
    assert unknown == {"thomas.wilhem": [WILHELM]}
    # Server/DC path must search via username=, not query= (silent empty there)
    assert mc.user_find_by_user_string.call_args.kwargs.get("username") == "thomas.wilhem"


def test_find_users_uses_query_on_cloud():
    from lib.users import find_users

    mc = make_mock_client(cloud=True)
    mc.user_find_by_user_string = mock.Mock(return_value=[WILHELM])
    assert find_users(mc, "wilhelm") == [WILHELM]
    assert mc.user_find_by_user_string.call_args.kwargs.get("query") == "wilhelm"


def test_verify_mentions_skips_accountid():
    mc = make_mock_client()
    mc.user = mock.Mock(side_effect=AssertionError("must not be called"))
    assert verify_mentions(mc, "[~accountid:5b10ac8d82e05b22cc7d4ef5]") == {}


# ─── jira-comment mention gate ───────────────────────────────────────────────


def _comment_client(**attrs):
    mc = make_mock_client(**attrs)
    mc.issue_add_comment = mock.Mock(return_value={"id": "1"})
    return mc


def test_comment_add_blocks_unknown_mention():
    mod = load_script("jira-comment", "workflow")
    mc = _comment_client(cloud=False)
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
