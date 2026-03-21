# `--assignee me` Support — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Support `me` as a special assignee value across all scripts, resolved at the library level so every script benefits automatically.

**Architecture:** Add a `resolve_assignee(client, identifier)` function in `lib/client.py` that handles `"me"` → `client.myself()`, account IDs, and user search. Replace the duplicated assignee resolution blocks in `jira-create.py` and `jira-issue.py` with calls to this function.

**Tech Stack:** Python 3.10+, click, atlassian-python-api, pytest + unittest.mock

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `skills/jira-communication/scripts/lib/client.py` | Modify | Add `resolve_assignee()` function |
| `skills/jira-communication/scripts/workflow/jira-create.py` | Modify | Replace assignee block with `resolve_assignee()` |
| `skills/jira-communication/scripts/core/jira-issue.py` | Modify | Replace assignee block with `resolve_assignee()` |
| `tests/test_client.py` | Modify | Add tests for `resolve_assignee()` |
| `skills/jira-communication/SKILL.md` | Modify | Document `--assignee me` |

**Note:** `jira-issue.py update` currently calls `error()` + `sys.exit(1)` when user search returns empty. After this change, it falls back to the raw identifier (matching `jira-create.py` behavior). This is intentional — Server/DC usernames often work as raw identifiers even when search fails.

---

### Task 1: Add `resolve_assignee()` to lib/client.py — Tests

**Files:**
- Test: `tests/test_client.py`

- [ ] **Step 1: Write failing tests for resolve_assignee()**

Add to end of `tests/test_client.py`:

```python
# ═══════════════════════════════════════════════════════════════════════════════
# Tests: resolve_assignee()
# ═══════════════════════════════════════════════════════════════════════════════


class TestResolveAssignee:
    """resolve_assignee() must handle 'me', account IDs, and user search."""

    def test_me_returns_account_id_on_cloud(self):
        """'me' resolves to accountId from client.myself() on Cloud."""
        mock_client = mock.Mock()
        mock_client.myself.return_value = {
            "accountId": "557058:abc-123",
            "displayName": "Test User",
        }
        result = resolve_assignee(mock_client, "me")
        assert result == {"accountId": "557058:abc-123"}
        mock_client.myself.assert_called_once()

    def test_me_returns_name_on_server(self):
        """'me' resolves to name from client.myself() on Server/DC (no accountId)."""
        mock_client = mock.Mock()
        mock_client.myself.return_value = {
            "name": "john.doe",
            "key": "john.doe",
            "displayName": "John Doe",
        }
        result = resolve_assignee(mock_client, "me")
        assert result == {"name": "john.doe"}
        mock_client.myself.assert_called_once()

    def test_me_case_insensitive(self):
        """'ME', 'Me', 'mE' all resolve as 'me'."""
        mock_client = mock.Mock()
        mock_client.myself.return_value = {"accountId": "abc:123"}
        for variant in ("ME", "Me", "mE"):
            result = resolve_assignee(mock_client, variant)
            assert "accountId" in result

    def test_account_id_passed_through(self):
        """Account IDs are returned directly without API calls."""
        mock_client = mock.Mock()
        result = resolve_assignee(mock_client, "557058:d5765ebc-27de-4ce3-b520-a77a87e5e99a")
        assert result == {"accountId": "557058:d5765ebc-27de-4ce3-b520-a77a87e5e99a"}
        mock_client.myself.assert_not_called()
        mock_client.user_find_by_user_string.assert_not_called()

    def test_username_searched_and_resolved_cloud(self):
        """Non-me, non-account-ID strings are searched via user_find_by_user_string."""
        mock_client = mock.Mock()
        mock_client.user_find_by_user_string.return_value = [
            {"accountId": "found:user-id", "displayName": "Found User"}
        ]
        result = resolve_assignee(mock_client, "found.user")
        assert result == {"accountId": "found:user-id"}

    def test_username_searched_and_resolved_server(self):
        """Server/DC user without accountId returns name."""
        mock_client = mock.Mock()
        mock_client.user_find_by_user_string.return_value = [
            {"name": "jdoe", "key": "jdoe", "displayName": "J Doe"}
        ]
        result = resolve_assignee(mock_client, "jdoe")
        assert result == {"name": "jdoe"}

    def test_user_not_found_returns_raw_name(self):
        """When user search returns empty, fall back to raw identifier."""
        mock_client = mock.Mock()
        mock_client.user_find_by_user_string.return_value = []
        result = resolve_assignee(mock_client, "unknown.user")
        assert result == {"name": "unknown.user"}

    def test_user_search_returns_string_fallback(self):
        """Server/DC may return a string instead of list — fall back to name."""
        mock_client = mock.Mock()
        mock_client.user_find_by_user_string.return_value = "some-string"
        result = resolve_assignee(mock_client, "some.user")
        assert result == {"name": "some.user"}
```

- [ ] **Step 2: Add import for resolve_assignee**

In `tests/test_client.py`, update the import block (line 12-19) to include `resolve_assignee`:

