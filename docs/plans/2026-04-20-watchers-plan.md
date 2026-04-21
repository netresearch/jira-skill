# Watchers Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `jira-watchers.py` — a Click subcommand group that lists, adds, and removes watchers on a Jira issue across Server/DC and Cloud.

**Architecture:** One standalone script in `scripts/utility/` with three subcommands (`list`, `add`, `remove`) on a `@click.group()`. Thin wrapper over `atlassian-python-api`'s `issue_get_watchers` / `issue_add_watcher` / `issue_delete_watcher`. User identity flows through a small pure helper that unwraps `resolve_assignee()`'s dict into a flat `(value, is_account_id)` pair suitable for the raw-string POST body and the DC-vs-Cloud DELETE query-param switch.

**Tech Stack:** Python 3.10+, click, PEP 723 inline deps, LazyJiraClient, atlassian-python-api.

**Design doc:** `docs/plans/2026-04-20-watchers-design.md`

**Sub-skills to use while executing:**
- `@superpowers:executing-plans` — task-by-task execution cadence.
- `@superpowers:test-driven-development` — fail/pass/commit cycle, one behavior at a time.
- `@superpowers:verification-before-completion` — run tests and confirm output before claiming done.

---

### Task 1: Scaffold test file and script skeleton

**Files:**
- Create: `tests/test_watchers.py`
- Create: `skills/jira-communication/scripts/utility/jira-watchers.py`

**Step 1: Create the test file with imports, loader, and first failing test**

Write `tests/test_watchers.py`:

```python
"""Tests for jira-watchers.py — list/add/remove issue watchers."""

import importlib.util
import json
import sys
from pathlib import Path
from unittest import mock

import click.testing
import pytest

# Add scripts to path for lib imports
_test_dir = Path(__file__).parent
_scripts_path = _test_dir.parent / "skills" / "jira-communication" / "scripts"
sys.path.insert(0, str(_scripts_path))


def _load_script(name: str, subdir: str = "utility"):
    """Load a hyphenated CLI script via importlib."""
    path = _scripts_path / subdir / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_watchers_mod = _load_script("jira-watchers", "utility")


def _make_mock_client(cloud: bool = False):
    mc = mock.Mock()
    mc.with_context = mock.Mock()
    # Explicit attribute — LazyJiraClient exposes .cloud via atlassian.Jira
    object.__setattr__(mc, "cloud", cloud)
    return mc


def _run(args, mock_client=None):
    """Run jira-watchers CLI with a mocked LazyJiraClient."""
    if mock_client is None:
        mock_client = _make_mock_client()
    runner = click.testing.CliRunner()
    with mock.patch.object(_watchers_mod, "LazyJiraClient", return_value=mock_client):
        result = runner.invoke(_watchers_mod.cli, args)
    return result, mock_client


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: help / subcommand registration
# ═══════════════════════════════════════════════════════════════════════════════


class TestWatchersHelp:
    def test_cli_help_shows_subcommands(self):
        runner = click.testing.CliRunner()
        result = runner.invoke(_watchers_mod.cli, ["--help"])
        assert result.exit_code == 0, result.output
        assert "list" in result.output
        assert "add" in result.output
        assert "remove" in result.output
```

**Step 2: Create the script skeleton**

Write `skills/jira-communication/scripts/utility/jira-watchers.py`:

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "atlassian-python-api>=3.41.0,<4",
#     "click>=8.1.0,<9",
# ]
# ///
"""Jira watcher operations — list, add, and remove issue watchers."""

import sys
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════════════
# Shared library import (TR1.1.1 - PYTHONPATH approach)
# ═══════════════════════════════════════════════════════════════════════════════
_script_dir = Path(__file__).parent
_lib_path = _script_dir.parent / "lib"
if _lib_path.exists():
    sys.path.insert(0, str(_lib_path.parent))

import click
from lib.client import LazyJiraClient, is_account_id, resolve_assignee
from lib.output import error, format_json, success, warning

# ═══════════════════════════════════════════════════════════════════════════════
# CLI Definition
# ═══════════════════════════════════════════════════════════════════════════════


