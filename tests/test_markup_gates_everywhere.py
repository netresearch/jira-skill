"""Every surface that posts wiki markup runs the same three gates.

The point of this file is the parametrisation, not any single case. The gates
lived in ``jira-comment.py`` and therefore ran on two of the seven surfaces;
the other five rendered the same markup through the same renderer and mangled
it the same way. A per-command test would have passed for ``add`` and told
nobody about the other six, which is the shape the original gap had.

The population is enumerated from the places that POST a body, not from the
call sites of a neighbouring gate. Counting the mention gate instead gave six
and missed ``jira-transition path --comment``, which carries neither.

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
from lib import markup_cli
from lib.preview import RenderVerdict

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/jira-communication/scripts"))

MARKER = "Extensions"
RAW = "Die {{a}}-Extensions, jede zu- und abschaltbar"
REPAIRED = "Die {{a}}\\-Extensions, jede zu- und abschaltbar"

# (id, script, folder, argv, the mock attribute that receives the write)
SURFACES = [
    ("comment-add", "jira-comment", "workflow", ["add", "PROJ-1", RAW], "issue_add_comment"),
    ("comment-edit", "jira-comment", "workflow", ["edit", "PROJ-1", "42", RAW], "issue_edit_comment"),
    ("worklog-comment", "jira-worklog", "core", ["add", "PROJ-1", "2h", "--comment", RAW], "issue_add_json_worklog"),
    ("issue-description", "jira-issue", "core", ["update", "PROJ-1", "--description", RAW], "update_issue_field"),
    (
        "create-description",
        "jira-create",
        "workflow",
        ["issue", "PROJ", "Summary", "--type", "Task", "--description", RAW],
        "create_issue",
    ),
    ("transition-comment", "jira-transition", "workflow", ["do", "PROJ-1", "Done", "--comment", RAW], "post"),
    ("path-comment", "jira-transition", "workflow", ["path", "PROJ-1", "Done", "--comment", RAW], "post"),
]


def _run(script, folder, argv, mock_client=None):
    module = load_script(script, folder)
    client = mock_client or make_mock_client()
    # A transition reads the available transitions before posting its comment;
    # the shared mock returns a bare Mock, which is not iterable.
    client.get_issue_transitions.return_value = [{"id": "31", "name": "Done", "to": {"name": "Done"}}]
    # `path` walks from the current status, so it reads one before transitioning.
    client.issue.return_value = {"fields": {"status": {"name": "Open"}}}
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
    looked one level down found four of seven and read like all of them.
    """
    if isinstance(value, str):
        return value if MARKER in value else None
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


def _written_text(client, attr):
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


@pytest.mark.parametrize("name,script,folder,argv,attr", SURFACES, ids=[s[0] for s in SURFACES])
def test_the_repair_reaches_every_surface(name, script, folder, argv, attr):
    result, client = _run(script, folder, argv)
    assert result.exit_code == 0, result.output
    written = _written_text(client, attr)
    assert written is not None, f"{name}: no wiki-markup body reached the client"
    assert written == REPAIRED, f"{name}: posted unrepaired text"


# Carries MARKER so a surface that wrote anyway is caught by the same search.
LINT_BAIT = "See {code} Extensions"


@pytest.mark.parametrize("name,script,folder,argv,attr", SURFACES, ids=[s[0] for s in SURFACES])
def test_a_lint_finding_aborts_every_surface(name, script, folder, argv, attr):
    """Gate 2 is wired everywhere, not just gate 1.

    The repair test above asserts text equality, which only exercises
    ``repair_markup``. Swapping any surface's ``guard_wiki_markup`` for a bare
    ``repair_markup`` would leave it green - this is the case that catches it.
    ``{code}`` used inline is a block tag mid-prose: the escaper leaves it
    alone, so only the lint can refuse it.
    """
    baited = [LINT_BAIT if arg is RAW else arg for arg in argv]
    result, client = _run(script, folder, baited)
    assert result.exit_code == 1, f"{name}: a block tag used inline must abort\n{result.output}"
    assert _written_text(client, attr) is None, f"{name}: wrote despite a lint finding"


@pytest.mark.parametrize("name,script,folder,argv,attr", SURFACES, ids=[s[0] for s in SURFACES])
def test_the_selected_profile_reaches_the_render_preview(name, script, folder, argv, attr):
    """--profile must reach the preview, or it previews against another tenant.

    The gates read the config from ``ctx.obj``, which only ``jira-comment.py``
    populated. Everywhere else ``ctx.obj.get("profile")`` returned None and the
    preview silently resolved the DEFAULT profile - a different Jira - while
    the command itself wrote to the selected one. Nothing reported it, because
    an unreachable renderer is advisory and just warns.
    """
    seen = {}

    def _record(text, *, issue_key=None, env_file=None, profile=None, **kwargs):
        seen["profile"] = profile
        seen["env_file"] = env_file
        return RenderVerdict(False, [], "stubbed")

    module = load_script(script, folder)
    client = make_mock_client()
    client.get_issue_transitions.return_value = [{"id": "31", "name": "Done", "to": {"name": "Done"}}]
    client.issue.return_value = {"fields": {"status": {"name": "Open"}}}
    client.create_issue.return_value = {"key": "PROJ-1", "id": "1"}
    runner = click.testing.CliRunner()
    with (
        mock.patch.object(module, "LazyJiraClient", return_value=client),
        mock.patch.object(module, "check_mentions_cli", return_value=None),
        mock.patch.object(markup_cli, "preflight_render", _record),
    ):
        result = runner.invoke(module.cli, ["--profile", "tenant-b", "--env-file", "/tmp/x.env", *argv])

    assert result.exit_code == 0, f"{name}: {result.output}"
    assert seen.get("profile") == "tenant-b", f"{name}: preview got profile {seen.get('profile')!r}"
    assert seen.get("env_file") == "/tmp/x.env", f"{name}: preview got env_file {seen.get('env_file')!r}"


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


@pytest.mark.parametrize("name,script,folder,argv,attr", SURFACES, ids=[s[0] for s in SURFACES])
def test_every_surface_offers_the_three_flags(name, script, folder, argv, attr):
    """The opt-outs must exist wherever the gates do, or --force is a lie."""
    module = load_script(script, folder)
    runner = click.testing.CliRunner()
    help_text = runner.invoke(module.cli, [argv[0], "--help"]).output
    for flag in ("--force", "--no-auto-escape", "--no-preflight"):
        assert flag in help_text, f"{name}: {flag} missing"