```python
from lib.client import (
    JIRA_TIMEOUT,
    LazyJiraClient,
    _check_captcha_challenge,
    _sanitize_error,
    get_jira_client,
    is_account_id,
    resolve_assignee,
)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /home/cybot/projects/jira-skill/main && python -m pytest tests/test_client.py::TestResolveAssignee -v`
Expected: ImportError — `resolve_assignee` not yet defined

- [ ] **Step 4: Commit test**

```bash
git add tests/test_client.py
git commit -S --signoff -m "test(client): add tests for resolve_assignee()"
```

---

### Task 2: Implement `resolve_assignee()` in lib/client.py

**Files:**
- Modify: `skills/jira-communication/scripts/lib/client.py`

- [ ] **Step 1: Add resolve_assignee() implementation**

Insert after line 35 (end of `is_account_id()`) and before line 38 (`# === INLINE_START: client ===`) in `skills/jira-communication/scripts/lib/client.py`:

```python
def resolve_assignee(client, identifier: str) -> dict:
    """Resolve an assignee identifier to a Jira-API-ready dict.

    Handles:
    - "me" (case-insensitive): resolves via client.myself()
    - Jira Cloud account IDs: returned as {"accountId": ...}
    - Usernames/emails: searched via user_find_by_user_string()

    Returns:
        dict with either {"accountId": ...} or {"name": ...}
    """
    if identifier.lower() == "me":
        user = client.myself()
        if "accountId" in user:
            return {"accountId": user["accountId"]}
        return {"name": user.get("name", user.get("key", ""))}

    if is_account_id(identifier):
        return {"accountId": identifier}

    users = client.user_find_by_user_string(query=identifier)
    if users and isinstance(users, list) and len(users) > 0:
        found = users[0]
        if isinstance(found, dict):
            if "accountId" in found:
                return {"accountId": found["accountId"]}
            return {"name": found.get("name", found.get("key", identifier))}
    # Fall back to raw identifier — let Jira validate
    return {"name": identifier}
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd /home/cybot/projects/jira-skill/main && python -m pytest tests/test_client.py::TestResolveAssignee -v`
Expected: All 8 tests PASS

- [ ] **Step 3: Run full test suite**

Run: `cd /home/cybot/projects/jira-skill/main && python -m pytest tests/test_client.py -v`
Expected: All tests PASS (existing + new)

- [ ] **Step 4: Commit implementation**

```bash
git add scripts/lib/client.py
git commit -S --signoff -m "feat(client): add resolve_assignee() with 'me' support"
```

---

### Task 3: Replace duplicated assignee code in jira-create.py

**Files:**
- Modify: `skills/jira-communication/scripts/workflow/jira-create.py:114-138` (assignee resolution block)

- [ ] **Step 1: Add import for resolve_assignee**

In `jira-create.py`, add `resolve_assignee` to the existing `from lib.client import` line:

```python
from lib.client import LazyJiraClient, is_account_id, resolve_assignee
```

- [ ] **Step 2: Replace the assignee block (lines 114-138) with:**

```python
    if assignee:
        fields["assignee"] = resolve_assignee(client, assignee)
```

- [ ] **Step 3: Verify --help still works**

Run: `cd /home/cybot/projects/jira-skill/main && uv run skills/jira-communication/scripts/workflow/jira-create.py --help`
Expected: Help output with `--assignee` option shown

- [ ] **Step 4: Run existing smoke tests**

Run: `cd /home/cybot/projects/jira-skill/main && python -m pytest tests/ -v -k create`
Expected: All create-related tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/workflow/jira-create.py
git commit -S --signoff -m "refactor(create): use shared resolve_assignee()"
```

---

### Task 4: Replace duplicated assignee code in jira-issue.py

**Files:**
- Modify: `skills/jira-communication/scripts/core/jira-issue.py:286-308` (assignee resolution block in update)

- [ ] **Step 1: Add import for resolve_assignee**

In `jira-issue.py`, add `resolve_assignee` to the existing `from lib.client import` line:

```python
from lib.client import LazyJiraClient, is_account_id, resolve_assignee
```

- [ ] **Step 2: Replace the assignee block (lines 286-308) with:**

```python
    if assignee:
        update_fields["assignee"] = resolve_assignee(client, assignee)
```

- [ ] **Step 3: Verify --help still works**

Run: `cd /home/cybot/projects/jira-skill/main && uv run skills/jira-communication/scripts/core/jira-issue.py update --help`
Expected: Help output with `--assignee` option shown

- [ ] **Step 4: Run full test suite**

Run: `cd /home/cybot/projects/jira-skill/main && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/core/jira-issue.py
git commit -S --signoff -m "refactor(issue): use shared resolve_assignee()"
```

---

### Task 5: Update SKILL.md

**Files:**
- Modify: `skills/jira-communication/SKILL.md`

- [ ] **Step 1: Add assign-to-me note in Quick Examples section**

Add after the existing quick examples (before `## Related Skills`):

```markdown
`--assignee me` resolves to the authenticated user on any script that accepts `--assignee`.
```

- [ ] **Step 2: Verify word count is under 500**

Run: `wc -w skills/jira-communication/SKILL.md`
Expected: Under 500

- [ ] **Step 3: Commit**

```bash
git add skills/jira-communication/SKILL.md
git commit -S --signoff -m "docs(skill): document --assignee me support"
```
