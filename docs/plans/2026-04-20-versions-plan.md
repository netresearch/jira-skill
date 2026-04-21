# Project Versions CRUD Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `jira-version.py` — a workflow script with full project-version CRUD (list, get, create, update, release, unrelease, archive, unarchive, move, merge, delete) so release managers can drive the release lifecycle from the shell.

**Architecture:** New script at `skills/jira-communication/scripts/workflow/jira-version.py`, Click group with one subcommand per operation. All updates use a safe-merge pattern (GET then PUT with merged dict) to tolerate deployments that treat PUT as replace. Destructive ops (`delete`, `merge`, `release`, `unrelease`, `archive`, `unarchive`, `update`, `create`, `move`) support `--dry-run`. The `move --after` form builds a full self URL from the configured Jira base URL (`client.url`) rather than accepting a raw URL from the user.

**Tech Stack:** Python 3.10+, click, LazyJiraClient, atlassian-python-api, PEP 723 inline deps.

**Design doc:** `docs/plans/2026-04-20-versions-design.md`

---

### Task 1: Scaffold test file and script skeleton

**Files:**
- Create: `tests/test_version.py`
- Create: `skills/jira-communication/scripts/workflow/jira-version.py`

**Step 1: Create `tests/test_version.py` with loader and helpers**

```python
"""Tests for jira-version.py — project versions CRUD."""

import importlib.util
import json
import sys
from pathlib import Path
from unittest import mock

import click.testing
import pytest

_test_dir = Path(__file__).parent
_scripts_path = _test_dir.parent / "skills" / "jira-communication" / "scripts"
sys.path.insert(0, str(_scripts_path))


def _load_script(name: str = "jira-version", subdir: str = "workflow"):
    path = _scripts_path / subdir / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mod = _load_script()


def _make_mock_client(url: str = "https://jira.example.com"):
    mc = mock.Mock()
    mc.with_context = mock.Mock()
    mc.url = url  # atlassian.Jira exposes .url on the client instance
    return mc


def _run(args, mock_client=None):
    if mock_client is None:
        mock_client = _make_mock_client()
    runner = click.testing.CliRunner()
    with mock.patch.object(_mod, "LazyJiraClient", return_value=mock_client):
        result = runner.invoke(_mod.cli, args)
    return result, mock_client


def _make_version(
    vid: str = "10042",
    name: str = "1.4.0",
    project: str = "PROJ",
    released: bool = False,
    archived: bool = False,
    description: str | None = None,
    start_date: str | None = None,
    release_date: str | None = None,
) -> dict:
    """Build a version dict matching the Jira REST API shape."""
    v = {
        "id": vid,
        "name": name,
        "projectId": 10000,
        "project": project,
        "released": released,
        "archived": archived,
        "self": f"https://jira.example.com/rest/api/2/version/{vid}",
    }
    if description is not None:
        v["description"] = description
    if start_date is not None:
        v["startDate"] = start_date
    if release_date is not None:
        v["releaseDate"] = release_date
    return v
```

**Step 2: Create `skills/jira-communication/scripts/workflow/jira-version.py`**

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "atlassian-python-api>=3.41.0,<4",
#     "click>=8.1.0,<9",
# ]
# ///
"""Jira project version operations - list, get, create, update, release lifecycle, move, merge, delete."""

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
from lib.client import LazyJiraClient
from lib.output import error, format_output, format_table, success, warning


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
    """Jira project version operations.

    Manage the release lifecycle: list, create, release, archive, merge, delete versions.
    """
    ctx.ensure_object(dict)
    ctx.obj["json"] = output_json
    ctx.obj["quiet"] = quiet
    ctx.obj["debug"] = debug
    ctx.obj["client"] = LazyJiraClient(env_file=env_file, profile=profile)


# All subcommands are stubs. TDD will flesh them out task by task.


@cli.command("list")
@click.argument("project_key")
@click.pass_context
def list_versions(ctx, project_key: str):
    """List versions in a project."""
    raise NotImplementedError


@cli.command()
@click.argument("version")
@click.pass_context
def get(ctx, version: str):
    """Get a single version by ID or name."""
    raise NotImplementedError


@cli.command()
@click.argument("project_key")
@click.argument("name")
@click.pass_context
def create(ctx, project_key: str, name: str):
    """Create a new version in a project."""
    raise NotImplementedError


@cli.command()
@click.argument("version_id")
@click.pass_context
def update(ctx, version_id: str):
    """Update fields on an existing version (GET + merge + PUT)."""
    raise NotImplementedError


@cli.command()
@click.argument("version_id")
@click.pass_context
def release(ctx, version_id: str):
    """Mark a version released (sets released=true + releaseDate)."""
    raise NotImplementedError


@cli.command()
@click.argument("version_id")
@click.pass_context
def unrelease(ctx, version_id: str):
    """Mark a version unreleased (clears releaseDate)."""
    raise NotImplementedError


@cli.command()
@click.argument("version_id")
@click.pass_context
def archive(ctx, version_id: str):
    """Archive a version (hides it from pickers)."""
    raise NotImplementedError


@cli.command()
@click.argument("version_id")
@click.pass_context
def unarchive(ctx, version_id: str):
    """Unarchive a version."""
    raise NotImplementedError


@cli.command()
@click.argument("version_id")
@click.pass_context
def move(ctx, version_id: str):
    """Reorder a version within its project."""
    raise NotImplementedError


@cli.command()
@click.argument("src_id")
@click.argument("into", type=click.Choice(["INTO"]))
@click.argument("dst_id")
@click.pass_context
def merge(ctx, src_id: str, into: str, dst_id: str):
    """Merge SRC_ID INTO DST_ID (reassign refs + delete source)."""
    raise NotImplementedError


@cli.command()
@click.argument("version_id")
@click.pass_context
def delete(ctx, version_id: str):
    """Delete a version, optionally reassigning fixVersions/versions refs."""
    raise NotImplementedError


if __name__ == "__main__":
    cli()
```

**Step 3: Write the CLI help smoke test**

Add to `tests/test_version.py`:

```python
class TestHelp:
    """All subcommands must respond to --help with exit code 0."""

    @pytest.mark.parametrize(
        "subcmd",
        ["list", "get", "create", "update", "release", "unrelease",
         "archive", "unarchive", "move", "merge", "delete"],
    )
    def test_subcommand_help(self, subcmd):
        runner = click.testing.CliRunner()
        result = runner.invoke(_mod.cli, [subcmd, "--help"])
        assert result.exit_code == 0, result.output

    def test_cli_help_lists_all_subcommands(self):
        runner = click.testing.CliRunner()
        result = runner.invoke(_mod.cli, ["--help"])
        assert result.exit_code == 0
        for sub in ("list", "get", "create", "update", "release", "unrelease",
                    "archive", "unarchive", "move", "merge", "delete"):
            assert sub in result.output
```

**Step 4: Run the smoke test**

Run: `uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_version.py::TestHelp -v --no-header`

Expected: all tests PASS.

**Step 5: Commit**

```bash
git add tests/test_version.py skills/jira-communication/scripts/workflow/jira-version.py
git commit -m "feat(version): scaffold jira-version.py and subcommand stubs"
```

---

### Task 2: `list` subcommand — happy path (flat endpoint)

**Files:**
- Modify: `tests/test_version.py`
- Modify: `skills/jira-communication/scripts/workflow/jira-version.py`

The wrapper `client.get_project_versions(key)` is available per the design doc, but we use the raw HTTP path for consistency with the rest of the script (which needs raw HTTP for `move`, `mergeto`, etc.). Verify via `python -c "import atlassian; import inspect; print(inspect.signature(atlassian.Jira.get_project_versions))"` before choosing; the tests mock the raw `client.get` path.

**Step 1: Write failing list test**

```python
class TestList:
    def test_list_flat_endpoint_default(self):
        mc = _make_mock_client()
        mc.get.return_value = [
            _make_version("10042", "1.4.0", released=False,
                          start_date="2026-05-01", release_date="2026-05-31"),
            _make_version("10048", "1.6.0", released=False),
        ]
        result, _ = _run(["list", "PROJ"], mc)
        assert result.exit_code == 0, result.output
        # The flat endpoint returns ALL versions; filter happens client-side
        mc.get.assert_called_once_with("rest/api/2/project/PROJ/versions")
        assert "10042" in result.output
        assert "1.4.0" in result.output
        # Default --status unreleased: both are unreleased so both show
        assert "10048" in result.output

    def test_list_table_columns(self):
        mc = _make_mock_client()
        mc.get.return_value = [
            _make_version("10042", "1.4.0", released=False,
                          start_date="2026-05-01", release_date="2026-05-31"),
        ]
        result, _ = _run(["list", "PROJ"], mc)
        assert result.exit_code == 0
        # Header keywords
        for header in ("ID", "NAME", "STATUS", "START", "RELEASE", "ISSUES"):
            assert header in result.output