@click.group()
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option("--quiet", "-q", is_flag=True, help="Minimal output")
@click.option("--env-file", type=click.Path(), help="Environment file path")
@click.option("--profile", "-P", help="Jira profile name from ~/.jira/profiles.json")
@click.option("--debug", is_flag=True, help="Show debug information on errors")
@click.pass_context
def cli(ctx, output_json: bool, quiet: bool, env_file: str | None, profile: str | None, debug: bool):
    """Jira watcher operations.

    List, add, and remove watchers on Jira issues.
    """
    ctx.ensure_object(dict)
    ctx.obj["json"] = output_json
    ctx.obj["quiet"] = quiet
    ctx.obj["debug"] = debug
    ctx.obj["client"] = LazyJiraClient(env_file=env_file, profile=profile)


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _resolve_watcher_identifier(client, identifier: str) -> tuple[str, bool]:
    """Return (value, is_account_id) suitable for issue_add_watcher / issue_delete_watcher.

    Reuses resolve_assignee() for the hard part (me / accountId / user search) and
    unwraps the dict into a flat string — the watchers REST API takes a bare
    identifier, not {"name": ...} / {"accountId": ...}.
    """
    raise NotImplementedError


# ═══════════════════════════════════════════════════════════════════════════════
# Subcommands
# ═══════════════════════════════════════════════════════════════════════════════


@cli.command("list")
@click.argument("issue_key")
@click.pass_context
def list_watchers(ctx, issue_key: str):
    """List watchers on an issue.

    ISSUE_KEY: The Jira issue key (e.g. PROJ-123)
    """
    raise NotImplementedError


@cli.command()
@click.argument("issue_key")
@click.option("--user", default="me", help="Username, accountId, email, or 'me' (default: me)")
@click.pass_context
def add(ctx, issue_key: str, user: str):
    """Add a watcher to an issue (default: yourself)."""
    raise NotImplementedError


@cli.command()
@click.argument("issue_key")
@click.option("--user", default="me", help="Username, accountId, email, or 'me' (default: me)")
@click.option("--dry-run", is_flag=True, help="Show what would be removed")
@click.pass_context
def remove(ctx, issue_key: str, user: str, dry_run: bool):
    """Remove a watcher from an issue (default: yourself)."""
    raise NotImplementedError


if __name__ == "__main__":
    cli()
```

**Step 3: Run the test to verify it passes**

```bash
uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_watchers.py::TestWatchersHelp -v --no-header
```

Expected: `test_cli_help_shows_subcommands PASSED`. (Help text is exercised before the `NotImplementedError` body is ever reached, so Click's group registration alone is enough.)

**Step 4: Smoke-check the script loads end-to-end**

```bash
uv run skills/jira-communication/scripts/utility/jira-watchers.py --help
```

Expected: help banner listing `list`, `add`, `remove` subcommands, exit code 0.

**Step 5: Commit**

```bash
git add tests/test_watchers.py skills/jira-communication/scripts/utility/jira-watchers.py
git commit -m "feat(watchers): scaffold jira-watchers script and help test"
```

---

### Task 2: `list` subcommand — happy path with watchers

**Files:**
- Modify: `tests/test_watchers.py`
- Modify: `skills/jira-communication/scripts/utility/jira-watchers.py`

**Step 1: Write failing test**

Append to `tests/test_watchers.py`:

```python
def _watcher(name="jdoe", display="John Doe", account_id=None):
    """Build a watcher dict matching the Jira API shape."""
    w = {"name": name, "displayName": display, "active": True}
    if account_id is not None:
        w["accountId"] = account_id
    return w


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: list subcommand
# ═══════════════════════════════════════════════════════════════════════════════


class TestWatchersList:
    def test_list_text_output(self):
        mc = _make_mock_client()
        mc.issue_get_watchers.return_value = {
            "watchCount": 2,
            "isWatching": False,
            "watchers": [
                _watcher("jdoe", "John Doe"),
                _watcher("asmith", "Alice Smith"),
            ],
        }
        result, _ = _run(["list", "TEST-1"], mc)
        assert result.exit_code == 0, result.output
        assert "TEST-1" in result.output
        assert "jdoe" in result.output
        assert "John Doe" in result.output
        assert "asmith" in result.output
        assert "Alice Smith" in result.output
        mc.issue_get_watchers.assert_called_once_with("TEST-1")
