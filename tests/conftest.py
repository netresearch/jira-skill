"""Shared test harness for the Jira CLI script tests.

Each CLI script is a standalone file (PEP 723, loaded by path rather than
installed as a package), so tests import them via :func:`load_script`.
:func:`make_mock_client` and :func:`run_cli` centralize the Click +
mocked-``LazyJiraClient`` invocation every command test performs.

Living in ``conftest.py`` means pytest makes these importable from any test
module (``from conftest import load_script, make_mock_client, run_cli``) and
the scripts path is added to ``sys.path`` once, before any test module loads.
"""

import importlib.util
import sys
from pathlib import Path
from unittest import mock

import click.testing

_SCRIPTS_PATH = Path(__file__).parent.parent / "skills" / "jira-communication" / "scripts"
if str(_SCRIPTS_PATH) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_PATH))


def load_script(name: str, subdir: str):
    """Import a standalone CLI script by file path and return the module.

    ``name`` is the hyphenated script name (e.g. ``jira-issue``); ``subdir`` is
    its directory under ``scripts/`` (``core`` / ``workflow`` / ``utility``).
    """
    path = _SCRIPTS_PATH / subdir / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def make_mock_client(url: str = "https://jira.example.com", **attrs):
    """Build a mock Jira client exposing the attributes scripts read off
    ``LazyJiraClient`` (``url``, ``with_context``, plus any extras via
    ``attrs`` — e.g. ``cloud=True``)."""
    mc = mock.Mock()
    mc.with_context = mock.Mock()
    mc.url = url
    for key, value in attrs.items():
        setattr(mc, key, value)
    return mc


def run_cli(mod, args, mock_client=None):
    """Invoke a script module's Click ``cli`` with ``LazyJiraClient`` patched
    to a mock. Returns ``(result, mock_client)``."""
    if mock_client is None:
        mock_client = make_mock_client()
    runner = click.testing.CliRunner()
    with mock.patch.object(mod, "LazyJiraClient", return_value=mock_client):
        result = runner.invoke(mod.cli, args)
    return result, mock_client