```

**Step 2: Run → verify failure**

Run: `uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_version.py::TestList -v --no-header`

Expected: FAIL with `NotImplementedError`.

**Step 3: Implement helpers and flat-path `list`**

In `jira-version.py`, add above the CLI group:

```python
# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _status_of(v: dict) -> str:
    if v.get("archived"):
        return "archived"
    return "released" if v.get("released") else "unreleased"


def _fmt_list_row(v: dict) -> dict:
    return {
        "ID": v.get("id", ""),
        "NAME": v.get("name", ""),
        "STATUS": _status_of(v),
        "START": v.get("startDate", "-") or "-",
        "RELEASE": v.get("releaseDate", "-") or "-",
        "ISSUES": v.get("issueCount", "-") if v.get("issueCount") is not None else "-",
    }
```

Replace the `list_versions` stub:

```python
@cli.command("list")
@click.argument("project_key")
@click.option("--status", type=click.Choice(["released", "unreleased", "archived", "all"]),
              default="unreleased", help="Filter by status")
@click.option("--query", help="Filter by name substring (paginated endpoint)")
@click.option("--order-by", type=click.Choice(["sequence", "name", "startDate", "releaseDate"]),
              help="Sort order (paginated endpoint)")
@click.pass_context
def list_versions(ctx, project_key: str, status: str, query: str | None, order_by: str | None):
    """List versions in a project.

    Uses the flat `/project/{key}/versions` endpoint unless --query or --order-by
    is provided, in which case it switches to the paginated endpoint.
    """
    client = ctx.obj["client"]
    try:
        if query or order_by:
            versions = _fetch_versions_paginated(client, project_key, status=status,
                                                 query=query, order_by=order_by)
        else:
            versions = client.get(f"rest/api/2/project/{project_key}/versions") or []
            if status != "all":
                versions = [v for v in versions if _status_of(v) == status]

        if ctx.obj["json"]:
            format_output(versions, as_json=True)
            return
        if ctx.obj["quiet"]:
            for v in versions:
                print(v.get("id", ""))
            return

        print(f"{status.capitalize()} versions in {project_key} ({len(versions)}):\n")
        rows = [_fmt_list_row(v) for v in versions]
        print(format_table(rows, columns=["ID", "NAME", "STATUS", "START", "RELEASE", "ISSUES"]))

    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to list versions: {e}")
        sys.exit(1)


def _fetch_versions_paginated(client, project_key, status=None, query=None, order_by=None):
    """Paginated search — DC >=9.x and Cloud only. Filter by name and/or order server-side."""
    raise NotImplementedError  # Implemented in Task 3
```

**Step 4: Run → verify pass**

Run: `uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_version.py::TestList -v --no-header`

Expected: both tests PASS.

**Step 5: Commit**

```bash
git add tests/test_version.py skills/jira-communication/scripts/workflow/jira-version.py
git commit -m "feat(version): implement list with flat endpoint and client-side status filter"
```

---

### Task 3: `list` — paginated endpoint with `--query` / `--order-by`

**Files:**
- Modify: `tests/test_version.py`
- Modify: `skills/jira-communication/scripts/workflow/jira-version.py`

**Step 1: Write failing tests**

```python
class TestListPaginated:
    def test_list_with_query_uses_paginated_endpoint(self):
        mc = _make_mock_client()
        mc.get.return_value = {
            "isLast": True,
            "values": [_make_version("10042", "1.4.0-rc1", released=False)],
        }
        result, _ = _run(["list", "PROJ", "--query", "rc"], mc)
        assert result.exit_code == 0, result.output
        # First positional arg to .get should be the paginated path
        called_path = mc.get.call_args.args[0]
        assert called_path == "rest/api/2/project/PROJ/version"
        called_params = mc.get.call_args.kwargs.get("params", {})
        assert called_params.get("query") == "rc"

    def test_list_with_order_by_uses_paginated_endpoint(self):
        mc = _make_mock_client()
        mc.get.return_value = {"isLast": True, "values": []}
        result, _ = _run(["list", "PROJ", "--order-by", "releaseDate"], mc)
        assert result.exit_code == 0, result.output
        called_params = mc.get.call_args.kwargs.get("params", {})
        assert called_params.get("orderBy") == "releaseDate"

    def test_list_paginated_follows_next_page(self):
        mc = _make_mock_client()
        mc.get.side_effect = [
            {"isLast": False, "values": [_make_version("10042", "1.4.0")], "startAt": 0, "maxResults": 1},
            {"isLast": True, "values": [_make_version("10045", "1.5.0")], "startAt": 1, "maxResults": 1},
        ]
        result, _ = _run(["list", "PROJ", "--query", "1."], mc)
        assert result.exit_code == 0, result.output
        assert mc.get.call_count == 2
        assert "10042" in result.output and "10045" in result.output

    def test_status_all_filters_nothing_on_paginated(self):
        mc = _make_mock_client()
        mc.get.return_value = {
            "isLast": True,
            "values": [
                _make_version("10042", "1.4.0", released=False),
                _make_version("10041", "1.3.0", released=True),
                _make_version("10030", "1.2.0", archived=True),
            ],
        }
        result, _ = _run(["list", "PROJ", "--query", ".", "--status", "all"], mc)
        assert result.exit_code == 0
        for vid in ("10042", "10041", "10030"):
            assert vid in result.output
```

**Step 2: Run → verify failure**

Run: `uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_version.py::TestListPaginated -v --no-header`

Expected: FAIL.

**Step 3: Implement `_fetch_versions_paginated`**

```python
def _fetch_versions_paginated(client, project_key, status=None, query=None, order_by=None):
    """Paginated search via `/project/{key}/version`.

    Availability: Jira Server/DC >=9.x and Jira Cloud. Older DC versions return
    404 — callers should rely on the flat `/project/{key}/versions` endpoint
    and filter client-side when `--query` / `--order-by` are not supplied.
    """
    all_values: list[dict] = []
    start_at = 0
    page_size = 50
    while True:
        params = {"startAt": start_at, "maxResults": page_size}
        if query:
            params["query"] = query
        if order_by:
            params["orderBy"] = order_by
        if status and status != "all":
            params["status"] = status
        page = client.get(f"rest/api/2/project/{project_key}/version", params=params) or {}
        values = page.get("values", [])
        all_values.extend(values)
        if page.get("isLast", True) or not values:
            break
        start_at += len(values) or page_size
    return all_values
```

**Step 4: Run → verify pass**

Run: `uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_version.py::TestListPaginated -v --no-header`

Expected: all PASS.

**Step 5: Commit**

```bash
git add tests/test_version.py skills/jira-communication/scripts/workflow/jira-version.py
git commit -m "feat(version): add paginated list with --query and --order-by"
```

---

### Task 4: `list` — JSON and quiet output modes

**Files:**
- Modify: `tests/test_version.py`

**Step 1: Write failing tests**

```python
class TestListOutputModes:
    def test_list_json_output(self):
        mc = _make_mock_client()
        versions = [_make_version("10042", "1.4.0"), _make_version("10048", "1.6.0")]
        mc.get.return_value = versions
        result, _ = _run(["--json", "list", "PROJ"], mc)
        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)
        assert isinstance(parsed, list)
        assert {v["id"] for v in parsed} == {"10042", "10048"}

    def test_list_quiet_output(self):
        mc = _make_mock_client()
        mc.get.return_value = [_make_version("10042", "1.4.0"), _make_version("10048", "1.6.0")]
        result, _ = _run(["--quiet", "list", "PROJ"], mc)
        assert result.exit_code == 0
        lines = [ln for ln in result.output.strip().splitlines() if ln]
        assert lines == ["10042", "10048"]
```

**Step 2: Run → expected pass (already implemented in Task 2)**

Run: `uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_version.py::TestListOutputModes -v --no-header`

Expected: PASS. If either fails, adjust the `list` subcommand's output branch.

**Step 3: Commit**

```bash
git add tests/test_version.py
git commit -m "test(version): cover list --json and --quiet output modes"
```

---

### Task 5: `get` — by numeric ID

**Files:**
- Modify: `tests/test_version.py`
- Modify: `skills/jira-communication/scripts/workflow/jira-version.py`

**Step 1: Write failing tests**

```python
class TestGetById:
    def test_get_by_id(self):
        mc = _make_mock_client()
        mc.get.return_value = _make_version(
            "10042", "1.4.0", released=False, description="Q2 release",
            start_date="2026-05-01", release_date="2026-05-31",
        )
        result, _ = _run(["get", "10042"], mc)
        assert result.exit_code == 0, result.output
        mc.get.assert_called_once_with("rest/api/2/version/10042")
        assert "1.4.0" in result.output
        assert "Q2 release" in result.output
        assert "2026-05-31" in result.output

    def test_get_by_id_json(self):
        mc = _make_mock_client()
        v = _make_version("10042", "1.4.0")
        mc.get.return_value = v
        result, _ = _run(["--json", "get", "10042"], mc)
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["id"] == "10042"
```

**Step 2: Run → verify failure**

Run: `uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_version.py::TestGetById -v --no-header`

Expected: FAIL.

**Step 3: Implement `get` for numeric IDs**

```python
def _is_numeric_id(s: str) -> bool:
    return s.isdigit()