```

**Step 2: Run and verify FAIL**

```bash
uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_watchers.py::TestWatchersList -v --no-header
```

Expected: `NotImplementedError` raised inside `list_watchers`.

**Step 3: Implement `list_watchers`**

Replace the `list_watchers` stub in `jira-watchers.py`:

```python
@cli.command("list")
@click.argument("issue_key")
@click.pass_context
def list_watchers(ctx, issue_key: str):
    """List watchers on an issue.

    ISSUE_KEY: The Jira issue key (e.g. PROJ-123)

    Example:

      jira-watchers list PROJ-123
    """
    ctx.obj["client"].with_context(issue_key=issue_key)
    client = ctx.obj["client"]

    try:
        data = client.issue_get_watchers(issue_key)

        if ctx.obj["json"]:
            print(format_json(data))
            return

        watchers = data.get("watchers", []) or []
        count = data.get("watchCount", len(watchers))

        if ctx.obj["quiet"]:
            for w in watchers:
                print(w.get("accountId") or w.get("name", ""))
            return

        if not watchers:
            print(f"(no watchers) for {issue_key}")
            return

        print(f"Watchers for {issue_key} ({count}):\n")
        for w in watchers:
            name = w.get("name") or w.get("accountId", "")
            display = w.get("displayName", "")
            print(f"  {name:<20} {display}")

    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to list watchers: {e}")
        sys.exit(1)
```

**Step 4: Run and verify PASS**

```bash
uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_watchers.py::TestWatchersList -v --no-header
```

Expected: PASS.

**Step 5: Commit**

```bash
git add tests/test_watchers.py skills/jira-communication/scripts/utility/jira-watchers.py
git commit -m "feat(watchers): implement list subcommand with watchers present"
```

---

### Task 3: `list` — empty result shows placeholder

**Files:**
- Modify: `tests/test_watchers.py`

**Step 1: Write failing test**

Add inside `class TestWatchersList`:

```python
    def test_list_empty(self):
        mc = _make_mock_client()
        mc.issue_get_watchers.return_value = {
            "watchCount": 0, "isWatching": False, "watchers": [],
        }
        result, _ = _run(["list", "TEST-1"], mc)
        assert result.exit_code == 0, result.output
        assert "(no watchers)" in result.output
        assert "TEST-1" in result.output
```

**Step 2: Run and verify PASS**

The Task 2 implementation already handles the empty case. Run the test to confirm:

```bash
uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_watchers.py::TestWatchersList::test_list_empty -v --no-header
```

Expected: PASS. If it FAILS, fix `list_watchers` so that an empty `watchers` list prints `(no watchers) for {issue_key}`.

**Step 3: Commit**

```bash
git add tests/test_watchers.py
git commit -m "test(watchers): verify list shows placeholder for empty watcher list"
```

---

### Task 4: `list` — JSON and quiet output modes

**Files:**
- Modify: `tests/test_watchers.py`

**Step 1: Write failing tests**

Add inside `class TestWatchersList`:

```python
    def test_list_json_output(self):
        mc = _make_mock_client()
        payload = {
            "watchCount": 1,
            "isWatching": True,
            "watchers": [_watcher("jdoe", "John Doe")],
        }
        mc.issue_get_watchers.return_value = payload
        result, _ = _run(["--json", "list", "TEST-1"], mc)
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["watchCount"] == 1
        assert data["isWatching"] is True
        assert data["watchers"][0]["name"] == "jdoe"

    def test_list_quiet_cloud_prints_account_ids(self):
        mc = _make_mock_client(cloud=True)
        mc.issue_get_watchers.return_value = {
            "watchCount": 2,
            "isWatching": False,
            "watchers": [
                _watcher("a", "A", account_id="557058:aaa"),
                _watcher("b", "B", account_id="557058:bbb"),
            ],
        }
        result, _ = _run(["--quiet", "list", "TEST-1"], mc)
        assert result.exit_code == 0
        lines = [ln for ln in result.output.splitlines() if ln.strip()]
        assert lines == ["557058:aaa", "557058:bbb"]

    def test_list_quiet_dc_prints_usernames(self):
        mc = _make_mock_client(cloud=False)
        mc.issue_get_watchers.return_value = {
            "watchCount": 2,
            "isWatching": False,
            "watchers": [_watcher("jdoe", "J"), _watcher("asmith", "A")],
        }
        result, _ = _run(["--quiet", "list", "TEST-1"], mc)
        assert result.exit_code == 0
        lines = [ln for ln in result.output.splitlines() if ln.strip()]
        assert lines == ["jdoe", "asmith"]
