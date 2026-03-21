# Subtask Type Auto-Detection — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When `--parent` is provided during issue creation, automatically validate and resolve the issue type against the project's actual subtask types (queried from the API), instead of relying on naming conventions.

**Architecture:** Add `get_project_issue_types(client, project_key)` and `resolve_subtask_type(client, project_key, requested_type)` functions in `lib/client.py`. The subtask resolver uses the Jira API's `subtask` boolean field on issue types — no naming convention assumptions. Add a `types` subcommand to `jira-fields.py` for discoverability.

**Tech Stack:** Python 3.10+, click, atlassian-python-api, pytest + unittest.mock

**Dependency:** This plan assumes the `--assignee me` plan has been implemented first (imports `resolve_assignee` in test file).

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `skills/jira-communication/scripts/lib/client.py` | Modify | Add `get_project_issue_types()`, `resolve_subtask_type()` |
| `skills/jira-communication/scripts/workflow/jira-create.py` | Modify | Use `resolve_subtask_type()` when `--parent` is given |
| `skills/jira-communication/scripts/utility/jira-fields.py` | Modify | Add `types` subcommand |
| `tests/test_client.py` | Modify | Add tests for new functions |
| `skills/jira-communication/SKILL.md` | Modify | Document subtask type behavior, add `jira-fields.py types` |

---

### Task 1: Add `get_project_issue_types()` and `resolve_subtask_type()` — Tests

**Files:**
- Test: `tests/test_client.py`

- [ ] **Step 1: Write failing tests**

Add to end of `tests/test_client.py`:

```python
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
        client = _mock_client_with_types([
            {"id": "1", "name": "Task", "subtask": False},
            {"id": "2", "name": "Teilaufgabe", "subtask": True},
        ])
        result = resolve_subtask_type(client, "PROJ", "Task")
        assert result == "Teilaufgabe"

    def test_no_subtask_types_returns_none(self):
        """When project has no subtask types, returns None."""
        client = _mock_client_with_types([
            {"id": "1", "name": "Task", "subtask": False},
            {"id": "2", "name": "Bug", "subtask": False},
        ])
        result = resolve_subtask_type(client, "PROJ", "Task")
        assert result is None

    def test_no_match_multiple_subtask_types_returns_none(self):
        """No match + multiple subtask types → None (ambiguous)."""
        client = _mock_client_with_types(SAMPLE_ISSUE_TYPES)
        result = resolve_subtask_type(client, "PROJ", "Epic")
        assert result is None
```

- [ ] **Step 2: Add imports**

Update the import block in `tests/test_client.py` to include the new functions:

```python
from lib.client import (
    JIRA_TIMEOUT,
    LazyJiraClient,
    _check_captcha_challenge,
    _sanitize_error,
    get_jira_client,
    get_project_issue_types,
    is_account_id,
    resolve_assignee,
    resolve_subtask_type,
)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /home/cybot/projects/jira-skill/main && python -m pytest tests/test_client.py::TestGetProjectIssueTypes tests/test_client.py::TestResolveSubtaskType -v`
Expected: ImportError — functions not yet defined

- [ ] **Step 4: Commit tests**

```bash
git add tests/test_client.py
git commit -S --signoff -m "test(client): add tests for subtask type resolution"
```

---

### Task 2: Implement `get_project_issue_types()` and `resolve_subtask_type()`

**Files:**
- Modify: `skills/jira-communication/scripts/lib/client.py` (after `resolve_assignee()`, before `# === INLINE_START: client ===`)

- [ ] **Step 1: Add implementation**

```python
def get_project_issue_types(client, project_key: str, subtask_only: bool | None = None) -> list[dict]:
    """Get available issue types for a project.

    Uses expand=issueTypes to ensure Server/DC includes type metadata.

    Args:
        client: Jira client instance
        project_key: Project key (e.g., "PROJ")
        subtask_only: If True, only subtask types. If False, only non-subtask. None = all.

    Returns:
        List of issue type dicts with at least 'id', 'name', 'subtask' keys.
    """
    project = client.project(project_key, expand="issueTypes")
    types = project.get("issueTypes", [])
    if subtask_only is True:
        return [t for t in types if t.get("subtask")]
    if subtask_only is False:
        return [t for t in types if not t.get("subtask")]
    return types


def resolve_subtask_type(client, project_key: str, requested_type: str) -> str | None:
    """Resolve a requested issue type to a valid subtask type for the project.

    Resolution order:
    1. Exact match (case-insensitive) among subtask types
    2. Subtask type whose name contains the requested type (e.g., "Task" → "Sub: Task")
    3. Generic subtask keywords ("subtask", "sub-task") → first available subtask type
    4. Only one subtask type available → return it regardless of name
    5. No match / no subtask types → return None

    Args:
        client: Jira client instance
        project_key: Project key
        requested_type: The issue type name the user requested

    Returns:
        Resolved subtask type name, or None if no match or no subtask types.
    """
    subtask_types = get_project_issue_types(client, project_key, subtask_only=True)
    if not subtask_types:
        return None

    req_lower = requested_type.lower()

    # 1. Exact match (case-insensitive)
    for st in subtask_types:
        if st["name"].lower() == req_lower:
            return st["name"]

    # 2. Subtask type whose name contains the requested type
    #    e.g., "Task" matches "Sub: Task", "Bug" matches "Sub: Bug"
    for st in subtask_types:
        if req_lower in st["name"].lower():
            return st["name"]

    # 3. Generic subtask keywords → first available
    if req_lower in ("subtask", "sub-task", "sub task"):
        return subtask_types[0]["name"]

    # 4. Only one subtask type? Use it (unambiguous).
    if len(subtask_types) == 1:
        return subtask_types[0]["name"]

    return None
```