def _render_version(v: dict, counts: dict | None = None) -> str:
    lines = [
        f"Version {v.get('id', '?')} — {v.get('name', '')}",
        f"  Project:      {v.get('project', v.get('projectId', ''))}",
        f"  Status:       {_status_of(v)}",
        f"  Start:        {v.get('startDate', '-') or '-'}",
        f"  Release:      {v.get('releaseDate', '-') or '-'}",
    ]
    if v.get("description"):
        lines.append(f"  Description:  {v['description']}")
    if counts:
        fixed = counts.get("issuesFixedCount", counts.get("fixed", "?"))
        affected = counts.get("issuesAffectedCount", counts.get("affected", "?"))
        unresolved = counts.get("issuesUnresolvedCount", counts.get("unresolved", "?"))
        lines.append(f"  Issues:       fixed={fixed} affected={affected} unresolved={unresolved}")
    return "\n".join(lines)
```

Replace the `get` stub:

```python
@cli.command()
@click.argument("version")
@click.option("--project", help="Required when VERSION is a name (not an ID)")
@click.option("--counts", is_flag=True, help="Include fixed/affected/unresolved issue counts")
@click.pass_context
def get(ctx, version: str, project: str | None, counts: bool):
    """Get a single version by ID or name."""
    client = ctx.obj["client"]
    try:
        if _is_numeric_id(version):
            v = client.get(f"rest/api/2/version/{version}")
        else:
            v = _resolve_version_by_name(client, version, project)  # implemented in Task 6

        extra = None
        if counts:
            extra = _fetch_counts(client, v["id"])  # implemented in Task 7

        if ctx.obj["json"]:
            payload = dict(v)
            if extra:
                payload["_counts"] = extra
            format_output(payload, as_json=True)
            return
        if ctx.obj["quiet"]:
            print(v.get("id", ""))
            return
        print(_render_version(v, counts=extra))

    except SystemExit:
        raise
    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to get version: {e}")
        sys.exit(1)


def _resolve_version_by_name(client, name, project_key):
    raise NotImplementedError  # Task 6


def _fetch_counts(client, vid):
    raise NotImplementedError  # Task 7
```

**Step 4: Run → verify pass**

Run: `uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_version.py::TestGetById -v --no-header`

Expected: PASS.

**Step 5: Commit**

```bash
git add tests/test_version.py skills/jira-communication/scripts/workflow/jira-version.py
git commit -m "feat(version): implement get by numeric ID"
```

---

### Task 6: `get` — by name with `--project`

**Files:**
- Modify: `tests/test_version.py`
- Modify: `skills/jira-communication/scripts/workflow/jira-version.py`

**Step 1: Write failing tests**

```python
class TestGetByName:
    def test_get_by_name_requires_project(self):
        mc = _make_mock_client()
        result, _ = _run(["get", "1.4.0"], mc)
        assert result.exit_code != 0
        assert "--project" in result.output.lower() or "project" in result.output.lower()

    def test_get_by_name_resolves(self):
        mc = _make_mock_client()
        mc.get.return_value = [
            _make_version("10041", "1.3.0"),
            _make_version("10042", "1.4.0"),
        ]
        result, _ = _run(["get", "1.4.0", "--project", "PROJ"], mc)
        assert result.exit_code == 0, result.output
        mc.get.assert_called_once_with("rest/api/2/project/PROJ/versions")
        assert "10042" in result.output

    def test_get_by_name_no_match(self):
        mc = _make_mock_client()
        mc.get.return_value = [_make_version("10041", "1.3.0")]
        result, _ = _run(["get", "1.4.0", "--project", "PROJ"], mc)
        assert result.exit_code != 0
        assert "not found" in result.output.lower() or "no version" in result.output.lower()

    def test_get_by_name_ambiguous(self):
        mc = _make_mock_client()
        mc.get.return_value = [
            _make_version("10042", "1.4.0"),
            _make_version("10043", "1.4.0"),  # duplicate name
        ]
        result, _ = _run(["get", "1.4.0", "--project", "PROJ"], mc)
        assert result.exit_code != 0
        assert "multiple" in result.output.lower() or "ambiguous" in result.output.lower()
```

**Step 2: Run → verify failure**

Run: `uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_version.py::TestGetByName -v --no-header`

Expected: FAIL.

**Step 3: Implement `_resolve_version_by_name`**

```python
def _resolve_version_by_name(client, name: str, project_key: str | None) -> dict:
    if not project_key:
        error("--project is required when looking up a version by name")
        sys.exit(2)
    versions = client.get(f"rest/api/2/project/{project_key}/versions") or []
    matches = [v for v in versions if v.get("name") == name]
    if not matches:
        error(f'No version named "{name}" found in {project_key}')
        sys.exit(1)
    if len(matches) > 1:
        ids = ", ".join(v.get("id", "?") for v in matches)
        error(f'Multiple versions named "{name}" in {project_key} (ids: {ids})')
        sys.exit(1)
    return matches[0]
```

**Step 4: Run → verify pass**

Run: `uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_version.py::TestGetByName -v --no-header`

Expected: PASS.

**Step 5: Commit**

```bash
git add tests/test_version.py skills/jira-communication/scripts/workflow/jira-version.py
git commit -m "feat(version): resolve version by name with --project"
```

---

### Task 7: `get --counts`

**Files:**
- Modify: `tests/test_version.py`
- Modify: `skills/jira-communication/scripts/workflow/jira-version.py`

**Step 1: Write failing test**

```python
class TestGetCounts:
    def test_counts_fetches_both_endpoints(self):
        mc = _make_mock_client()
        # Three GETs: version, relatedIssueCounts, unresolvedIssueCount
        mc.get.side_effect = [
            _make_version("10042", "1.4.0"),
            {"issuesFixedCount": 12, "issuesAffectedCount": 3},
            {"issuesUnresolvedCount": 4},
        ]
        result, _ = _run(["get", "10042", "--counts"], mc)
        assert result.exit_code == 0, result.output
        assert mc.get.call_count == 3
        paths = [c.args[0] for c in mc.get.call_args_list]
        assert paths[0] == "rest/api/2/version/10042"
        assert paths[1] == "rest/api/2/version/10042/relatedIssueCounts"
        assert paths[2] == "rest/api/2/version/10042/unresolvedIssueCount"
        assert "fixed=12" in result.output
        assert "affected=3" in result.output
        assert "unresolved=4" in result.output
```

**Step 2: Run → verify failure**

Run: `uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_version.py::TestGetCounts -v --no-header`

Expected: FAIL.

**Step 3: Implement `_fetch_counts`**

```python
def _fetch_counts(client, vid: str) -> dict:
    related = client.get(f"rest/api/2/version/{vid}/relatedIssueCounts") or {}
    unresolved = client.get(f"rest/api/2/version/{vid}/unresolvedIssueCount") or {}
    return {**related, **unresolved}
```

**Step 4: Run → verify pass**

Run: `uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_version.py::TestGetCounts -v --no-header`

Expected: PASS.

**Step 5: Commit**

```bash
git add tests/test_version.py skills/jira-communication/scripts/workflow/jira-version.py
git commit -m "feat(version): add --counts to get subcommand"
```

---

### Task 8: Date validator helper

**Files:**
- Modify: `tests/test_version.py`
- Modify: `skills/jira-communication/scripts/workflow/jira-version.py`

**Step 1: Write failing tests**

```python
class TestValidateIsoDate:
    def test_accepts_iso_date(self):
        assert _mod._validate_iso_date("2026-05-31") == "2026-05-31"

    def test_accepts_leap_day(self):
        assert _mod._validate_iso_date("2024-02-29") == "2024-02-29"

    def test_rejects_invalid_day(self):
        with pytest.raises(click.BadParameter):
            _mod._validate_iso_date("2026-02-30")

    def test_rejects_timestamp(self):
        with pytest.raises(click.BadParameter):
            _mod._validate_iso_date("2026-05-31T00:00:00Z")

    def test_rejects_garbage(self):
        with pytest.raises(click.BadParameter):
            _mod._validate_iso_date("tomorrow")

    def test_rejects_slashes(self):
        with pytest.raises(click.BadParameter):
            _mod._validate_iso_date("2026/05/31")