```

**Step 2: Run and verify PASS**

The implementation from Task 2 already handles both modes. Run:

```bash
uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_watchers.py::TestWatchersList -v --no-header
```

Expected: all four `TestWatchersList` tests PASS. If JSON or quiet output does not match, adjust `list_watchers` to emit exactly `format_json(data)` and, for quiet, one `accountId or name` per line.

**Step 3: Commit**

```bash
git add tests/test_watchers.py
git commit -m "test(watchers): cover list --json and --quiet output modes"
```

---

### Task 5: `add` subcommand — self-watch default

**Files:**
- Modify: `tests/test_watchers.py`
- Modify: `skills/jira-communication/scripts/utility/jira-watchers.py`

**Step 1: Write failing test**

Append:

```python
# ═══════════════════════════════════════════════════════════════════════════════
# Tests: add subcommand
# ═══════════════════════════════════════════════════════════════════════════════


class TestWatchersAdd:
    def test_add_self_default(self):
        mc = _make_mock_client()
        # Default --user is "me", resolve_assignee calls client.myself()
        mc.myself.return_value = {"name": "bwilson", "displayName": "Bob Wilson"}
        mc.issue_add_watcher.return_value = None  # 204 No Content
        result, _ = _run(["add", "TEST-1"], mc)
        assert result.exit_code == 0, result.output
        assert "Added watcher" in result.output
        assert "TEST-1" in result.output
        assert "bwilson" in result.output
        # Raw string identifier, not a dict — Jira's watchers POST body is
        # a JSON-encoded string; atlassian-python-api passes this straight
        # through as the request body.
        mc.issue_add_watcher.assert_called_once_with("TEST-1", "bwilson")
```

**Step 2: Run and verify FAIL**

```bash
uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_watchers.py::TestWatchersAdd::test_add_self_default -v --no-header
```

Expected: `NotImplementedError` from either `_resolve_watcher_identifier` or `add`.

**Step 3: Implement `_resolve_watcher_identifier` and `add`**

Replace the `_resolve_watcher_identifier` stub:

```python
def _resolve_watcher_identifier(client, identifier: str) -> tuple[str, bool]:
    """Return (value, is_account_id) suitable for issue_add_watcher / issue_delete_watcher.

    Reuses resolve_assignee() for 'me' / accountId / user-search handling and
    unwraps the {"name": ...} / {"accountId": ...} dict into a flat string,
    because the watchers REST API takes a bare identifier as its JSON body
    (not an object). atlassian-python-api passes the string through verbatim.
    """
    resolved = resolve_assignee(client, identifier)
    if "accountId" in resolved:
        return resolved["accountId"], True
    return resolved["name"], False
```

Replace the `add` stub:

```python
@cli.command()
@click.argument("issue_key")
@click.option("--user", default="me", help="Username, accountId, email, or 'me' (default: me)")
@click.pass_context
def add(ctx, issue_key: str, user: str):
    """Add a watcher to an issue (default: yourself).

    ISSUE_KEY: The Jira issue key (e.g. PROJ-123)

    Adding yourself requires only Browse Projects; adding someone else
    requires the Manage Watchers permission. Self-adds are idempotent —
    Jira silently accepts repeated adds.

    Examples:

      jira-watchers add PROJ-123

      jira-watchers add PROJ-123 --user asmith
    """
    ctx.obj["client"].with_context(issue_key=issue_key)
    client = ctx.obj["client"]

    try:
        identifier, _is_acct = _resolve_watcher_identifier(client, user)

        # POST body is a raw JSON-encoded string (e.g. '"jdoe"'), NOT
        # {"name": "jdoe"}. atlassian-python-api's issue_add_watcher handles
        # that correctly — do not wrap in a dict.
        client.issue_add_watcher(issue_key, identifier)

        suffix = " (you)" if user.lower() == "me" else ""

        if ctx.obj["json"]:
            print(format_json({"key": issue_key, "user": identifier, "added": True}))
        elif ctx.obj["quiet"]:
            print("ok")
        else:
            success(f"Added watcher to {issue_key}: {identifier}{suffix}")

    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to add watcher: {e}")
        sys.exit(1)
