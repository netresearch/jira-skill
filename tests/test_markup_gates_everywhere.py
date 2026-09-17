"""Every surface that posts wiki markup runs the same three gates.

The point of this file is the parametrisation, not any single case. The gates
lived in ``jira-comment.py`` and therefore ran on two of the six surfaces; the
other four rendered the same markup through the same renderer and mangled it
the same way. A per-command test would have passed for ``add`` and told nobody
about the other five, which is the shape the original gap had.

Each case drives the real Click command with a mocked client and asserts on the
text the client was handed - not on a helper call, because "the helper exists"
was true the whole time the descriptions were unguarded.
"""

import sys
from pathlib import Path
from unittest import mock

import click.testing
import pytest
from conftest import load_script, make_mock_client

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/jira-communication/scripts"))

RAW = "Die {{a}}-Extensions, jede zu- und abschaltbar"
REPAIRED = "Die {{a}}\\-Extensions, jede zu- und abschaltbar"

# (id, script, folder, argv, mock attribute that receives the write, index of
# the text in that call's positional args)
SURFACES = [
    ("comment-add", "jira-comment", "workflow", ["add", "PROJ-1", RAW], "issue_add_comment", 1),
    ("comment-edit", "jira-comment", "workflow", ["edit", "PROJ-1", "42", RAW], "issue_edit_comment", 2),
    (
        "worklog-comment",
        "jira-worklog",
        "core",
        ["add", "PROJ-1", "2h", "--comment", RAW],
        "issue_add_json_worklog",
        None,
    ),
    ("issue-description", "jira-issue", "core", ["update", "PROJ-1", "--description", RAW], "update_issue_field", None),
    (
        "create-description",
        "jira-create",
        "workflow",
        ["issue", "PROJ", "Summary", "--type", "Task", "--description", RAW],
        "create_issue",
        None,
    ),
    ("transition-comment", "jira-transition", "workflow", ["do", "PROJ-1", "Done", "--comment", RAW], None, None),
]


def _run(script, folder, argv, mock_client=None):
    module = load_script(script, folder)
    client = mock_client or make_mock_client()
    # A transition reads the available transitions before posting its comment;
    # the shared mock returns a bare Mock, which is not iterable.
    client.get_issue_transitions.return_value = [{"id": "31", "name": "Done", "to": {"name": "Done"}}]
    client.issue_transition.return_value = None
    client.create_issue.return_value = {"key": "PROJ-1", "id": "1"}
    runner = click.testing.CliRunner()
    with (
        mock.patch.object(module, "LazyJiraClient", return_value=client),
        mock.patch.object(module, "check_mentions_cli", return_value=None),
    ):
        result = runner.invoke(module.cli, argv)
    return result, client


def _find_marker(value):
    """The wiki-markup body anywhere inside a call's arguments.

    Recursive because the surfaces bury it at different depths: a comment is a
    positional argument, a description sits in a fields dict, and a transition
    posts `payload["update"]["comment"][0]["add"]["body"]`. A search that only
    looked one level down found four of six and read like all six.
    """
    if isinstance(value, str):
        return value if "Extensions" in value else None
    if isinstance(value, dict):
        for inner in value.values():
            found = _find_marker(inner)
            if found is not None:
                return found
    if isinstance(value, (list, tuple)):
        for inner in value:
            found = _find_marker(inner)
            if found is not None:
                return found
    return None


def _written_text(client, attr, index):
    """The wiki-markup body the client was handed, wherever it ended up."""
    calls = []
    if attr is not None and getattr(client, attr).call_args is not None:
        calls.append(getattr(client, attr).call_args)
    else:
        for name in dir(client):
            if name.startswith("_"):
                continue
            call = getattr(getattr(client, name), "call_args", None)
            if call is not None:
                calls.append(call)
    for call in calls:
        found = _find_marker(list(call.args) + list(call.kwargs.values()))
        if found is not None:
            return found
    return None


@pytest.mark.parametrize("name,script,folder,argv,attr,index", SURFACES, ids=[s[0] for s in SURFACES])
def test_the_repair_reaches_every_surface(name, script, folder, argv, attr, index):
    result, client = _run(script, folder, argv)
    assert result.exit_code == 0, result.output
    written = _written_text(client, attr, index)
    assert written is not None, f"{name}: no wiki-markup body reached the client"
    assert written == REPAIRED, f"{name}: posted unrepaired text"


def test_create_renders_without_an_issue_key_but_lints_the_project():
    """The two gates on ``create issue`` need different keys, deliberately.

    ``POST /rest/api/1.0/render`` resolves ``issueKey`` to a real issue and
    answers 404 for a project key - measured against jira.netresearch.de - so
    passing the project there would print "render preview unavailable" on every
    create. The language lint, which only reads the project part, still gets it.
    """
    module = load_script("jira-create", "workflow")
    seen = {}

    def _record(text, *, issue_key=None, **kwargs):
        seen["render_key"] = issue_key
        from lib.preview import RenderVerdict

        return RenderVerdict(False, [], "stubbed")

    def _lint(text, issue_key):
        seen["lint_key"] = issue_key
        return []

    from lib import markup_cli

    client = make_mock_client()
    client.create_issue.return_value = {"key": "PROJ-1", "id": "1"}
    runner = click.testing.CliRunner()
    with (
        mock.patch.object(module, "LazyJiraClient", return_value=client),
        mock.patch.object(module, "check_mentions_cli", return_value=None),
        mock.patch.object(markup_cli, "preflight_render", _record),
        mock.patch.object(markup_cli, "lint_ticket_language", _lint),
    ):
        result = runner.invoke(module.cli, ["issue", "PROJ", "Summary", "--type", "Task", "--description", RAW])

    assert result.exit_code == 0, result.output
    assert seen["render_key"] is None, "the renderer must not be handed a project key"
    assert seen["lint_key"] == "PROJ", "the language lint must still see the project"


@pytest.mark.parametrize("name,script,folder,argv,attr,index", SURFACES, ids=[s[0] for s in SURFACES])
def test_every_surface_offers_the_three_flags(name, script, folder, argv, attr, index):
    """The opt-outs must exist wherever the gates do, or --force is a lie."""
    module = load_script(script, folder)
    runner = click.testing.CliRunner()
    help_text = runner.invoke(module.cli, [argv[0], "--help"]).output
    for flag in ("--force", "--no-auto-escape", "--no-preflight"):
        assert flag in help_text, f"{name}: {flag} missing"