```

**Step 2: Run → verify failure**

Run: `uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_version.py::TestValidateIsoDate -v --no-header`

Expected: FAIL.

**Step 3: Implement**

```python
import re
from datetime import date as _date

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _validate_iso_date(s: str) -> str:
    """Validate an ISO date string (YYYY-MM-DD) and return it unchanged.

    Jira rejects full timestamps like `2026-05-31T00:00:00Z` with a 400 on
    version start/release dates. This helper enforces the date-only shape
    client-side with a clear error.
    """
    if not isinstance(s, str) or not _ISO_DATE_RE.match(s):
        raise click.BadParameter(
            f'Expected YYYY-MM-DD, got "{s}". Timestamps are not allowed.'
        )
    try:
        y, m, d = (int(p) for p in s.split("-"))
        _date(y, m, d)
    except ValueError as e:
        raise click.BadParameter(f'Invalid date "{s}": {e}') from e
    return s
```

**Step 4: Run → verify pass**

Run: `uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_version.py::TestValidateIsoDate -v --no-header`

Expected: PASS.

**Step 5: Commit**

```bash
git add tests/test_version.py skills/jira-communication/scripts/workflow/jira-version.py
git commit -m "feat(version): add ISO date validator helper"
```

---

### Task 9: `create` subcommand

**Files:**
- Modify: `tests/test_version.py`
- Modify: `skills/jira-communication/scripts/workflow/jira-version.py`

**Step 1: Write failing tests**

```python
class TestCreate:
    def test_create_minimal(self):
        mc = _make_mock_client()
        mc.post.return_value = _make_version("10042", "1.4.0")
        result, _ = _run(["create", "PROJ", "1.4.0"], mc)
        assert result.exit_code == 0, result.output
        mc.post.assert_called_once()
        path = mc.post.call_args.args[0]
        assert path == "rest/api/2/version"
        body = mc.post.call_args.kwargs.get("data") or mc.post.call_args.kwargs.get("json")
        assert body["name"] == "1.4.0"
        assert body["project"] == "PROJ"
        assert body.get("released", False) is False
        assert body.get("archived", False) is False

    def test_create_with_dates_and_description(self):
        mc = _make_mock_client()
        mc.post.return_value = _make_version("10042", "1.4.0")
        result, _ = _run(
            ["create", "PROJ", "1.4.0",
             "--description", "Q2 2026",
             "--start-date", "2026-05-01",
             "--release-date", "2026-05-31"],
            mc,
        )
        assert result.exit_code == 0, result.output
        body = mc.post.call_args.kwargs.get("data") or mc.post.call_args.kwargs.get("json")
        assert body["description"] == "Q2 2026"
        assert body["startDate"] == "2026-05-01"
        assert body["releaseDate"] == "2026-05-31"

    def test_create_released_and_archived_flags(self):
        mc = _make_mock_client()
        mc.post.return_value = _make_version("10042", "1.4.0", released=True, archived=True)
        result, _ = _run(
            ["create", "PROJ", "1.4.0", "--released", "--archived",
             "--release-date", "2026-05-31"],
            mc,
        )
        assert result.exit_code == 0, result.output
        body = mc.post.call_args.kwargs.get("data") or mc.post.call_args.kwargs.get("json")
        assert body["released"] is True
        assert body["archived"] is True

    def test_create_rejects_bad_date(self):
        mc = _make_mock_client()
        result, _ = _run(["create", "PROJ", "1.4.0", "--release-date", "2026/05/31"], mc)
        assert result.exit_code != 0
        assert "YYYY-MM-DD" in result.output or "Invalid date" in result.output
        mc.post.assert_not_called()

    def test_create_dry_run(self):
        mc = _make_mock_client()
        result, _ = _run(["create", "PROJ", "1.4.0", "--release-date", "2026-05-31", "--dry-run"], mc)
        assert result.exit_code == 0
        mc.post.assert_not_called()
        assert "DRY RUN" in result.output
        assert "1.4.0" in result.output
```

**Step 2: Run → verify failure**

Run: `uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_version.py::TestCreate -v --no-header`

Expected: FAIL.

**Step 3: Implement `create`**

Replace the `create` stub:

```python
@cli.command()
@click.argument("project_key")
@click.argument("name")
@click.option("--description", help="Version description (plain text or wiki markup)")
@click.option("--start-date", help="Start date YYYY-MM-DD")
@click.option("--release-date", help="Release date YYYY-MM-DD")
@click.option("--released", is_flag=True, help="Mark as released on creation")
@click.option("--archived", is_flag=True, help="Mark as archived on creation")
@click.option("--dry-run", is_flag=True, help="Show what would be created")
@click.pass_context
def create(ctx, project_key, name, description, start_date, release_date, released, archived, dry_run):
    """Create a new version in a project."""
    client = ctx.obj["client"]
    payload = {"name": name, "project": project_key, "released": released, "archived": archived}
    if description:
        payload["description"] = description
    if start_date:
        payload["startDate"] = _validate_iso_date(start_date)
    if release_date:
        payload["releaseDate"] = _validate_iso_date(release_date)

    if dry_run:
        warning("DRY RUN - No version will be created")
        print(f"Would POST rest/api/2/version with:\n  {payload}")
        return

    try:
        created = client.post("rest/api/2/version", data=payload)
        vid = (created or {}).get("id", "?")

        if ctx.obj["json"]:
            format_output(created, as_json=True)
        elif ctx.obj["quiet"]:
            print(vid)
        else:
            extra = f" (release {release_date})" if release_date else ""
            success(f'Created version {vid} "{name}" in {project_key}{extra}')

    except Exception as e:
        if ctx.obj["debug"]:
            raise
        # Delegate 409 handling to Task 10
        error(f"Failed to create version: {e}")
        sys.exit(1)
```

**Step 4: Run → verify pass**

Run: `uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_version.py::TestCreate -v --no-header`

Expected: PASS.

**Step 5: Commit**

```bash
git add tests/test_version.py skills/jira-communication/scripts/workflow/jira-version.py
git commit -m "feat(version): implement create with dates, flags, and --dry-run"
```

---

### Task 10: `create` — surface 409 duplicate-name as a clean error

**Files:**
- Modify: `tests/test_version.py`
- Modify: `skills/jira-communication/scripts/workflow/jira-version.py`

**Step 1: Write failing test**

```python
class TestCreateConflict:
    def test_duplicate_name_409(self):
        mc = _make_mock_client()
        # atlassian-python-api raises HTTPError on 4xx; simulate that shape
        from requests.exceptions import HTTPError
        from requests import Response
        resp = Response()
        resp.status_code = 409
        resp._content = b'{"errors":{"name":"A version with this name already exists."}}'
        err = HTTPError("409 Conflict", response=resp)
        mc.post.side_effect = err

        result, _ = _run(["create", "PROJ", "1.4.0"], mc)
        assert result.exit_code != 0
        # Clean message, not a stack trace
        assert "already exists" in result.output.lower()
        assert "1.4.0" in result.output
        assert "PROJ" in result.output
```

**Step 2: Run → verify failure**

Run: `uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_version.py::TestCreateConflict -v --no-header`

Expected: FAIL.

**Step 3: Add 409 handling**

Update the `except` block in `create`:

```python
    except Exception as e:
        if ctx.obj["debug"]:
            raise
        status = getattr(getattr(e, "response", None), "status_code", None)
        if status == 409:
            error(f'Version "{name}" already exists in {project_key}')
        else:
            error(f"Failed to create version: {e}")
        sys.exit(1)
```

**Step 4: Run → verify pass**

Run: `uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_version.py::TestCreateConflict -v --no-header`

Expected: PASS.

**Step 5: Commit**

```bash
git add tests/test_version.py skills/jira-communication/scripts/workflow/jira-version.py
git commit -m "feat(version): surface 409 duplicate-name as clear error"
```

---

### Task 11: Safe-merge update helper

**Files:**
- Modify: `tests/test_version.py`
- Modify: `skills/jira-communication/scripts/workflow/jira-version.py`

**Step 1: Write failing tests for `_safe_update_version`**

```python
class TestSafeUpdate:
    def test_merges_patch_onto_current(self):
        mc = _make_mock_client()
        mc.get.return_value = _make_version(
            "10042", "1.4.0", released=False,
            description="old", start_date="2026-05-01", release_date="2026-05-31",
        )
        mc.put.return_value = {}
        _mod._safe_update_version(mc, "10042", description="new", releaseDate="2026-06-07")

        mc.get.assert_called_once_with("rest/api/2/version/10042")
        path = mc.put.call_args.args[0]
        assert path == "rest/api/2/version/10042"
        body = mc.put.call_args.kwargs.get("data") or mc.put.call_args.kwargs.get("json")
        assert body["description"] == "new"
        assert body["releaseDate"] == "2026-06-07"
        # Untouched fields retained from GET
        assert body["name"] == "1.4.0"
        assert body["startDate"] == "2026-05-01"
        assert body["released"] is False

    def test_explicit_none_sets_null(self):
        """Clearing a field (e.g. unrelease) means explicit None -> null in the PUT body."""
        mc = _make_mock_client()
        mc.get.return_value = _make_version(
            "10042", "1.4.0", released=True, release_date="2026-05-31",
        )
        mc.put.return_value = {}
        _mod._safe_update_version(mc, "10042", released=False, releaseDate=None)
        body = mc.put.call_args.kwargs.get("data") or mc.put.call_args.kwargs.get("json")
        assert body["released"] is False
        assert "releaseDate" in body
        assert body["releaseDate"] is None

    def test_does_not_send_unset_kwargs(self):
        """Kwargs not passed by the caller must not appear in the patch."""
        mc = _make_mock_client()
        mc.get.return_value = _make_version("10042", "1.4.0", description="orig")
        mc.put.return_value = {}
        _mod._safe_update_version(mc, "10042", name="1.4.0-rc")
        body = mc.put.call_args.kwargs.get("data") or mc.put.call_args.kwargs.get("json")
        assert body["name"] == "1.4.0-rc"
        # description retained from GET, not cleared
        assert body["description"] == "orig"