```

**Step 4: Run and verify PASS**

```bash
uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_watchers.py::TestWatchersAdd -v --no-header
```

Expected: PASS.

**Step 5: Commit**

```bash
git add tests/test_watchers.py skills/jira-communication/scripts/utility/jira-watchers.py
git commit -m "feat(watchers): implement add subcommand for self-watch default"
```

---

### Task 6: `add` subcommand — specific user via `--user`

**Files:**
- Modify: `tests/test_watchers.py`

**Step 1: Write failing tests**

Add inside `class TestWatchersAdd`:

```python
    def test_add_user_by_username_dc(self):
        mc = _make_mock_client(cloud=False)
        mc.user_find_by_user_string.return_value = [
            {"name": "asmith", "displayName": "Alice Smith"}
        ]
        result, _ = _run(["add", "TEST-1", "--user", "asmith"], mc)
        assert result.exit_code == 0, result.output
        assert "asmith" in result.output
        assert "(you)" not in result.output
        mc.issue_add_watcher.assert_called_once_with("TEST-1", "asmith")

    def test_add_user_by_account_id_cloud(self):
        """An account-id-shaped identifier bypasses user search."""
        mc = _make_mock_client(cloud=True)
        acct = "557058:d5765ebc-27de-4ce3-b520-a77a87e5e99a"
        result, _ = _run(["add", "TEST-1", "--user", acct], mc)
        assert result.exit_code == 0, result.output
        mc.user_find_by_user_string.assert_not_called()
        mc.issue_add_watcher.assert_called_once_with("TEST-1", acct)

    def test_add_json_output(self):
        mc = _make_mock_client()
        mc.myself.return_value = {"name": "bwilson"}
        result, _ = _run(["--json", "add", "TEST-1"], mc)
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data == {"key": "TEST-1", "user": "bwilson", "added": True}

    def test_add_quiet_output(self):
        mc = _make_mock_client()
        mc.myself.return_value = {"name": "bwilson"}
        result, _ = _run(["--quiet", "add", "TEST-1"], mc)
        assert result.exit_code == 0
        assert result.output.strip() == "ok"
```

**Step 2: Run and verify PASS**

```bash
uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_watchers.py::TestWatchersAdd -v --no-header
```

Expected: PASS — no code change needed; `resolve_assignee` + the existing `add` implementation cover all three paths.

**Step 3: Commit**

```bash
git add tests/test_watchers.py
git commit -m "test(watchers): cover add --user by name, accountId, and output modes"
```

---

### Task 7: `add` — idempotent self-add and 403 error surfacing

**Files:**
- Modify: `tests/test_watchers.py`

**Step 1: Write failing tests**

Add inside `class TestWatchersAdd`:

```python
    def test_add_self_is_idempotent(self):
        """Jira returns 204 for duplicate self-adds; script treats as success."""
        mc = _make_mock_client()
        mc.myself.return_value = {"name": "bwilson"}
        # Simulate a second add — library returns None either way, no special
        # handling needed. The test exists to pin the contract.
        mc.issue_add_watcher.return_value = None
        result, _ = _run(["add", "TEST-1"], mc)
        assert result.exit_code == 0, result.output
        assert "Added watcher" in result.output

    def test_add_manage_watchers_permission_error(self):
        mc = _make_mock_client()
        mc.user_find_by_user_string.return_value = [{"name": "asmith"}]
        mc.issue_add_watcher.side_effect = Exception(
            "403 Client Error: Forbidden — Manage Watchers permission required"
        )
        result, _ = _run(["add", "TEST-1", "--user", "asmith"], mc)
        assert result.exit_code == 1
        assert "Failed to add watcher" in result.output
        assert "403" in result.output or "Forbidden" in result.output