- [ ] **Step 2: Run tests**

Run: `cd /home/cybot/projects/jira-skill/main && python -m pytest tests/test_client.py::TestGetProjectIssueTypes tests/test_client.py::TestResolveSubtaskType -v`
Expected: All 14 tests PASS

- [ ] **Step 3: Run full test suite**

Run: `cd /home/cybot/projects/jira-skill/main && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add skills/jira-communication/scripts/lib/client.py
git commit -S --signoff -m "feat(client): add subtask type resolution via API"
```

---

### Task 3: Integrate subtask type resolution into jira-create.py

**Files:**
- Modify: `skills/jira-communication/scripts/workflow/jira-create.py:140-146` (parent/subtask handling)

- [ ] **Step 1: Add imports**

Add to existing imports in `jira-create.py`:

```python
from lib.client import LazyJiraClient, is_account_id, resolve_assignee, resolve_subtask_type
```

- [ ] **Step 2: Replace the parent handling block (lines 140-146)**

Replace the existing `if parent:` block with:

```python
    if parent:
        # Resolve issue type to a valid subtask type for the target project
        resolved_type = resolve_subtask_type(client, project, issue_type)
        if resolved_type is None:
            error(
                f"Project {project} has no subtask issue types matching '{issue_type}'",
                suggestion=f"Run: jira-fields.py types {project}  to list available types",
            )
            sys.exit(1)
        if resolved_type != issue_type:
            warning(f"Resolved issue type '{issue_type}' → '{resolved_type}' (subtask type for {project})")
            fields["issuetype"] = {"name": resolved_type}
        fields["parent"] = {"key": parent}
```

- [ ] **Step 3: Verify --help still works**

Run: `cd /home/cybot/projects/jira-skill/main && uv run skills/jira-communication/scripts/workflow/jira-create.py --help`
Expected: Help output displayed

- [ ] **Step 4: Run tests**

Run: `cd /home/cybot/projects/jira-skill/main && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add skills/jira-communication/scripts/workflow/jira-create.py
git commit -S --signoff -m "feat(create): auto-resolve subtask types via API when --parent given"
```

---

### Task 4: Add `types` subcommand to jira-fields.py

**Files:**
- Modify: `skills/jira-communication/scripts/utility/jira-fields.py`

- [ ] **Step 1: Add `warning` to imports**

Update the import from `lib.output` (currently line 24) to include `warning`:

```python
from lib.output import error, format_output, format_table, warning
```

- [ ] **Step 2: Add `types` subcommand**

Add after the existing `list` subcommand:

```python
@cli.command("types")
@click.argument("project", required=False)
@click.pass_context
def list_types(ctx, project: str | None):
    """List available issue types.

    If PROJECT is given, show types for that project (including subtask flag).
    Otherwise, show all global issue types.

    Examples:

      jira-fields.py types PROJ

      jira-fields.py types
    """
    client = ctx.obj["client"]

    try:
        if project:
            from lib.client import get_project_issue_types

            # Use project key for profile resolution
            client.with_context(issue_key=f"{project}-1")
            types = get_project_issue_types(client, project)
        else:
            types = client.get_all_issuetypes()

        if ctx.obj["json"]:
            format_output(types, as_json=True)
            return

        if not types:
            warning("No issue types found")
            return

        rows = []
        for t in types:
            rows.append({
                "Name": t.get("name", ""),
                "ID": t.get("id", ""),
                "Subtask": "Yes" if t.get("subtask") else "",
            })
        rows.sort(key=lambda r: (r["Subtask"] != "Yes", r["Name"]))
        print(format_table(rows, ["Name", "ID", "Subtask"]))

    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to list issue types: {e}")
        sys.exit(1)
```

- [ ] **Step 2: Verify --help works**

Run: `cd /home/cybot/projects/jira-skill/main && uv run skills/jira-communication/scripts/utility/jira-fields.py types --help`
Expected: Help output for types subcommand

- [ ] **Step 3: Commit**

```bash
git add skills/jira-communication/scripts/utility/jira-fields.py
git commit -S --signoff -m "feat(fields): add 'types' subcommand to list issue types"
```

---

### Task 5: Update SKILL.md

**Files:**
- Modify: `skills/jira-communication/SKILL.md`

- [ ] **Step 1: Update scripts table**

Update the `jira-fields.py` row:

```markdown
| `scripts/utility/jira-fields.py` | Search fields, list issue types |
```

- [ ] **Step 2: Add subtask note**

Add after the scripts table (keep under 500 words total):

```markdown
`--parent` auto-resolves `--type` to a valid subtask type for the project via API.
```

- [ ] **Step 3: Verify word count**

Run: `wc -w skills/jira-communication/SKILL.md`
Expected: Under 500

- [ ] **Step 4: Commit**

```bash
git add skills/jira-communication/SKILL.md
git commit -S --signoff -m "docs(skill): document subtask type auto-detection and jira-fields types"
```