```

**Step 2: Run → verify failure**

Run: `uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_version.py::TestSafeUpdate -v --no-header`

Expected: FAIL.

**Step 3: Implement `_safe_update_version`**

```python
# Sentinel distinguishes "caller did not provide this key" from "caller passed None to clear".
_UNSET = object()


def _safe_update_version(client, vid: str, **patch) -> dict:
    """Safely update a version by GET + dict-merge + PUT.

    Why: Jira's `PUT /version/{id}` is treated as *replace* on some Server/DC
    deployments (and a few Cloud tenants), meaning any field omitted from the
    body is cleared. To avoid accidentally wiping `description`, `startDate`,
    etc. when the user only wants to update one field, we always fetch the
    current version first and merge the caller's patch onto it before PUTting.

    Any kwarg whose value is not the _UNSET sentinel is applied verbatim. Pass
    an explicit ``None`` to clear a field (e.g. `releaseDate=None` on unrelease);
    the null is preserved in the PUT body.
    """
    current = client.get(f"rest/api/2/version/{vid}") or {}
    merged = dict(current)
    for key, value in patch.items():
        if value is _UNSET:
            continue
        merged[key] = value
    # Strip server-managed fields we shouldn't echo back
    for ro in ("self", "operations", "projectId"):
        merged.pop(ro, None)
    return client.put(f"rest/api/2/version/{vid}", data=merged)
```

**Step 4: Run → verify pass**

Run: `uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_version.py::TestSafeUpdate -v --no-header`

Expected: PASS.

**Step 5: Commit**

```bash
git add tests/test_version.py skills/jira-communication/scripts/workflow/jira-version.py
git commit -m "feat(version): add safe-merge update helper (GET + merge + PUT)"
```

---

### Task 12: `update` subcommand

**Files:**
- Modify: `tests/test_version.py`
- Modify: `skills/jira-communication/scripts/workflow/jira-version.py`

**Step 1: Write failing tests**

```python
class TestUpdate:
    def test_update_description(self):
        mc = _make_mock_client()
        mc.get.return_value = _make_version("10042", "1.4.0", description="old")
        mc.put.return_value = {}
        result, _ = _run(["update", "10042", "--description", "new"], mc)
        assert result.exit_code == 0, result.output
        body = mc.put.call_args.kwargs.get("data") or mc.put.call_args.kwargs.get("json")
        assert body["description"] == "new"
        assert body["name"] == "1.4.0"  # retained

    def test_update_name(self):
        mc = _make_mock_client()
        mc.get.return_value = _make_version("10042", "1.4.0")
        mc.put.return_value = {}
        result, _ = _run(["update", "10042", "--name", "1.4.0-final"], mc)
        assert result.exit_code == 0
        body = mc.put.call_args.kwargs.get("data") or mc.put.call_args.kwargs.get("json")
        assert body["name"] == "1.4.0-final"

    def test_update_dates(self):
        mc = _make_mock_client()
        mc.get.return_value = _make_version("10042", "1.4.0")
        mc.put.return_value = {}
        result, _ = _run(
            ["update", "10042", "--start-date", "2026-05-01", "--release-date", "2026-06-07"], mc
        )
        assert result.exit_code == 0
        body = mc.put.call_args.kwargs.get("data") or mc.put.call_args.kwargs.get("json")
        assert body["startDate"] == "2026-05-01"
        assert body["releaseDate"] == "2026-06-07"

    def test_update_released_flag(self):
        mc = _make_mock_client()
        mc.get.return_value = _make_version("10042", "1.4.0", released=False)
        mc.put.return_value = {}
        result, _ = _run(["update", "10042", "--released"], mc)
        assert result.exit_code == 0
        body = mc.put.call_args.kwargs.get("data") or mc.put.call_args.kwargs.get("json")
        assert body["released"] is True

    def test_update_unreleased_clears_release_date(self):
        mc = _make_mock_client()
        mc.get.return_value = _make_version("10042", "1.4.0", released=True, release_date="2026-05-31")
        mc.put.return_value = {}
        result, _ = _run(["update", "10042", "--unreleased"], mc)
        assert result.exit_code == 0
        body = mc.put.call_args.kwargs.get("data") or mc.put.call_args.kwargs.get("json")
        assert body["released"] is False
        assert body["releaseDate"] is None

    def test_update_dry_run(self):
        mc = _make_mock_client()
        mc.get.return_value = _make_version("10042", "1.4.0")
        result, _ = _run(["update", "10042", "--description", "new", "--dry-run"], mc)
        assert result.exit_code == 0
        mc.put.assert_not_called()
        assert "DRY RUN" in result.output

    def test_update_rejects_bad_date(self):
        mc = _make_mock_client()
        result, _ = _run(["update", "10042", "--release-date", "tomorrow"], mc)
        assert result.exit_code != 0
        mc.put.assert_not_called()
```

**Step 2: Run → verify failure**

Run: `uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_version.py::TestUpdate -v --no-header`

Expected: FAIL.

**Step 3: Implement `update`**

Replace the `update` stub:

```python
@cli.command()
@click.argument("version_id")
@click.option("--name", help="New name")
@click.option("--description", help="New description")
@click.option("--start-date", help="New start date YYYY-MM-DD")
@click.option("--release-date", help="New release date YYYY-MM-DD")
@click.option("--released/--unreleased", default=None, help="Mark released or unreleased")
@click.option("--archived/--unarchived", default=None, help="Mark archived or unarchived")
@click.option("--dry-run", is_flag=True, help="Show what would be updated")
@click.pass_context
def update(ctx, version_id, name, description, start_date, release_date,
           released, archived, dry_run):
    """Update fields on an existing version (safe-merge: GET + merge + PUT)."""
    client = ctx.obj["client"]

    patch: dict = {}
    if name is not None:
        patch["name"] = name
    if description is not None:
        patch["description"] = description
    if start_date is not None:
        patch["startDate"] = _validate_iso_date(start_date)
    if release_date is not None:
        patch["releaseDate"] = _validate_iso_date(release_date)
    if released is True:
        patch["released"] = True
    elif released is False:
        # --unreleased: clear releaseDate unless caller also set --release-date
        patch["released"] = False
        patch.setdefault("releaseDate", None)
    if archived is True:
        patch["archived"] = True
    elif archived is False:
        patch["archived"] = False

    if not patch:
        error("No fields to update. Provide at least one of --name / --description / --start-date / --release-date / --released/--unreleased / --archived/--unarchived")
        sys.exit(2)

    if dry_run:
        warning("DRY RUN - No version will be updated")
        print(f"Would PUT rest/api/2/version/{version_id} with patch:\n  {patch}")
        return

    try:
        _safe_update_version(client, version_id, **patch)
        if ctx.obj["json"]:
            format_output({"id": version_id, "updated": True, "patch": patch}, as_json=True)
        elif ctx.obj["quiet"]:
            print("ok")
        else:
            success(f"Updated version {version_id}")
    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to update version: {e}")
        sys.exit(1)
