"""`jira-comment list` must say on stderr when it is showing part of a history.

The notice used to be a `print()` in the table branch only. A caller piping the
table through a line filter dropped it, and `--json` / `--quiet` never had it at
all -- so a read of 10 of 163 comments looked exactly like a complete one. The
failure that follows is a confident negative ("no such comment on this ticket")
drawn from a cut nobody saw.
"""

from conftest import load_script, make_mock_client, run_cli

_mod = load_script("jira-comment", "workflow")


def _comment(cid: str):
    return {
        "id": cid,
        "author": {"displayName": "Someone", "name": "someone"},
        "created": "2026-09-11T10:00:00.000+0200",
        "body": f"body of {cid}",
    }


def _client_with(shown: int, total: int):
    """A client whose issue() returns `shown` comments out of `total`."""
    mc = make_mock_client()
    mc.issue = lambda key, fields=None: {
        "fields": {"comment": {"comments": [_comment(str(i)) for i in range(shown)], "total": total}}
    }
    return mc


def _stderr(result):
    """click >= 8.2 keeps stderr separate; older runners merge it into output."""
    try:
        return result.stderr
    except (AttributeError, ValueError):
        return result.output


class TestTruncationNotice:
    def test_table_mode_warns_on_stderr_not_only_stdout(self):
        result, _ = run_cli(_mod, ["list", "PROJ-1"], _client_with(shown=10, total=163))
        assert result.exit_code == 0
        assert "10 of 163" in _stderr(result)

    def test_json_mode_warns_too(self):
        """The worst case: a machine reading --json got no notice at all."""
        result, _ = run_cli(_mod, ["--json", "list", "PROJ-1"], _client_with(shown=10, total=163))
        assert result.exit_code == 0
        assert "10 of 163" in _stderr(result)

    def test_quiet_mode_warns_too(self):
        result, _ = run_cli(_mod, ["--quiet", "list", "PROJ-1"], _client_with(shown=10, total=163))
        assert result.exit_code == 0
        assert "10 of 163" in _stderr(result)

    def test_complete_history_is_not_flagged(self):
        """A full read must stay quiet, or the warning becomes noise and is ignored."""
        result, _ = run_cli(_mod, ["list", "PROJ-1"], _client_with(shown=3, total=3))
        assert result.exit_code == 0
        assert "of 3 comments" not in _stderr(result)