```

**Step 2: Run and verify PASS**

```bash
uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_watchers.py::TestWatchersAdd -v --no-header
```

Expected: PASS. If the 403 message is truncated by `error()`, confirm the full exception `str(e)` is interpolated in the f-string (it is in the Task 5 implementation).

**Step 3: Commit**

```bash
git add tests/test_watchers.py
git commit -m "test(watchers): verify idempotent self-add and 403 error surfacing"
```

---

### Task 8: `remove` subcommand — self, `--user`, and `--dry-run`

**Files:**
- Modify: `tests/test_watchers.py`
- Modify: `skills/jira-communication/scripts/utility/jira-watchers.py`

**Step 1: Write failing tests**

Append:

```python
# ═══════════════════════════════════════════════════════════════════════════════
# Tests: remove subcommand
# ═══════════════════════════════════════════════════════════════════════════════


class TestWatchersRemove:
    def test_remove_self_default_dc(self):
        mc = _make_mock_client(cloud=False)
        mc.myself.return_value = {"name": "bwilson"}
        result, _ = _run(["remove", "TEST-1"], mc)
        assert result.exit_code == 0, result.output
        assert "Removed watcher" in result.output
        assert "bwilson" in result.output
        assert "(you)" in result.output
        mc.issue_delete_watcher.assert_called_once_with("TEST-1", username="bwilson")

    def test_remove_user_by_username_dc(self):
        mc = _make_mock_client(cloud=False)
        mc.user_find_by_user_string.return_value = [{"name": "asmith"}]
        result, _ = _run(["remove", "TEST-1", "--user", "asmith"], mc)
        assert result.exit_code == 0, result.output
        assert "(you)" not in result.output
        mc.issue_delete_watcher.assert_called_once_with("TEST-1", username="asmith")

    def test_remove_dry_run_does_not_call_api(self):
        mc = _make_mock_client()
        mc.myself.return_value = {"name": "bwilson"}
        result, _ = _run(["remove", "TEST-1", "--dry-run"], mc)
        assert result.exit_code == 0, result.output
        assert "DRY RUN" in result.output
        assert "Would remove" in result.output
        assert "bwilson" in result.output
        mc.issue_delete_watcher.assert_not_called()

    def test_remove_json_output(self):
        mc = _make_mock_client(cloud=False)
        mc.myself.return_value = {"name": "bwilson"}
        result, _ = _run(["--json", "remove", "TEST-1"], mc)
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data == {"key": "TEST-1", "user": "bwilson", "removed": True}

    def test_remove_non_watcher_surfaces_error(self):
        mc = _make_mock_client(cloud=False)
        mc.myself.return_value = {"name": "bwilson"}
        mc.issue_delete_watcher.side_effect = Exception("404 Not Found")
        result, _ = _run(["remove", "TEST-1"], mc)
        assert result.exit_code == 1
        assert "Failed to remove watcher" in result.output
        assert "404" in result.output