```

**Step 4: Run → verify pass**

Run: `uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_version.py::TestUpdate -v --no-header`

Expected: PASS.

**Step 5: Commit**

```bash
git add tests/test_version.py skills/jira-communication/scripts/workflow/jira-version.py
git commit -m "feat(version): wire update CLI flags to safe-merge helper"
```

---

### Task 13: `release` and `unrelease` subcommands

**Files:**
- Modify: `tests/test_version.py`
- Modify: `skills/jira-communication/scripts/workflow/jira-version.py`

**Step 1: Write failing tests**

```python
class TestReleaseUnrelease:
    def test_release_with_date(self):
        mc = _make_mock_client()
        mc.get.return_value = _make_version("10042", "1.4.0", released=False)
        mc.put.return_value = {}
        result, _ = _run(["release", "10042", "--release-date", "2026-05-31"], mc)
        assert result.exit_code == 0, result.output
        body = mc.put.call_args.kwargs.get("data") or mc.put.call_args.kwargs.get("json")
        assert body["released"] is True
        assert body["releaseDate"] == "2026-05-31"

    def test_release_defaults_to_today(self):
        mc = _make_mock_client()
        mc.get.return_value = _make_version("10042", "1.4.0", released=False)
        mc.put.return_value = {}
        result, _ = _run(["release", "10042"], mc)
        assert result.exit_code == 0, result.output
        from datetime import date
        body = mc.put.call_args.kwargs.get("data") or mc.put.call_args.kwargs.get("json")
        assert body["released"] is True
        assert body["releaseDate"] == date.today().isoformat()

    def test_unrelease_clears_release_date(self):
        mc = _make_mock_client()
        mc.get.return_value = _make_version(
            "10042", "1.4.0", released=True, release_date="2026-05-31"
        )
        mc.put.return_value = {}
        result, _ = _run(["unrelease", "10042"], mc)
        assert result.exit_code == 0, result.output
        body = mc.put.call_args.kwargs.get("data") or mc.put.call_args.kwargs.get("json")
        assert body["released"] is False
        assert body["releaseDate"] is None

    def test_release_dry_run(self):
        mc = _make_mock_client()
        mc.get.return_value = _make_version("10042", "1.4.0")
        result, _ = _run(["release", "10042", "--release-date", "2026-05-31", "--dry-run"], mc)
        assert result.exit_code == 0
        mc.put.assert_not_called()
        assert "DRY RUN" in result.output
```

**Step 2: Run → verify failure**

Run: `uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_version.py::TestReleaseUnrelease -v --no-header`

Expected: FAIL.

**Step 3: Implement**

Replace the `release` and `unrelease` stubs:

```python
@cli.command()
@click.argument("version_id")
@click.option("--release-date", help="Release date YYYY-MM-DD (default: today)")
@click.option("--dry-run", is_flag=True, help="Show what would change")
@click.pass_context
def release(ctx, version_id, release_date, dry_run):
    """Mark a version released (sets released=true + releaseDate)."""
    from datetime import date as _d
    rdate = _validate_iso_date(release_date) if release_date else _d.today().isoformat()
    patch = {"released": True, "releaseDate": rdate}

    if dry_run:
        warning("DRY RUN - No version will be updated")
        print(f"Would release {version_id} on {rdate}")
        return

    client = ctx.obj["client"]
    try:
        _safe_update_version(client, version_id, **patch)
        success(f"Released version {version_id} on {rdate}")
    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to release version: {e}")
        sys.exit(1)


@cli.command()
@click.argument("version_id")
@click.option("--dry-run", is_flag=True, help="Show what would change")
@click.pass_context
def unrelease(ctx, version_id, dry_run):
    """Mark a version unreleased (clears releaseDate)."""
    patch = {"released": False, "releaseDate": None}

    if dry_run:
        warning("DRY RUN - No version will be updated")
        print(f"Would unrelease {version_id} (releaseDate cleared)")
        return

    client = ctx.obj["client"]
    try:
        _safe_update_version(client, version_id, **patch)
        success(f"Unreleased version {version_id}")
    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to unrelease version: {e}")
        sys.exit(1)
```

Note on `releaseDate: null`: the design doc warns that some deployments may reject explicit null. If integration testing surfaces a 400, fall back to omitting `releaseDate` from the merged body (drop it in `_safe_update_version` when the value is `None` for this field only). Keep the behavior covered by tests either way.

**Step 4: Run → verify pass**

Run: `uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_version.py::TestReleaseUnrelease -v --no-header`

Expected: PASS.

**Step 5: Commit**

```bash
git add tests/test_version.py skills/jira-communication/scripts/workflow/jira-version.py
git commit -m "feat(version): add release and unrelease subcommands"
```

---

### Task 14: `archive` and `unarchive` subcommands

**Files:**
- Modify: `tests/test_version.py`
- Modify: `skills/jira-communication/scripts/workflow/jira-version.py`

**Step 1: Write failing tests**

```python
class TestArchiveUnarchive:
    def test_archive(self):
        mc = _make_mock_client()
        mc.get.return_value = _make_version("10042", "1.4.0", archived=False)
        mc.put.return_value = {}
        result, _ = _run(["archive", "10042"], mc)
        assert result.exit_code == 0, result.output
        body = mc.put.call_args.kwargs.get("data") or mc.put.call_args.kwargs.get("json")
        assert body["archived"] is True
        # Other fields untouched
        assert body["name"] == "1.4.0"

    def test_unarchive(self):
        mc = _make_mock_client()
        mc.get.return_value = _make_version("10042", "1.4.0", archived=True)
        mc.put.return_value = {}
        result, _ = _run(["unarchive", "10042"], mc)
        assert result.exit_code == 0
        body = mc.put.call_args.kwargs.get("data") or mc.put.call_args.kwargs.get("json")
        assert body["archived"] is False

    def test_archive_dry_run(self):
        mc = _make_mock_client()
        mc.get.return_value = _make_version("10042", "1.4.0")
        result, _ = _run(["archive", "10042", "--dry-run"], mc)
        assert result.exit_code == 0
        mc.put.assert_not_called()
```

**Step 2: Run → verify failure**

Run: `uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_version.py::TestArchiveUnarchive -v --no-header`

Expected: FAIL.

**Step 3: Implement**

Replace the `archive` and `unarchive` stubs:

```python
@cli.command()
@click.argument("version_id")
@click.option("--dry-run", is_flag=True, help="Show what would change")
@click.pass_context
def archive(ctx, version_id, dry_run):
    """Archive a version (hides it from pickers)."""
    if dry_run:
        warning("DRY RUN - No version will be updated")
        print(f"Would archive {version_id}")
        return
    client = ctx.obj["client"]
    try:
        _safe_update_version(client, version_id, archived=True)
        success(f"Archived version {version_id}")
    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to archive version: {e}")
        sys.exit(1)


@cli.command()
@click.argument("version_id")
@click.option("--dry-run", is_flag=True, help="Show what would change")
@click.pass_context
def unarchive(ctx, version_id, dry_run):
    """Unarchive a version."""
    if dry_run:
        warning("DRY RUN - No version will be updated")
        print(f"Would unarchive {version_id}")
        return
    client = ctx.obj["client"]
    try:
        _safe_update_version(client, version_id, archived=False)
        success(f"Unarchived version {version_id}")
    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to unarchive version: {e}")
        sys.exit(1)
```

**Step 4: Run → verify pass**

Run: `uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_version.py::TestArchiveUnarchive -v --no-header`

Expected: PASS.

**Step 5: Commit**

```bash
git add tests/test_version.py skills/jira-communication/scripts/workflow/jira-version.py
git commit -m "feat(version): add archive and unarchive subcommands"
```

---

### Task 15: Self-URL builder helper

**Files:**
- Modify: `tests/test_version.py`
- Modify: `skills/jira-communication/scripts/workflow/jira-version.py`

**Step 1: Write failing tests**

```python
class TestSelfUrl:
    def test_builds_self_url(self):
        mc = _make_mock_client(url="https://jira.example.com")
        assert _mod._version_self_url(mc, "10042") == \
            "https://jira.example.com/rest/api/2/version/10042"

    def test_strips_trailing_slash(self):
        mc = _make_mock_client(url="https://jira.example.com/")
        assert _mod._version_self_url(mc, "10042") == \
            "https://jira.example.com/rest/api/2/version/10042"

    def test_preserves_context_path(self):
        mc = _make_mock_client(url="https://corp.example.com/jira")
        assert _mod._version_self_url(mc, "10042") == \
            "https://corp.example.com/jira/rest/api/2/version/10042"

    def test_raises_without_url(self):
        mc = mock.Mock()
        mc.url = ""
        with pytest.raises(RuntimeError):
            _mod._version_self_url(mc, "10042")
```

**Step 2: Run → verify failure**

Run: `uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_version.py::TestSelfUrl -v --no-header`

Expected: FAIL.

**Step 3: Implement**

```python
def _version_self_url(client, vid: str) -> str:
    """Build a fully-qualified self URL for a version from the client's base URL.

    Used by `move --after OTHER_ID` where the Jira API expects a `self` URL
    rather than a bare ID. Constructed from the configured Jira base URL
    (never from user input) to avoid SSRF or cross-instance spoofing.
    """
    base = getattr(client, "url", "") or ""
    if not base:
        raise RuntimeError("Jira client has no configured URL; cannot build self URL")
    base = base.rstrip("/")
    return f"{base}/rest/api/2/version/{vid}"
