# Issue Changelog Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `changelog` subcommand to `jira-issue.py` that fetches an issue's change history (who changed what, when) with filtering by field, date range, author, and limit.

**Architecture:** Extends the existing `jira-issue.py` Click group — no new script. Dual-path fetch dispatches on `is_cloud`: DC uses embedded `expand=changelog` (capped at 100, surfaces a truncation warning), Cloud uses the paginated `/issue/{key}/changelog` endpoint. The pipeline is pure-function friendly: `flatten_histories()` → `filter_histories()` → formatter, which keeps TDD tractable and makes DC/Cloud paths converge on one shape downstream of the fetch helpers.

**Tech Stack:** Python 3.10+, click, LazyJiraClient, atlassian-python-api.

**Design doc:** `docs/plans/2026-04-20-changelog-design.md`

---

## Reuse notes (before you start)

Before writing any task, skim these facts — they change how code is placed:

- **`parse_date` does not currently exist** in `jira-worklog-query.py` (the design doc's claim is outdated as of `2026-04-21`). `lib/` has no date helpers either. **Decision for this change-set:** define a local `parse_date()` helper inside `jira-issue.py`, documented with a FIXME referencing later DRY-up if a second consumer appears. Smaller blast radius than extracting to `lib/dates.py` today. Revisit when a third consumer materializes.
- **`is_cloud` detection** is available through `lib.config.is_cloud_url(url)` combined with the `JIRA_CLOUD` env override — mirror the same two-line check already used in `lib/client.py:309-311`. The plan wraps this in `_resolve_is_cloud(client)` to keep the subcommand body clean.
- **`LazyJiraClient` uses `__getattr__` delegation** (`lib/client.py:260`), so `client.issue(key, expand="changelog")` and `client.get("rest/api/3/issue/...", params=...)` both forward to the underlying `atlassian.Jira` instance. No new lib methods needed.
- **Existing `jira-issue.py` structure** (verified at `skills/jira-communication/scripts/core/jira-issue.py`, 442 lines):
  - Imports block: lines 11-25 (add new imports here)
  - Click group + shared ctx: lines 32-48
  - `get` subcommand: lines 51-125
  - `_print_issue` helper: lines 128-289
  - `update` subcommand: lines 292-379
  - `delete` subcommand: lines 382-438
  - Entry point: lines 441-442
  - **Insertion target for changelog helpers:** right after `_print_issue`, before `update` (between lines 289 and 292).
  - **Insertion target for the `@cli.command("changelog")` subcommand:** between `delete` and the `if __name__` block (between lines 438 and 441).

---

### Task 1: Scaffold test file with fixtures

**Files:**
- Create: `tests/test_issue_changelog.py`

**Step 1: Create the test file**

Model the skeleton on `tests/test_weblink.py:1-54` (importlib loader, click.testing, mock helpers).

```python
"""Tests for jira-issue.py changelog subcommand."""

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


def _load_script():
    """Load jira-issue.py via importlib."""
    path = _scripts_path / "core" / "jira-issue.py"
    spec = importlib.util.spec_from_file_location("jira_issue", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mod = _load_script()


# ───────────────────────────────────────────────────────────────────────────────
# Raw API payload fixtures — DC (embedded) and Cloud (paginated).
# Keep these as dict literals (not external JSON) so tests read top-to-bottom.
# ───────────────────────────────────────────────────────────────────────────────


def _history(hid, created, author_name, items, *, account_id=None, display_name=None):
    author = {"name": author_name, "displayName": display_name or author_name}
    if account_id:
        author["accountId"] = account_id
    return {"id": hid, "author": author, "created": created, "items": items}


def _item(field, from_str, to_str, *, field_id=None, schema_custom_id=None):
    row = {
        "field": field,
        "fieldtype": "jira",
        "from": None,
        "to": None,
        "fromString": from_str,
        "toString": to_str,
    }
    if field_id:
        row["fieldId"] = field_id
    if schema_custom_id:
        row["fieldSchema"] = {"customId": schema_custom_id}
    return row


DC_EMBEDDED_FIXTURE = {
    "key": "PROJ-1",
    "changelog": {
        "histories": [
            _history(
                "10001",
                "2026-04-18T09:12:33.000+0000",
                "alice",
                [_item("status", "In Progress", "Done", field_id="status")],
                display_name="Alice Example",
                account_id="acct-alice",
            ),
            _history(
                "10002",
                "2026-04-17T14:55:00.000+0000",
                "bwilson",
                [
                    _item("assignee", "Alice Example", "Bob Wilson", field_id="assignee"),
                    _item("Sprint", "Sprint 42", "Sprint 43", schema_custom_id=10020),
                ],
                display_name="Bob Wilson",
                account_id="acct-bob",
            ),
            _history(
                "10003",
                "2026-04-10T08:00:00.000+0000",
                "alice",
                [_item("assignee", "Bob Wilson", None, field_id="assignee")],  # un-assigned
                display_name="Alice Example",
                account_id="acct-alice",
            ),
        ]
    },
}


CLOUD_PAGINATED_FIXTURE = {
    "startAt": 0,
    "maxResults": 100,
    "total": 3,
    "isLast": True,
    "values": DC_EMBEDDED_FIXTURE["changelog"]["histories"],
}
```

**Step 2: Sanity-check the fixture loads**

Run:

```bash
uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_issue_changelog.py -q
```

Expected: collected 0 items (no tests yet), exit 5. Anything else indicates an import error — fix before proceeding.

**Step 3: Commit**

```bash
git add tests/test_issue_changelog.py
git commit -m "test(changelog): scaffold test file with DC and Cloud fixtures"
```

---

### Task 2: `flatten_histories()` helper — pure fan-out

**Files:**
- Modify: `tests/test_issue_changelog.py`
- Modify: `skills/jira-communication/scripts/core/jira-issue.py`

**Step 1: Write failing tests**

Append to `tests/test_issue_changelog.py`:

```python
class TestFlattenHistories:
    def test_fans_out_items_into_rows(self):
        histories = DC_EMBEDDED_FIXTURE["changelog"]["histories"]
        rows = _mod.flatten_histories(histories)
        # 1 status + 2 (assignee + Sprint) + 1 un-assign = 4 rows
        assert len(rows) == 4

    def test_row_shape(self):
        rows = _mod.flatten_histories(DC_EMBEDDED_FIXTURE["changelog"]["histories"])
        first = rows[0]
        assert first["created"] == "2026-04-18T09:12:33.000+0000"
        assert first["author"]["name"] == "alice"
        assert first["field"] == "status"
        assert first["fieldId"] == "status"
        assert first["fromString"] == "In Progress"
        assert first["toString"] == "Done"

    def test_preserves_null_to_string(self):
        rows = _mod.flatten_histories(DC_EMBEDDED_FIXTURE["changelog"]["histories"])
        unassign = [r for r in rows if r["fromString"] == "Bob Wilson"][0]
        assert unassign["toString"] is None  # NOT coalesced

    def test_preserves_field_schema(self):
        rows = _mod.flatten_histories(DC_EMBEDDED_FIXTURE["changelog"]["histories"])
        sprint = [r for r in rows if r["field"] == "Sprint"][0]
        assert sprint["fieldSchema"] == {"customId": 10020}

    def test_empty_histories(self):
        assert _mod.flatten_histories([]) == []
```

**Step 2: Run to verify failure**

```bash
uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_issue_changelog.py::TestFlattenHistories -q
```

Expected: all FAIL with `AttributeError: module 'jira_issue' has no attribute 'flatten_histories'`.

**Step 3: Implement `flatten_histories()` in `jira-issue.py`**

Insert at the top of the helper region — directly after `_print_issue` ends at line 289 and before the `@cli.command()` for `update` on line 292. Add a section banner to keep the file self-navigable.

```python
# ═══════════════════════════════════════════════════════════════════════════════
# Changelog helpers (pure functions — dual-path DC/Cloud converge here)
# ═══════════════════════════════════════════════════════════════════════════════


def flatten_histories(histories: list[dict]) -> list[dict]:
    """Fan out Jira histories[].items[] into one row per item.

    Each row preserves the parent entry's created/author plus the item's
    field metadata. Null fromString/toString are preserved (callers decide
    how to render them — coalescing loses information).
    """
    rows: list[dict] = []
    for entry in histories or []:
        created = entry.get("created")
        author = entry.get("author", {}) or {}
        for item in entry.get("items", []) or []:
            rows.append(
                {
                    "created": created,
                    "author": author,
                    "field": item.get("field"),
                    "fieldId": item.get("fieldId"),
                    "fieldSchema": item.get("fieldSchema"),
                    "from": item.get("from"),
                    "to": item.get("to"),
                    "fromString": item.get("fromString"),
                    "toString": item.get("toString"),
                }
            )
    return rows
```

**Step 4: Run to verify pass**

```bash
uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_issue_changelog.py::TestFlattenHistories -q
```

Expected: 5 passed.

**Step 5: Commit**

```bash
git add skills/jira-communication/scripts/core/jira-issue.py tests/test_issue_changelog.py
git commit -m "feat(changelog): add flatten_histories() pure helper"
```

---

### Task 3: `filter_histories()` — field matching

**Files:**
- Modify: `tests/test_issue_changelog.py`
- Modify: `skills/jira-communication/scripts/core/jira-issue.py`

**Step 1: Write failing tests**

```python
class TestFilterHistoriesByField:
    @pytest.fixture
    def rows(self):
        return _mod.flatten_histories(DC_EMBEDDED_FIXTURE["changelog"]["histories"])

    def test_match_by_field_id(self, rows):
        out = _mod.filter_histories(rows, fields=["status"])
        assert len(out) == 1
        assert out[0]["field"] == "status"

    def test_match_by_display_name_case_insensitive(self, rows):
        out = _mod.filter_histories(rows, fields=["sprint"])
        assert len(out) == 1
        assert out[0]["field"] == "Sprint"

    def test_match_by_customfield_schema(self, rows):
        out = _mod.filter_histories(rows, fields=["customfield_10020"])
        assert len(out) == 1
        assert out[0]["field"] == "Sprint"

    def test_multiple_fields_union(self, rows):
        out = _mod.filter_histories(rows, fields=["status", "assignee"])
        # 1 status + 2 assignee = 3 rows
        assert len(out) == 3

    def test_unknown_field_returns_empty(self, rows):
        assert _mod.filter_histories(rows, fields=["nope"]) == []

    def test_no_fields_filter_returns_all(self, rows):
        assert len(_mod.filter_histories(rows, fields=None)) == 4


class TestItemMatchesField:
    def test_fieldid_precedence(self):
        row = {"field": "Assignee", "fieldId": "assignee", "fieldSchema": None}
        assert _mod._row_matches_field(row, "assignee")

    def test_display_name_lowercased(self):
        row = {"field": "Sprint", "fieldId": None, "fieldSchema": None}
        assert _mod._row_matches_field(row, "SPRINT")

    def test_customfield_via_schema(self):
        row = {"field": "Whatever", "fieldId": None, "fieldSchema": {"customId": 10100}}
        assert _mod._row_matches_field(row, "customfield_10100")
```

**Step 2: Run to verify failure**

```bash
uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_issue_changelog.py -q -k "Filter or Matches"
```

Expected: all FAIL.

**Step 3: Implement helpers**

Append to the changelog helpers region in `jira-issue.py` (right after `flatten_histories`):

```python
def _row_matches_field(row: dict, requested: str) -> bool:
    """Match a flattened row against a requested field identifier.

    Resolution order (per design doc):
      1. fieldId exact match (case-insensitive)
      2. field (display name) exact match (case-insensitive)
      3. "customfield_" + fieldSchema.customId exact match (case-insensitive)
    """
    req = requested.lower()
    field_id = (row.get("fieldId") or "").lower()
    if field_id and field_id == req:
        return True
    field_display = (row.get("field") or "").lower()
    if field_display and field_display == req:
        return True
    schema = row.get("fieldSchema") or {}
    custom_id = schema.get("customId")
    if custom_id is not None and f"customfield_{custom_id}".lower() == req:
        return True
    return False


def filter_histories(
    rows: list[dict],
    *,
    fields: list[str] | None = None,
    since: str | None = None,  # filled in Task 4
    until: str | None = None,  # filled in Task 4
    author: str | None = None,  # filled in Task 5
) -> list[dict]:
    """Filter flattened changelog rows by field, date range, and author.

    Date and author parameters are placeholders at this task — implemented
    in Tasks 4 and 5. Keep the signature stable to avoid churn.
    """
    out = rows
    if fields:
        requested = list(fields)
        out = [r for r in out if any(_row_matches_field(r, f) for f in requested)]
    return out
```

**Step 4: Run to verify pass**

```bash
uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_issue_changelog.py -q -k "Filter or Matches"
```

Expected: 9 passed (6 filter + 3 matcher).

**Step 5: Commit**

```bash
git add skills/jira-communication/scripts/core/jira-issue.py tests/test_issue_changelog.py
git commit -m "feat(changelog): filter_histories by field with id/display/customfield precedence"
```

---

### Task 4: `filter_histories()` — date range + local `parse_date()`

**Files:**
- Modify: `tests/test_issue_changelog.py`
- Modify: `skills/jira-communication/scripts/core/jira-issue.py`

**Rationale:** Design doc says "reuse parse_date from jira-worklog-query.py" but no such helper exists there today (verified `2026-04-21`). Local copy for this change-set, FIXME marker for later extraction to `lib/dates.py`.

**Step 1: Write failing tests**

```python
class TestParseDate:
    def test_iso_date(self):
        from datetime import date
        assert _mod.parse_date("2026-03-01") == date(2026, 3, 1)

    def test_relative_days(self, monkeypatch):
        from datetime import date
        fake_today = date(2026, 4, 20)

        class _FakeDate(date):
            @classmethod
            def today(cls):
                return fake_today

        monkeypatch.setattr(_mod, "date", _FakeDate)
        assert _mod.parse_date("7d") == date(2026, 4, 13)

    def test_relative_weeks(self, monkeypatch):
        from datetime import date
        fake_today = date(2026, 4, 20)

        class _FakeDate(date):
            @classmethod
            def today(cls):
                return fake_today

        monkeypatch.setattr(_mod, "date", _FakeDate)
        assert _mod.parse_date("2w") == date(2026, 4, 6)

    def test_relative_months_approx(self, monkeypatch):
        from datetime import date
        fake_today = date(2026, 4, 20)

        class _FakeDate(date):
            @classmethod
            def today(cls):
                return fake_today

        monkeypatch.setattr(_mod, "date", _FakeDate)
        # 1m = 30 days (documented approximation)
        assert _mod.parse_date("1m") == date(2026, 3, 21)

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            _mod.parse_date("garbage")


class TestFilterHistoriesByDate:
    @pytest.fixture
    def rows(self):
        return _mod.flatten_histories(DC_EMBEDDED_FIXTURE["changelog"]["histories"])

    def test_since_inclusive(self, rows):
        out = _mod.filter_histories(rows, since="2026-04-17")
        # Drops the 2026-04-10 entry
        assert len(out) == 3
        assert all(r["created"][:10] >= "2026-04-17" for r in out)

    def test_until_inclusive(self, rows):
        out = _mod.filter_histories(rows, until="2026-04-17")
        # Drops the 2026-04-18 entry
        assert len(out) == 3
        assert all(r["created"][:10] <= "2026-04-17" for r in out)

    def test_since_and_until(self, rows):
        out = _mod.filter_histories(rows, since="2026-04-17", until="2026-04-17")
        assert len(out) == 2  # both items on 2026-04-17

    def test_since_filters_nothing_when_before_all(self, rows):
        out = _mod.filter_histories(rows, since="2020-01-01")
        assert len(out) == 4
```

**Step 2: Run to verify failure**

```bash
uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_issue_changelog.py -q -k "ParseDate or ByDate"
```

Expected: all FAIL.

**Step 3: Import `date`/`timedelta` and `re` into `jira-issue.py`**

Edit the imports block (lines 11-14). After `import json`, add:

```python
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path
```

**Step 4: Implement `parse_date()` and extend `filter_histories()`**

Add `parse_date` right before `_row_matches_field` in the changelog helpers region:

```python
# FIXME(changelog/dates): duplicated with a future jira-worklog-query consumer.
# When a second caller appears, extract to lib/dates.py. See design doc
# 2026-04-20-changelog-design.md §Filter semantics.
_RELATIVE_DATE_RE = re.compile(r"^(\d+)([dwm])$")


def parse_date(value: str) -> "date":
    """Parse an ISO date or relative form (Nd / Nw / Nm) into a date.

    Nd = N days ago, Nw = N weeks ago, Nm = N months ago (30-day approx).
    Raises ValueError on unparseable input.
    """
    match = _RELATIVE_DATE_RE.match(value.strip())
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        today = date.today()
        if unit == "d":
            return today - timedelta(days=amount)
        if unit == "w":
            return today - timedelta(weeks=amount)
        if unit == "m":
            return today - timedelta(days=amount * 30)
    # Fall through to ISO parse; raises ValueError on bad input.
    return date.fromisoformat(value)
```

Extend `filter_histories` — replace the body:

```python
def filter_histories(
    rows: list[dict],
    *,
    fields: list[str] | None = None,
    since: str | None = None,
    until: str | None = None,
    author: str | None = None,  # implemented in Task 5
) -> list[dict]:
    """Filter flattened changelog rows by field, date range, and author."""
    out = rows
    if fields:
        requested = list(fields)
        out = [r for r in out if any(_row_matches_field(r, f) for f in requested)]
    if since:
        since_str = parse_date(since).isoformat()
        out = [r for r in out if (r.get("created") or "")[:10] >= since_str]
    if until:
        until_str = parse_date(until).isoformat()
        out = [r for r in out if (r.get("created") or "")[:10] <= until_str]
    return out
```

**Step 5: Run to verify pass**

```bash
uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_issue_changelog.py -q -k "ParseDate or ByDate"
```

Expected: 9 passed (5 parse_date + 4 date filter).

**Step 6: Commit**

```bash
git add skills/jira-communication/scripts/core/jira-issue.py tests/test_issue_changelog.py
git commit -m "feat(changelog): add parse_date and since/until filtering"
```

---

### Task 5: `filter_histories()` — author matching

**Files:**
- Modify: `tests/test_issue_changelog.py`
- Modify: `skills/jira-communication/scripts/core/jira-issue.py`

**Step 1: Write failing tests**

```python
class TestFilterHistoriesByAuthor:
    @pytest.fixture
    def rows(self):
        return _mod.flatten_histories(DC_EMBEDDED_FIXTURE["changelog"]["histories"])

    def test_by_username(self, rows):
        out = _mod.filter_histories(rows, author="bwilson")
        assert len(out) == 2  # both items on the bwilson history entry
        assert all(r["author"]["name"] == "bwilson" for r in out)

    def test_by_display_name(self, rows):
        out = _mod.filter_histories(rows, author="Alice Example")
        assert len(out) == 2  # 1 status item + 1 un-assign item

    def test_by_account_id(self, rows):
        out = _mod.filter_histories(rows, author="acct-alice")
        assert len(out) == 2

    def test_unknown_author_empty(self, rows):
        assert _mod.filter_histories(rows, author="nobody") == []
```

**Step 2: Run to verify failure**

```bash
uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_issue_changelog.py::TestFilterHistoriesByAuthor -q
```

Expected: all FAIL (filter ignores `author` so all 4 rows come back).

**Step 3: Implement author filter**

Extend `filter_histories` — add the author branch at the end of the function body, before `return out`:

```python
    if author:
        out = [r for r in out if _row_matches_author(r, author)]
    return out
```

Add the helper right below `_row_matches_field`:

```python
def _row_matches_author(row: dict, requested: str) -> bool:
    """Match a row's author against a username, accountId, or display name.

    Exact match; caller is responsible for resolving "me" to the current
    user's identifier before calling (so this function stays pure).
    """
    a = row.get("author") or {}
    return requested in (a.get("name", ""), a.get("accountId", ""), a.get("displayName", ""))
```

**Step 4: Run to verify pass**

```bash
uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_issue_changelog.py::TestFilterHistoriesByAuthor -q
```

Expected: 4 passed.

**Step 5: Commit**

```bash
git add skills/jira-communication/scripts/core/jira-issue.py tests/test_issue_changelog.py
git commit -m "feat(changelog): filter_histories by author (name/accountId/displayName)"
```

---

### Task 6: DC fetch path

**Files:**
- Modify: `tests/test_issue_changelog.py`
- Modify: `skills/jira-communication/scripts/core/jira-issue.py`

**Step 1: Write failing tests**

```python
class TestFetchChangelogDc:
    def test_calls_issue_with_expand_changelog(self):
        client = mock.Mock()
        client.issue.return_value = DC_EMBEDDED_FIXTURE
        histories = _mod._fetch_changelog_dc(client, "PROJ-1")
        client.issue.assert_called_once_with("PROJ-1", expand="changelog")
        assert len(histories) == 3

    def test_missing_changelog_returns_empty(self):
        client = mock.Mock()
        client.issue.return_value = {"key": "PROJ-1"}  # no changelog key
        assert _mod._fetch_changelog_dc(client, "PROJ-1") == []
```

**Step 2: Run to verify failure**

```bash
uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_issue_changelog.py::TestFetchChangelogDc -q
```

Expected: FAIL.

**Step 3: Implement**

Append to the changelog helpers region:

```python
def _fetch_changelog_dc(client, issue_key: str) -> list[dict]:
    """Fetch changelog via DC's embedded expand=changelog.

    DC is capped at 100 entries with no pagination. Caller is responsible
    for surfacing the truncation warning (see _fetch_changelog).
    """
    issue = client.issue(issue_key, expand="changelog")
    return issue.get("changelog", {}).get("histories", []) or []
```

**Step 4: Run to verify pass**

```bash
uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_issue_changelog.py::TestFetchChangelogDc -q
```

Expected: 2 passed.

**Step 5: Commit**

```bash
git add skills/jira-communication/scripts/core/jira-issue.py tests/test_issue_changelog.py
git commit -m "feat(changelog): add _fetch_changelog_dc helper"
```

---

### Task 7: Cloud fetch path with pagination

**Files:**
- Modify: `tests/test_issue_changelog.py`
- Modify: `skills/jira-communication/scripts/core/jira-issue.py`

**Step 1: Write failing tests**

```python
class TestFetchChangelogCloud:
    def test_single_page(self):
        client = mock.Mock()
        client.get.return_value = CLOUD_PAGINATED_FIXTURE
        histories = _mod._fetch_changelog_cloud(client, "PROJ-1")
        client.get.assert_called_once_with(
            "rest/api/3/issue/PROJ-1/changelog",
            params={"startAt": 0, "maxResults": 100},
        )
        assert len(histories) == 3

    def test_follows_pagination_until_is_last(self):
        client = mock.Mock()
        page1 = {
            "startAt": 0, "maxResults": 100, "total": 150, "isLast": False,
            "values": DC_EMBEDDED_FIXTURE["changelog"]["histories"],  # 3 entries stand-in
        }
        page2 = {
            "startAt": 100, "maxResults": 100, "total": 150, "isLast": True,
            "values": DC_EMBEDDED_FIXTURE["changelog"]["histories"][:2],  # 2 entries
        }
        client.get.side_effect = [page1, page2]
        histories = _mod._fetch_changelog_cloud(client, "PROJ-1")
        assert len(histories) == 5
        assert client.get.call_count == 2
        # Second call offsets startAt by the page size.
        second_params = client.get.call_args_list[1].kwargs["params"]
        assert second_params["startAt"] == 100

    def test_limit_stops_pagination(self):
        client = mock.Mock()
        client.get.return_value = {
            "startAt": 0, "maxResults": 100, "total": 500, "isLast": False,
            "values": DC_EMBEDDED_FIXTURE["changelog"]["histories"],  # 3 entries
        }
        histories = _mod._fetch_changelog_cloud(client, "PROJ-1", limit=2)
        assert len(histories) == 2
        # One fetch is enough — we hit the limit before asking for more.
        assert client.get.call_count == 1
```

**Step 2: Run to verify failure**

```bash
uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_issue_changelog.py::TestFetchChangelogCloud -q
```

Expected: FAIL.

**Step 3: Implement**

Append to changelog helpers:

```python
def _fetch_changelog_cloud(client, issue_key: str, limit: int | None = None) -> list[dict]:
    """Fetch changelog via Cloud's paginated /issue/{key}/changelog endpoint.

    Follows pagination until isLast=true or `limit` entries collected.
    Returns the concatenated histories in API order.
    """
    all_histories: list[dict] = []
    start_at = 0
    page_size = 100
    while True:
        result = client.get(
            f"rest/api/3/issue/{issue_key}/changelog",
            params={"startAt": start_at, "maxResults": page_size},
        )
        values = result.get("values", []) or []
        all_histories.extend(values)
        if limit is not None and len(all_histories) >= limit:
            return all_histories[:limit]
        if result.get("isLast") is True or not values:
            break
        start_at += len(values) if values else page_size
    return all_histories
```

**Step 4: Run to verify pass**

```bash
uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_issue_changelog.py::TestFetchChangelogCloud -q
```

Expected: 3 passed.

**Step 5: Commit**

```bash
git add skills/jira-communication/scripts/core/jira-issue.py tests/test_issue_changelog.py
git commit -m "feat(changelog): add _fetch_changelog_cloud helper with pagination"
```

---

### Task 8: DC 100-cap truncation warning

**Files:**
- Modify: `tests/test_issue_changelog.py`
- Modify: `skills/jira-communication/scripts/core/jira-issue.py`

**Step 1: Write failing test**

```python
class TestDcCapWarning:
    def test_warns_on_100_entries(self):
        client = mock.Mock()
        client.issue.return_value = {
            "changelog": {"histories": [_history(str(i), "2026-04-18T00:00:00.000+0000",
                                                 "alice", [_item("status", "x", "y")],
                                                 display_name="Alice") for i in range(100)]}
        }
        with mock.patch.object(_mod, "warning") as mocked_warn:
            _mod._fetch_changelog(client, "PROJ-1", is_cloud=False)
        assert mocked_warn.called
        msg = mocked_warn.call_args.args[0]
        assert "100" in msg and "truncat" in msg.lower()

    def test_no_warning_below_cap(self):
        client = mock.Mock()
        client.issue.return_value = DC_EMBEDDED_FIXTURE  # 3 entries
        with mock.patch.object(_mod, "warning") as mocked_warn:
            _mod._fetch_changelog(client, "PROJ-1", is_cloud=False)
        assert not mocked_warn.called
```

Note: This test also exercises `_fetch_changelog` (the endpoint-dispatching helper from Task 9). Writing the warning tests before the dispatcher is deliberate — see Task 9 Step 3 for why the warning lives in the dispatcher.

**Step 2: Run to verify failure**

```bash
uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_issue_changelog.py::TestDcCapWarning -q
```

Expected: `AttributeError: module has no attribute '_fetch_changelog'`.

**Step 3: Implementation deferred**

`_fetch_changelog` is defined in Task 9 and includes the cap warning there. Leave these tests red until Task 9 lands, then verify both green together.

**Step 4: Do not commit yet**

These tests commit together with Task 9's dispatcher. Keep working tree dirty.

---

### Task 9: Endpoint dispatcher `_fetch_changelog()` + `_resolve_is_cloud()`

**Files:**
- Modify: `tests/test_issue_changelog.py`
- Modify: `skills/jira-communication/scripts/core/jira-issue.py`

**Step 1: Write failing tests for the dispatcher**

```python
class TestFetchChangelogDispatcher:
    def test_dispatches_to_cloud_when_is_cloud_true(self):
        client = mock.Mock()
        client.get.return_value = CLOUD_PAGINATED_FIXTURE
        _mod._fetch_changelog(client, "PROJ-1", is_cloud=True)
        assert client.get.called
        assert not client.issue.called

    def test_dispatches_to_dc_when_is_cloud_false(self):
        client = mock.Mock()
        client.issue.return_value = DC_EMBEDDED_FIXTURE
        _mod._fetch_changelog(client, "PROJ-1", is_cloud=False)
        assert client.issue.called
        assert not client.get.called

    def test_cloud_forwards_limit(self):
        client = mock.Mock()
        client.get.return_value = CLOUD_PAGINATED_FIXTURE
        _mod._fetch_changelog(client, "PROJ-1", is_cloud=True, limit=2)
        params = client.get.call_args.kwargs["params"]
        assert params["maxResults"] == 100  # page size stays 100; limit is applied in-helper
```

**Step 2: Run to verify failure**

```bash
uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_issue_changelog.py::TestFetchChangelogDispatcher tests/test_issue_changelog.py::TestDcCapWarning -q
```

Expected: all FAIL.

**Step 3: Implement dispatcher + is_cloud resolver**

Append to the changelog helpers region:

```python
DC_HISTORY_CAP = 100


def _fetch_changelog(
    client,
    issue_key: str,
    *,
    is_cloud: bool,
    limit: int | None = None,
) -> list[dict]:
    """Dispatch to the right fetch helper and surface DC truncation warnings."""
    if is_cloud:
        return _fetch_changelog_cloud(client, issue_key, limit=limit)
    histories = _fetch_changelog_dc(client, issue_key)
    if len(histories) >= DC_HISTORY_CAP:
        warning(
            f"DC returned {DC_HISTORY_CAP} history entries (cap). "
            "Results may be truncated."
        )
    return histories


def _resolve_is_cloud(client) -> bool:
    """Decide whether the client is talking to Jira Cloud.

    Mirrors the logic in lib/client.py:309-311 — JIRA_CLOUD env override
    wins, otherwise fall back to URL pattern matching.
    """
    from lib.config import is_cloud_url, load_config

    config = load_config()
    explicit = str(config.get("JIRA_CLOUD", "")).lower()
    if explicit in ("true", "false"):
        return explicit == "true"
    return is_cloud_url(config.get("JIRA_URL", ""))
```

**Step 4: Run both test classes to verify pass**

```bash
uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_issue_changelog.py::TestFetchChangelogDispatcher tests/test_issue_changelog.py::TestDcCapWarning -q
```

Expected: 5 passed (3 dispatcher + 2 cap warning).

**Step 5: Commit**

```bash
git add skills/jira-communication/scripts/core/jira-issue.py tests/test_issue_changelog.py
git commit -m "feat(changelog): dispatch DC/Cloud fetch and warn on DC 100-entry cap"
```

---

### Task 10: Output formatters (table / JSON / quiet)

**Files:**
- Modify: `tests/test_issue_changelog.py`
- Modify: `skills/jira-communication/scripts/core/jira-issue.py`

**Step 1: Write failing tests**

```python
class TestFormatChangelog:
    @pytest.fixture
    def rows(self):
        return _mod.flatten_histories(DC_EMBEDDED_FIXTURE["changelog"]["histories"])

    def test_table_has_header_and_rows(self, rows):
        out = _mod.format_changelog_table("PROJ-1", rows)
        assert "PROJ-1" in out
        assert "WHEN" in out and "WHO" in out and "FIELD" in out
        assert "status" in out
        assert "Alice Example" in out

    def test_table_null_to_renders_dash(self, rows):
        out = _mod.format_changelog_table("PROJ-1", rows)
        # Un-assign row has toString=None — render as an em-dash sentinel.
        assert "\u2014" in out  # em-dash sentinel

    def test_json_is_flat_rows(self, rows):
        out = _mod.format_changelog_json(rows)
        parsed = json.loads(out)
        assert isinstance(parsed, list)
        assert len(parsed) == 4
        assert parsed[0]["field"] == "status"

    def test_json_preserves_null_to_string(self, rows):
        parsed = json.loads(_mod.format_changelog_json(rows))
        unassign = next(r for r in parsed if r["fromString"] == "Bob Wilson")
        assert unassign["toString"] is None

    def test_quiet_is_tab_separated_one_row_per_line(self, rows):
        out = _mod.format_changelog_quiet(rows)
        lines = out.strip().splitlines()
        assert len(lines) == 4
        for line in lines:
            parts = line.split("\t")
            assert len(parts) == 5  # created, author, field, from, to

    def test_empty_rows_table(self):
        out = _mod.format_changelog_table("PROJ-1", [])
        assert "no" in out.lower() or "0 entries" in out.lower()
```

**Step 2: Run to verify failure**

```bash
uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_issue_changelog.py::TestFormatChangelog -q
```

Expected: FAIL.

**Step 3: Implement formatters**

Append to changelog helpers region. Import `format_json` at the top of the file — edit the existing import on line 25:

```python
from lib.output import error, extract_adf_text, format_json, format_output, success, warning
```

Then implement:

```python
NULL_SENTINEL = "\u2014"  # em-dash — matches the design doc's rendering choice


def _row_display(row: dict) -> tuple[str, str, str, str, str]:
    """Extract display tuple (when, who, field, from, to) for a row."""
    created = row.get("created", "") or ""
    when = created[:16].replace("T", " ")  # "2026-04-18 09:12"
    author = row.get("author", {}) or {}
    who = author.get("displayName") or author.get("name") or ""
    field = row.get("field") or row.get("fieldId") or ""
    from_str = row.get("fromString")
    to_str = row.get("toString")
    from_disp = from_str if from_str is not None else NULL_SENTINEL
    to_disp = to_str if to_str is not None else NULL_SENTINEL
    return when, who, field, from_disp, to_disp


def format_changelog_table(issue_key: str, rows: list[dict]) -> str:
    """Render flattened rows as a fixed-column text table."""
    if not rows:
        return f"{issue_key} changelog (0 entries)\n"
    lines = [f"{issue_key} changelog ({len(rows)} entries)", ""]
    lines.append(f"{'WHEN':<17} {'WHO':<20} {'FIELD':<20} {'FROM':<20} TO")
    for row in rows:
        when, who, field, from_disp, to_disp = _row_display(row)
        if len(who) > 20:
            who = who[:17] + "..."
        if len(field) > 20:
            field = field[:17] + "..."
        if len(from_disp) > 20:
            from_disp = from_disp[:17] + "..."
        lines.append(f"{when:<17} {who:<20} {field:<20} {from_disp:<20} {to_disp}")
    return "\n".join(lines)


def format_changelog_json(rows: list[dict]) -> str:
    """Render rows as JSON (flattened, not nested histories)."""
    return format_json(rows)


def format_changelog_quiet(rows: list[dict]) -> str:
    """Tab-separated: created\tauthor\tfield\tfrom\tto — one row per line."""
    lines = []
    for row in rows:
        created = row.get("created", "") or ""
        author = row.get("author", {}) or {}
        who = author.get("name") or author.get("accountId") or author.get("displayName") or ""
        field = row.get("field") or row.get("fieldId") or ""
        from_str = row.get("fromString") if row.get("fromString") is not None else ""
        to_str = row.get("toString") if row.get("toString") is not None else ""
        lines.append(f"{created}\t{who}\t{field}\t{from_str}\t{to_str}")
    return "\n".join(lines) + ("\n" if lines else "")
```

**Step 4: Run to verify pass**

```bash
uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_issue_changelog.py::TestFormatChangelog -q
```

Expected: 6 passed.

**Step 5: Commit**

```bash
git add skills/jira-communication/scripts/core/jira-issue.py tests/test_issue_changelog.py
git commit -m "feat(changelog): add table/JSON/quiet formatters with null-sentinel rendering"
```

---

### Task 11: Wire the `@cli.command("changelog")` subcommand

**Files:**
- Modify: `tests/test_issue_changelog.py`
- Modify: `skills/jira-communication/scripts/core/jira-issue.py`

**Step 1: Write failing happy-path integration test**

```python
class TestChangelogCli:
    def _run(self, args, *, dc_fixture=None, is_cloud=False):
        client = mock.Mock()
        client.with_context = mock.Mock()
        if dc_fixture is not None:
            client.issue.return_value = dc_fixture
        runner = click.testing.CliRunner()
        with (
            mock.patch.object(_mod, "LazyJiraClient", return_value=client),
            mock.patch.object(_mod, "_resolve_is_cloud", return_value=is_cloud),
        ):
            result = runner.invoke(_mod.cli, args)
        return result, client

    def test_happy_path_table(self):
        result, _ = self._run(
            ["changelog", "PROJ-1"], dc_fixture=DC_EMBEDDED_FIXTURE, is_cloud=False
        )
        assert result.exit_code == 0, result.output
        assert "PROJ-1 changelog" in result.output
        assert "status" in result.output
        assert "Alice Example" in result.output

    def test_json_flag_emits_array(self):
        result, _ = self._run(
            ["--json", "changelog", "PROJ-1"], dc_fixture=DC_EMBEDDED_FIXTURE
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert isinstance(parsed, list)
        assert len(parsed) == 4

    def test_quiet_flag_tabs(self):
        result, _ = self._run(
            ["--quiet", "changelog", "PROJ-1"], dc_fixture=DC_EMBEDDED_FIXTURE
        )
        assert result.exit_code == 0
        first_line = result.output.splitlines()[0]
        assert first_line.count("\t") == 4
```

**Step 2: Run to verify failure**

```bash
uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_issue_changelog.py::TestChangelogCli -q
```

Expected: FAIL with "No such command 'changelog'".

**Step 3: Wire the subcommand in `jira-issue.py`**

Insert between `delete` (ends at line 438) and `if __name__ == "__main__":` (line 441). Copy the decorator style, docstring style, and error handling pattern directly from `delete`.

```python
@cli.command()
@click.argument("issue_key")
@click.option(
    "--field",
    "fields",
    multiple=True,
    help="Filter by field id or display name (repeatable, case-insensitive)",
)
@click.option("--since", help="Start date: ISO (2026-03-01) or relative (7d, 2w, 1m)")
@click.option("--until", help="End date: ISO or relative form")
@click.option("--author", help="Filter by username, accountId, display name, or 'me'")
@click.option("--limit", type=int, help="Cap total entries returned after filtering")
@click.pass_context
def changelog(
    ctx,
    issue_key: str,
    fields: tuple[str, ...],
    since: str | None,
    until: str | None,
    author: str | None,
    limit: int | None,
):
    """Show an issue's change history.

    ISSUE_KEY: The Jira issue key (e.g., PROJ-123)

    Examples:

      jira-issue changelog PROJ-123

      jira-issue changelog PROJ-123 --field status

      jira-issue changelog PROJ-123 --author me --since 7d --json
    """
    ctx.obj["client"].with_context(issue_key=issue_key)
    client = ctx.obj["client"]

    try:
        is_cloud = _resolve_is_cloud(client)

        # Resolve "me" before filtering so filter_histories stays pure.
        resolved_author = author
        if author and author.lower() == "me":
            me = client.myself()
            resolved_author = me.get("accountId") or me.get("name") or me.get("displayName") or author

        # Cloud can pre-trim at the API; DC fetches everything it has.
        fetch_limit = limit if is_cloud and not (fields or since or until or author) else None
        histories = _fetch_changelog(client, issue_key, is_cloud=is_cloud, limit=fetch_limit)

        rows = flatten_histories(histories)
        rows = filter_histories(
            rows,
            fields=list(fields) if fields else None,
            since=since,
            until=until,
            author=resolved_author,
        )
        if limit is not None:
            rows = rows[:limit]

        if ctx.obj["json"]:
            click.echo(format_changelog_json(rows))
        elif ctx.obj["quiet"]:
            click.echo(format_changelog_quiet(rows), nl=False)
        else:
            click.echo(format_changelog_table(issue_key, rows))

    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to get changelog for {issue_key}: {e}")
        sys.exit(1)
```

**Step 4: Run to verify pass**

```bash
uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_issue_changelog.py::TestChangelogCli -q
```

Expected: 3 passed.

**Step 5: Commit**

```bash
git add skills/jira-communication/scripts/core/jira-issue.py tests/test_issue_changelog.py
git commit -m "feat(changelog): wire @cli.command('changelog') with --json/--quiet/default output"
```

---

### Task 12: Integration test — all flags together

**Files:**
- Modify: `tests/test_issue_changelog.py`

**Step 1: Extend the rich fixture and add a combined-flags test**

Append to the `TestChangelogCli` class:

```python
    def test_all_flags_together(self):
        # Rich fixture: status change by alice, assignee change by bwilson,
        # another status change by alice outside the window, and an older
        # status change by alice inside the window.
        fixture = {
            "changelog": {
                "histories": [
                    _history("1", "2026-04-20T10:00:00.000+0000", "alice",
                             [_item("status", "To Do", "In Progress", field_id="status")],
                             display_name="Alice", account_id="acct-alice"),
                    _history("2", "2026-04-19T10:00:00.000+0000", "bwilson",
                             [_item("assignee", "Alice", "Bob", field_id="assignee")],
                             display_name="Bob", account_id="acct-bob"),
                    _history("3", "2026-04-15T10:00:00.000+0000", "alice",
                             [_item("status", "In Progress", "Done", field_id="status")],
                             display_name="Alice", account_id="acct-alice"),
                    _history("4", "2026-03-01T10:00:00.000+0000", "alice",
                             [_item("status", "Open", "To Do", field_id="status")],
                             display_name="Alice", account_id="acct-alice"),
                ]
            }
        }
        result, _ = self._run(
            [
                "changelog", "PROJ-1",
                "--field", "status",
                "--since", "2026-04-01",
                "--until", "2026-04-30",
                "--author", "alice",
                "--limit", "10",
            ],
            dc_fixture=fixture,
            is_cloud=False,
        )
        assert result.exit_code == 0, result.output
        # Keeps history 1 and 3 (status + alice + in window), drops 2 (not alice),
        # drops 4 (outside window).
        assert "To Do" in result.output and "In Progress" in result.output
        assert "Done" in result.output
        assert "assignee" not in result.output  # history 2 filtered out by --field
        assert "2026-03-01" not in result.output  # history 4 filtered out by --since
```

**Step 2: Run**

```bash
uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_issue_changelog.py::TestChangelogCli::test_all_flags_together -q
```

Expected: pass.

**Step 3: Commit**

```bash
git add tests/test_issue_changelog.py
git commit -m "test(changelog): integration test exercising all filter flags together"
```

---

### Task 13: CLI smoke test coverage

**Files:**
- Modify: `tests/test_cli_smoke.py`

**Step 1: Verify the existing `jira-issue --help` smoke test lists `changelog`**

`tests/test_cli_smoke.py:62-64` already calls `--help` on `_issue_mod.cli`. After adding the subcommand, `--help` lists it in the Commands block. Strengthen `test_issue_help` to assert the subcommand is discoverable.

Edit `tests/test_cli_smoke.py`, replacing `test_issue_help`:

```python
    def test_issue_help(self):
        output = self._run_help(_issue_mod.cli)
        assert "issue" in output.lower()
        # changelog subcommand must be listed in the help output
        assert "changelog" in output.lower()
```

**Step 2: Add a direct help check on the subcommand**

Inside `TestHelpOutput`, append:

```python
    def test_issue_changelog_help(self):
        runner = click.testing.CliRunner()
        result = runner.invoke(_issue_mod.cli, ["changelog", "--help"])
        assert result.exit_code == 0, result.output
        assert "changelog" in result.output.lower()
        assert "--field" in result.output
        assert "--since" in result.output
        assert "--author" in result.output
```

**Step 3: Run smoke tests**

```bash
uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/test_cli_smoke.py -q
```

Expected: all pass including the new `test_issue_changelog_help`.

**Step 4: Commit**

```bash
git add tests/test_cli_smoke.py
git commit -m "test(changelog): extend smoke tests to cover changelog subcommand --help"
```

---

### Task 14: Update SKILL.md

**Files:**
- Modify: `skills/jira-communication/SKILL.md`

**Step 1: Add the changelog subcommand example**

Locate the `jira-issue` example block in `skills/jira-communication/SKILL.md` (the file covering `get`/`update`/`delete` usage). Append — matching the surrounding example style, no new sections:

```bash
# Show issue changelog (who changed what, when)
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-issue.py changelog PROJ-123
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-issue.py changelog PROJ-123 --field status --since 30d
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-issue.py changelog PROJ-123 --author me --since 7d --json
```

**Step 2: Do not touch metadata.version or any other doc file**

Per `CLAUDE.md`: version is managed only in `.claude-plugin/plugin.json` and SKILL.md metadata during releases, not per-feature.

**Step 3: Commit**

```bash
git add skills/jira-communication/SKILL.md
git commit -m "docs(changelog): add jira-issue changelog examples to SKILL.md"
```

---

### Task 15: Full sweep — lint, security, tests

**Files:** none (validation only; commit autofixes if any)

**Step 1: Ruff**

```bash
uv run --no-project --with ruff ruff check skills/jira-communication/scripts/core/jira-issue.py tests/test_issue_changelog.py
```

Expected: clean. If any issues, run `ruff check --fix` on the same paths, re-run, commit as `style(changelog): apply ruff autofixes`.

**Step 2: Bandit**

```bash
uv run --no-project --with bandit bandit -r skills/jira-communication/scripts/ scripts/ -c pyproject.toml --severity-level medium
```

Expected: clean.

**Step 3: Full pytest**

```bash
uv run --no-project --with pytest --with atlassian-python-api --with click --with requests python -m pytest tests/ -q
```

Expected: all tests pass. The suite previously had 187 tests (per MEMORY.md); after Tasks 1-12 it grows by roughly 40 tests (5 flatten + 9 filter-field + 9 date + 4 author + 2 dc + 3 cloud + 2 cap + 3 dispatcher + 6 format + 4 cli + 1 smoke ≈ 48).

**Step 4: Pre-commit smoke**

```bash
uv run skills/jira-communication/scripts/core/jira-validate.py --help
uv run skills/jira-communication/scripts/core/jira-issue.py changelog --help
```

Expected: both print help, exit 0.

**Step 5: Invoke skill-repo before final commit**

Per MEMORY.md: run `/skill-repo` to mirror CI's SKILL.md / plugin.json / composer.json validation. If it flags anything, fix and commit as `chore(changelog): address skill-repo findings`.

**Step 6: No commit unless fixes were required**

If all checks are clean, Task 15 produces no commit. If autofixes landed, commit them with the conventional prefix matching what changed (`style(changelog): ...` for ruff, `chore(changelog): ...` for metadata).