```

**Step 2: Run and verify FAIL**

```bash
uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_watchers.py::TestWatchersRemove -v --no-header
```

Expected: all FAIL with `NotImplementedError` from `remove`.

**Step 3: Implement `remove`**

Replace the `remove` stub:

```python
@cli.command()
@click.argument("issue_key")
@click.option("--user", default="me", help="Username, accountId, email, or 'me' (default: me)")
@click.option("--dry-run", is_flag=True, help="Show what would be removed")
@click.pass_context
def remove(ctx, issue_key: str, user: str, dry_run: bool):
    """Remove a watcher from an issue (default: yourself).

    ISSUE_KEY: The Jira issue key (e.g. PROJ-123)

    Removing yourself requires only Browse Projects; removing someone else
    requires Manage Watchers. Removing a non-watcher returns 404 — surfaced
    as a clean error, not a silent success.

    Examples:

      jira-watchers remove PROJ-123

      jira-watchers remove PROJ-123 --user asmith --dry-run
    """
    ctx.obj["client"].with_context(issue_key=issue_key)
    client = ctx.obj["client"]

    try:
        identifier, is_acct = _resolve_watcher_identifier(client, user)
        suffix = " (you)" if user.lower() == "me" else ""

        if dry_run:
            warning("DRY RUN - No watcher will be removed")
            print(f"Would remove {identifier}{suffix} from {issue_key}")
            return

        kwargs = _watcher_api_arg(client, identifier, is_acct)
        client.issue_delete_watcher(issue_key, **kwargs)

        if ctx.obj["json"]:
            print(format_json({"key": issue_key, "user": identifier, "removed": True}))
        elif ctx.obj["quiet"]:
            print("ok")
        else:
            success(f"Removed watcher from {issue_key}: {identifier}{suffix}")

    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to remove watcher: {e}")
        sys.exit(1)
```

Add the helper above `list_watchers` (Task 9 covers its own tests, but a minimal version is needed here so the remove tests pass). Add below `_resolve_watcher_identifier`:

```python
def _watcher_api_arg(client, identifier: str, is_account_id_value: bool) -> dict:
    """Return the keyword arg dict for issue_delete_watcher.

    DC takes ?username=...; Cloud takes ?accountId=.... atlassian-python-api
    exposes both as keyword args; pick based on the resolved identifier
    shape (an account-id-shaped string means Cloud/accountId).
    """
    if is_account_id_value:
        return {"account_id": identifier}
    return {"username": identifier}
```

> Note: `atlassian-python-api`'s `issue_delete_watcher` accepts `username=` and `account_id=` kwargs. If this signature is not verified in the installed version, fall back to raw REST: `client.delete(f"rest/api/2/issue/{issue_key}/watchers", params=kwargs_with_camelcase)` with `username` or `accountId` as the param key, and state the fallback explicitly in code review.

**Step 4: Run and verify PASS**

```bash
uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_watchers.py::TestWatchersRemove -v --no-header
```

Expected: PASS.

**Step 5: Commit**

```bash
git add tests/test_watchers.py skills/jira-communication/scripts/utility/jira-watchers.py
git commit -m "feat(watchers): implement remove subcommand with --dry-run and error surfacing"
```

---

### Task 9: `remove` — DC vs Cloud query-param helper isolation

**Files:**
- Modify: `tests/test_watchers.py`

**Step 1: Write failing tests**

Append:

```python
# ═══════════════════════════════════════════════════════════════════════════════
# Tests: _watcher_api_arg helper (pure)
# ═══════════════════════════════════════════════════════════════════════════════


class TestWatcherApiArg:
    def test_dc_username(self):
        mc = _make_mock_client(cloud=False)
        assert _watchers_mod._watcher_api_arg(mc, "jdoe", False) == {"username": "jdoe"}

    def test_cloud_account_id(self):
        mc = _make_mock_client(cloud=True)
        acct = "557058:d5765ebc-27de-4ce3-b520-a77a87e5e99a"
        assert _watchers_mod._watcher_api_arg(mc, acct, True) == {"account_id": acct}


class TestWatchersRemoveCloud:
    def test_remove_cloud_passes_account_id(self):
        mc = _make_mock_client(cloud=True)
        acct = "557058:d5765ebc-27de-4ce3-b520-a77a87e5e99a"
        result, _ = _run(["remove", "TEST-1", "--user", acct], mc)
        assert result.exit_code == 0, result.output
        mc.issue_delete_watcher.assert_called_once_with("TEST-1", account_id=acct)