```

**Step 4: Run → verify pass**

Run: `uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_version.py::TestSelfUrl -v --no-header`

Expected: PASS.

**Step 5: Commit**

```bash
git add tests/test_version.py skills/jira-communication/scripts/workflow/jira-version.py
git commit -m "feat(version): add self-URL builder for move --after"
```

---

### Task 16: `move` subcommand

**Files:**
- Modify: `tests/test_version.py`
- Modify: `skills/jira-communication/scripts/workflow/jira-version.py`

**Step 1: Write failing tests**

```python
class TestMove:
    def test_move_after(self):
        mc = _make_mock_client(url="https://jira.example.com")
        mc.post.return_value = {}
        result, _ = _run(["move", "10045", "--after", "10042"], mc)
        assert result.exit_code == 0, result.output
        path = mc.post.call_args.args[0]
        assert path == "rest/api/2/version/10045/move"
        body = mc.post.call_args.kwargs.get("data") or mc.post.call_args.kwargs.get("json")
        assert body["after"] == "https://jira.example.com/rest/api/2/version/10042"

    def test_move_position(self):
        mc = _make_mock_client()
        mc.post.return_value = {}
        result, _ = _run(["move", "10042", "--position", "First"], mc)
        assert result.exit_code == 0, result.output
        body = mc.post.call_args.kwargs.get("data") or mc.post.call_args.kwargs.get("json")
        assert body == {"position": "First"}

    def test_move_requires_after_or_position(self):
        mc = _make_mock_client()
        result, _ = _run(["move", "10042"], mc)
        assert result.exit_code != 0
        mc.post.assert_not_called()

    def test_move_after_and_position_mutually_exclusive(self):
        mc = _make_mock_client()
        result, _ = _run(["move", "10042", "--after", "10041", "--position", "Last"], mc)
        assert result.exit_code != 0
        mc.post.assert_not_called()

    def test_move_dry_run(self):
        mc = _make_mock_client()
        result, _ = _run(["move", "10042", "--position", "First", "--dry-run"], mc)
        assert result.exit_code == 0
        mc.post.assert_not_called()
```

**Step 2: Run → verify failure**

Run: `uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_version.py::TestMove -v --no-header`

Expected: FAIL.

**Step 3: Implement**

Replace the `move` stub:

```python
@cli.command()
@click.argument("version_id")
@click.option("--after", help="Move this version to directly after the given version ID")
@click.option("--position", type=click.Choice(["First", "Last", "Earlier", "Later"]),
              help="Move relative to current position")
@click.option("--dry-run", is_flag=True, help="Show what would change")
@click.pass_context
def move(ctx, version_id, after, position, dry_run):
    """Reorder a version within its project."""
    if bool(after) == bool(position):
        error("Provide exactly one of --after or --position")
        sys.exit(2)

    client = ctx.obj["client"]
    if after:
        body = {"after": _version_self_url(client, after)}
    else:
        body = {"position": position}

    if dry_run:
        warning("DRY RUN - No version will be moved")
        print(f"Would POST rest/api/2/version/{version_id}/move with:\n  {body}")
        return

    try:
        client.post(f"rest/api/2/version/{version_id}/move", data=body)
        if after:
            success(f"Moved version {version_id} after {after}")
        else:
            success(f"Moved version {version_id} to {position}")
    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to move version: {e}")
        sys.exit(1)
```

**Step 4: Run → verify pass**

Run: `uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_version.py::TestMove -v --no-header`

Expected: PASS.

**Step 5: Commit**

```bash
git add tests/test_version.py skills/jira-communication/scripts/workflow/jira-version.py
git commit -m "feat(version): add move subcommand with --after and --position"
```

---

### Task 17: `merge` subcommand

**Files:**
- Modify: `tests/test_version.py`
- Modify: `skills/jira-communication/scripts/workflow/jira-version.py`

**Step 1: Write failing tests**

```python
class TestMerge:
    def test_merge_executes(self):
        mc = _make_mock_client()
        mc.post.return_value = {}
        result, _ = _run(["merge", "10050", "INTO", "10042"], mc)
        assert result.exit_code == 0, result.output
        path = mc.post.call_args.args[0]
        assert path == "rest/api/2/version/10050/mergeto/10042"

    def test_merge_requires_INTO(self):
        mc = _make_mock_client()
        result, _ = _run(["merge", "10050", "BESIDE", "10042"], mc)
        assert result.exit_code != 0
        mc.post.assert_not_called()

    def test_merge_dry_run_fetches_counts(self):
        mc = _make_mock_client()
        mc.get.side_effect = [
            {"issuesFixedCount": 7, "issuesAffectedCount": 1},  # src relatedIssueCounts
            _make_version("10050", "1.4.0-dup"),                 # src version
            _make_version("10042", "1.4.0"),                     # dst version
        ]
        result, _ = _run(["merge", "10050", "INTO", "10042", "--dry-run"], mc)
        assert result.exit_code == 0, result.output
        mc.post.assert_not_called()
        assert "DRY RUN" in result.output
        assert "7" in result.output   # fixed count
        assert "1" in result.output   # affected count
        assert "1.4.0-dup" in result.output
        assert "1.4.0" in result.output

    def test_merge_does_not_issue_separate_delete(self):
        """mergeto deletes the source server-side; no extra DELETE needed."""
        mc = _make_mock_client()
        mc.post.return_value = {}
        result, _ = _run(["merge", "10050", "INTO", "10042"], mc)
        assert result.exit_code == 0
        mc.delete.assert_not_called()
```

**Step 2: Run → verify failure**

Run: `uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_version.py::TestMerge -v --no-header`

Expected: FAIL.

**Step 3: Implement**

Replace the `merge` stub:

```python
@cli.command()
@click.argument("src_id")
@click.argument("into", type=click.Choice(["INTO"]))
@click.argument("dst_id")
@click.option("--dry-run", is_flag=True, help="Show what would change without calling mergeto")
@click.pass_context
def merge(ctx, src_id, into, dst_id, dry_run):
    """Merge SRC_ID INTO DST_ID.

    Reassigns fixVersions / versions references from SRC to DST, then deletes
    SRC server-side. There is no undo.
    """
    client = ctx.obj["client"]

    if dry_run:
        warning("DRY RUN - No changes will be made")
        counts = client.get(f"rest/api/2/version/{src_id}/relatedIssueCounts") or {}
        src = client.get(f"rest/api/2/version/{src_id}") or {}
        dst = client.get(f"rest/api/2/version/{dst_id}") or {}
        fixed = counts.get("issuesFixedCount", "?")
        affected = counts.get("issuesAffectedCount", "?")
        print(f'Would merge {src_id} "{src.get("name", "?")}" INTO '
              f'{dst_id} "{dst.get("name", "?")}":')
        print(f"  fixed issues to reassign:    {fixed}")
        print(f"  affected issues to reassign: {affected}")
        print("  source version would be deleted")
        return

    try:
        client.post(f"rest/api/2/version/{src_id}/mergeto/{dst_id}")
        success(f"Merged {src_id} into {dst_id}; source deleted")
    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to merge version: {e}")
        sys.exit(1)
```

**Step 4: Run → verify pass**

Run: `uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_version.py::TestMerge -v --no-header`

Expected: PASS.

**Step 5: Commit**

```bash
git add tests/test_version.py skills/jira-communication/scripts/workflow/jira-version.py
git commit -m "feat(version): add merge subcommand with --dry-run counts preview"
```

---

### Task 18: `delete` subcommand — dry-run preview

**Files:**
- Modify: `tests/test_version.py`
- Modify: `skills/jira-communication/scripts/workflow/jira-version.py`

**Step 1: Write failing test**

```python
class TestDeleteDryRun:
    def test_delete_dry_run_fetches_counts(self):
        mc = _make_mock_client()
        mc.get.side_effect = [
            _make_version("10050", "1.4.0-dup"),
            {"issuesFixedCount": 7, "issuesAffectedCount": 1},
        ]
        result, _ = _run(["delete", "10050", "--dry-run"], mc)
        assert result.exit_code == 0, result.output
        mc.delete.assert_not_called()
        assert "DRY RUN" in result.output
        assert "7" in result.output
        assert "1" in result.output
        assert "1.4.0-dup" in result.output
