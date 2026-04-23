# Links — Issue-to-Issue and Web Links

## When to load

Load this reference whenever the user wants to create, list, or delete a link between two issues (`jira-link.py`), or a web link from an issue to an external URL (`jira-weblink.py`).

## Issue-to-issue links

```bash
# Create — uses the outward direction of the link type
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-link.py create PROJ-123 PROJ-456 --type Blocks

# List — shows inward and outward links together
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-link.py list PROJ-123

# Delete by link ID (from `list --json`)
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-link.py delete PROJ-123 --id 10042
```

**Link type naming:** use the exact name shown by `jira-fields.py search "link"` or your project's admin panel. Names are case-sensitive and vary per instance.

## Typical link types (names vary per instance)

| Name | Outward (PROJ-A → PROJ-B) | Inward (PROJ-B → PROJ-A) |
|------|---------------------------|---------------------------|
| `Blockade` | blocks | is blocked by |
| `Cause` | causes | is caused by |
| `Duplicate` | duplicates | is duplicated by |
| `Relation` | relates to | is related to |
| `Resolve` | resolves | is resolved by |

Pass the **Name** column to `--type`. Confirm the exact names on your instance via the admin panel or `jira-fields.py search "link"`.

## Web links (links to external URLs)

```bash
# Create a web link
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-weblink.py add PROJ-123 \
    --url "https://example.com/design-doc" --title "Design doc"

# List
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-weblink.py list PROJ-123

# Delete by ID
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-weblink.py delete PROJ-123 --id 42
```

Web links are scoped per issue; the same URL on two issues is two independent web links.