```

**Step 2: Run and verify PASS**

```bash
uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_watchers.py::TestWatcherApiArg tests/test_watchers.py::TestWatchersRemoveCloud -v --no-header
```

Expected: PASS (helper already added in Task 8). If FAIL, confirm `_watcher_api_arg` is exported at module scope and not nested inside `remove`.

**Step 3: Commit**

```bash
git add tests/test_watchers.py
git commit -m "test(watchers): pin DC vs Cloud watcher-delete param mapping"
```

---

### Task 10: Register the script in the CLI smoke test

**Files:**
- Modify: `tests/test_cli_smoke.py`

**Step 1: Add module load**

In `tests/test_cli_smoke.py`, locate the block of `_load_script` calls near the top (around line 34–45 based on current file). Add one line at the end of that block:

```python
_watchers_mod = _load_script("jira-watchers", "utility")
```

**Step 2: Add help test**

Inside `class TestHelpOutput` (which contains `test_weblink_help` around line 110), append a new method following the same shape:

```python
    def test_watchers_help(self):
        output = self._run_help(_watchers_mod.cli)
        assert "watcher" in output.lower()
```

**Step 3: Run smoke tests**

```bash
uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_cli_smoke.py -v --no-header
```

Expected: all pass including the new `test_watchers_help`.

**Step 4: Commit**

```bash
git add tests/test_cli_smoke.py
git commit -m "test(watchers): register jira-watchers in CLI smoke test"
```

---

### Task 11: Update SKILL.md with the new script

**Files:**
- Modify: `skills/jira-communication/SKILL.md`

**Step 1: Update the Utility scripts line**

On line 25 of `SKILL.md`, the current line is:

```
**Utility**: `jira-user.py` (get/search/me), `jira-fields.py` (search/types), `jira-link.py`, `jira-weblink.py` (web link CRUD), `jira-worklog-query.py`
```

Change it to:

```
**Utility**: `jira-user.py` (get/search/me), `jira-fields.py` (search/types), `jira-link.py`, `jira-weblink.py` (web link CRUD), `jira-watchers.py` (watcher CRUD), `jira-worklog-query.py`
```

**Step 2: Add Common Tasks examples**

In the Common Tasks section, after the `jira-weblink.py` block (around line 79), append:

```bash
# Watchers (self-subscribe, subscribe stakeholders, unsubscribe)
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-watchers.py list PROJ-123
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-watchers.py add PROJ-123
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-watchers.py add PROJ-123 --user product.owner
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-watchers.py remove PROJ-123
```

**Step 3: Commit**

```bash
git add skills/jira-communication/SKILL.md
git commit -m "docs(watchers): document jira-watchers in SKILL.md"
```

---

### Task 12: Full lint + security + test sweep

**Files:** none modified by the task itself; may auto-fix lint findings in `jira-watchers.py` or `test_watchers.py`.

Apply `@superpowers:verification-before-completion` — run each command and confirm output before claiming done.

**Step 1: Pre-commit smoke check**

```bash
uv run skills/jira-communication/scripts/core/jira-validate.py --help
uv run skills/jira-communication/scripts/utility/jira-watchers.py --help
```

Expected: both print their help banner with exit code 0.

**Step 2: Ruff**

```bash
uv run --no-project --with ruff ruff check skills/jira-communication/scripts/utility/jira-watchers.py tests/test_watchers.py
```

Expected: `All checks passed!`. If fixes are reported, run `ruff check --fix` on the same files, re-run the check, and commit any resulting changes with `style(watchers): apply ruff autofixes`.

**Step 3: Bandit**

```bash
uv run --no-project --with bandit bandit -r skills/jira-communication/scripts/ scripts/ -c pyproject.toml --severity-level medium
```

Expected: no issues identified at medium+ severity.

**Step 4: Full pytest**

```bash
uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/ -q
```

Expected: all tests pass (existing + new watcher suite + the CLI smoke registration).

**Step 5: Commit any autofixes**

```bash
git status
# If ruff made edits in Step 2, commit them:
git add skills/jira-communication/scripts/utility/jira-watchers.py tests/test_watchers.py
git commit -m "style(watchers): apply ruff autofixes"
```

If nothing changed, skip the commit — do not create an empty commit.

---

## Done criteria

- `jira-watchers.py` exists under `scripts/utility/` with `list`, `add`, `remove` subcommands.
- All new tests in `tests/test_watchers.py` pass.
- `tests/test_cli_smoke.py` includes the watcher help test.
- `SKILL.md` lists the script and gives at least three usage examples.
- Ruff and Bandit are clean; full pytest suite is green.