```

**Step 2: Run → verify failure**

Run: `uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_version.py::TestDeleteDryRun -v --no-header`

Expected: FAIL.

**Step 3: Implement dry-run branch of `delete`**

Replace the `delete` stub (real-delete branch filled in Task 19):

```python
@cli.command()
@click.argument("version_id")
@click.option("--move-fix-to", help="Reassign fixVersions refs to this version ID")
@click.option("--move-affected-to", help="Reassign affectsVersions refs to this version ID")
@click.option("--dry-run", is_flag=True, help="Show what would be deleted")
@click.pass_context
def delete(ctx, version_id, move_fix_to, move_affected_to, dry_run):
    """Delete a version, optionally reassigning fixVersions/versions refs."""
    client = ctx.obj["client"]
    if dry_run:
        v = client.get(f"rest/api/2/version/{version_id}") or {}
        counts = client.get(f"rest/api/2/version/{version_id}/relatedIssueCounts") or {}
        warning("DRY RUN - No version will be deleted")
        fixed = counts.get("issuesFixedCount", "?")
        affected = counts.get("issuesAffectedCount", "?")
        print(f'Would delete {version_id} "{v.get("name", "?")}":')
        print(f"  fixVersion refs:        {fixed}"
              + (f" → {move_fix_to}" if move_fix_to else " (would be orphaned)"))
        print(f"  affectsVersion refs:    {affected}"
              + (f" → {move_affected_to}" if move_affected_to else " (would be orphaned)"))
        return

    raise NotImplementedError  # Task 19
```

**Step 4: Run → verify pass**

Run: `uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_version.py::TestDeleteDryRun -v --no-header`

Expected: PASS.

**Step 5: Commit**

```bash
git add tests/test_version.py skills/jira-communication/scripts/workflow/jira-version.py
git commit -m "feat(version): add delete --dry-run with reference counts"
```

---

### Task 19: `delete` — real delete with reassign / orphan warning

**Files:**
- Modify: `tests/test_version.py`
- Modify: `skills/jira-communication/scripts/workflow/jira-version.py`

**Step 1: Write failing tests**

```python
class TestDelete:
    def test_delete_with_move_fix_to(self):
        mc = _make_mock_client()
        mc.delete.return_value = {}
        result, _ = _run(["delete", "10050", "--move-fix-to", "10042"], mc)
        assert result.exit_code == 0, result.output
        path = mc.delete.call_args.args[0]
        assert path == "rest/api/2/version/10050"
        params = mc.delete.call_args.kwargs.get("params") or {}
        assert params.get("moveFixIssuesTo") == "10042"
        # Not provided → absent
        assert "moveAffectedIssuesTo" not in params

    def test_delete_with_both_move_targets(self):
        mc = _make_mock_client()
        mc.delete.return_value = {}
        result, _ = _run(
            ["delete", "10050", "--move-fix-to", "10042", "--move-affected-to", "10043"], mc
        )
        assert result.exit_code == 0
        params = mc.delete.call_args.kwargs.get("params") or {}
        assert params.get("moveFixIssuesTo") == "10042"
        assert params.get("moveAffectedIssuesTo") == "10043"

    def test_delete_without_move_targets_warns(self):
        mc = _make_mock_client()
        mc.delete.return_value = {}
        result, _ = _run(["delete", "10050"], mc)
        assert result.exit_code == 0, result.output
        # Warning printed (to stderr captured by CliRunner into result.output)
        assert "orphan" in result.output.lower() or "warning" in result.output.lower() or "⚠" in result.output
        params = mc.delete.call_args.kwargs.get("params") or {}
        assert "moveFixIssuesTo" not in params
        assert "moveAffectedIssuesTo" not in params
```

**Step 2: Run → verify failure**

Run: `uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_version.py::TestDelete -v --no-header`

Expected: FAIL.

**Step 3: Replace the `NotImplementedError` branch in `delete`**

```python
    # non-dry-run
    params: dict = {}
    if move_fix_to:
        params["moveFixIssuesTo"] = move_fix_to
    if move_affected_to:
        params["moveAffectedIssuesTo"] = move_affected_to

    if not move_fix_to and not move_affected_to:
        warning(
            f"No --move-fix-to / --move-affected-to provided. "
            f"fixVersions/versions references on existing issues will be orphaned."
        )

    try:
        client.delete(f"rest/api/2/version/{version_id}", params=params or None)
        parts = []
        if move_fix_to:
            parts.append(f"fixVersion refs reassigned to {move_fix_to}")
        if move_affected_to:
            parts.append(f"affectsVersion refs reassigned to {move_affected_to}")
        detail = "; " + "; ".join(parts) if parts else ""
        success(f"Deleted version {version_id}{detail}")
    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to delete version: {e}")
        sys.exit(1)
```

**Step 4: Run → verify pass**

Run: `uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_version.py::TestDelete -v --no-header`

Expected: PASS.

**Step 5: Commit**

```bash
git add tests/test_version.py skills/jira-communication/scripts/workflow/jira-version.py
git commit -m "feat(version): implement delete with reassign flags and orphan warning"
```

---

### Task 20: Add `jira-version` to CLI smoke tests

**Files:**
- Modify: `tests/test_cli_smoke.py`

**Step 1: Add module load and help test**

In the module-load section (near `_weblink_mod = _load_script(...)`):

```python
_version_mod = _load_script("jira-version", "workflow")
```

In `TestHelpOutput`:

```python
    def test_version_help(self):
        output = self._run_help(_version_mod.cli)
        assert "version" in output.lower()
```

**Step 2: Run all smoke tests**

Run: `uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_cli_smoke.py -v --no-header`

Expected: all PASS.

**Step 3: Commit**

```bash
git add tests/test_cli_smoke.py
git commit -m "test(version): include jira-version in CLI smoke tests"
```

---

### Task 21: Update SKILL.md

**Files:**
- Modify: `skills/jira-communication/SKILL.md`

**Step 1: Update the Scripts section**

Change the Workflow line (line 24) to include `jira-version.py`:

```
**Workflow**: `jira-create.py`, `jira-transition.py`, `jira-comment.py` (add/edit/delete/list), `jira-move.py`, `jira-sprint.py`, `jira-board.py`, `jira-version.py`
```

**Step 2: Add a `# Versions` subsection under Common Tasks**

After the existing command blocks (near the "Move / link / web links" section), add:

```bash
# Versions (list, create, release lifecycle, merge, delete)
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-version.py list PROJ
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-version.py list PROJ --status unreleased --order-by releaseDate
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-version.py get 10042 --counts
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-version.py create PROJ "1.4.0" --release-date 2026-05-31 --description "Q2 release"
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-version.py release 10042 --release-date 2026-05-31
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-version.py archive 10039
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-version.py merge 10050 INTO 10042 --dry-run
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-version.py delete 10050 --move-fix-to 10042
```

Add one gotcha line near the end of the same section:

```
# Note: on issues, use plural field names — fixVersions / versions — never fixVersion / version.
# Archived versions still match JQL `fixVersion = "..."` — archive only hides from pickers.
```

**Step 3: Verify SKILL.md word count / metadata**

Run (per the project memory): `/skill-repo` or manually:

```bash
uv run skills/jira-communication/scripts/core/jira-validate.py --help
```

Expected: exit 0. No metadata changes needed (no version bump in this plan).

**Step 4: Commit**

```bash
git add skills/jira-communication/SKILL.md
git commit -m "docs(version): document jira-version.py in SKILL.md"
```

---

### Task 22: Full lint / bandit / test sweep

**Files:** none (verification only, commit fixes if required).

**Step 1: Run the full test suite**

Run: `uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/ -q`

Expected: all tests PASS (187 existing + ~40 new).

**Step 2: Lint**

Run: `uv run --no-project --with ruff ruff check skills/jira-communication/scripts/workflow/jira-version.py tests/test_version.py`

Expected: clean. If autofixes are needed: `uv run --no-project --with ruff ruff check --fix skills/jira-communication/scripts/workflow/jira-version.py tests/test_version.py` then re-run.

**Step 3: Format**

Run: `uv run --no-project --with ruff ruff format skills/jira-communication/scripts/workflow/jira-version.py tests/test_version.py`

Expected: no changes, or minor whitespace fixups.

**Step 4: Bandit**

Run: `uv run --no-project --with bandit bandit -r skills/jira-communication/scripts/workflow/jira-version.py -c pyproject.toml --severity-level medium`

Expected: no medium+ findings.

**Step 5: Pre-commit smoke check**

Run: `uv run skills/jira-communication/scripts/core/jira-validate.py --help`

Expected: help text, exit 0.

**Step 6: Commit any autofixes**

```bash
git add -A
git diff --cached --quiet || git commit -m "chore(version): ruff autofixes"
```

If no diff, skip the commit.

---

## Follow-ups (not in this PR)

Per the design doc "Out of Scope":

- Component CRUD (`/rest/api/2/component`) — separate design doc.
- First-class `--fix-version` flag on `jira-create` and `jira-issue update` (currently done via `--fields-json '{"fixVersions": [{"name": "..."}]}'`).
- Release-notes generation from version issue lists — compose with `jira-search` on `fixVersion = "<name>"`.
- Cloud ADF description support.
- Sprint-to-version auto-linking.
