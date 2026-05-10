# Links — Issue-to-Issue and Web Links

## When to load

Load this reference whenever the user wants to create, list, or delete a link between two issues (`jira-link.py`), or a web link from an issue to an external URL (`jira-weblink.py`).

## ⚠️ Direction rule (read this before `create`)

> `jira-link.py create FROM TO --type X` creates the link such that **`TO` is the source/active actor** (uses the link type's *outward* verb) and **`FROM` is the destination/passive recipient** (uses the *inward* verb).
>
> Mnemonic: **TO is the *agent*, FROM is the *patient*.**
> Read the call as: *"on FROM, record that TO does X to it."*

This matches Atlassian's REST API convention (`outwardIssue` is the source; `inwardIssue` is the destination). The `--source` / `--target` aliases in step 4 below make the intent explicit:

- `create FROM TO --type X`  ≡  `create --source TO --target FROM --type X`

`jira-link.py` prints the resulting natural-language sentence on success, so you can verify the direction immediately:

```text
Created: IOS-18 causes NRS-878 (link-type: Cause)
```

## Issue-to-issue links

```bash
# Create — see the direction rule above. TO is the active actor.
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-link.py create PROJ-123 PROJ-456 --type Blocks
# → "PROJ-456 blocks PROJ-123"

# Equivalent named form (recommended for clarity):
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-link.py create \
    --source PROJ-456 --target PROJ-123 --type Blocks

# Preview without writing — also prints the resolved sentence
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-link.py create PROJ-123 PROJ-456 --type Blocks --dry-run

# List — shows inward and outward links together
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-link.py list PROJ-123

# Delete by link ID (from `list --json`)
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-link.py delete PROJ-123 --id 10042
```

**Link type naming:** the canonical name (as displayed by Jira and stored in the link object) varies per instance — confirm yours via `jira-link.py list-types` or `jira-fields.py search "link"`. The `--type` argument matches case-insensitively against the canonical name (`blocks`, `Blocks`, `BLOCKS` all resolve to the same type), so case mismatches will not fail; non-existent type names will.

## Typical link types (names vary per instance)

In `create FROM TO --type T`, `TO` is the active party and uses the outward verb. The table is keyed on the link-type **name** as you pass it to `--type`.

| `--type` value | Outward verb (what `TO` does to `FROM`) | Inward verb (how `FROM` is described) |
|----------------|------------------------------------------|----------------------------------------|
| `Blockade`     | blocks                                   | is blocked by                          |
| `Cause`        | causes                                   | is caused by                           |
| `Duplicate`    | duplicates                               | is duplicated by                       |
| `Relation`     | relates to                               | is related to                          |
| `Resolve`      | resolves                                 | is resolved by                         |
| `Side effect`  | affects                                  | is affected by                         |

Confirm the exact names on your instance via `jira-link.py list-types` or the admin panel.

## Worked examples

Each example shows the call, the resulting natural-language sentence, and what each endpoint's view shows in the Jira UI after the link is created.

### 1. Blocker (infrastructure blocks a frontend ticket)

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-link.py create FRONTEND-12 INFRA-99 --type Blockade
# Created: INFRA-99 blocks FRONTEND-12 (link-type: Blockade)
```

After creation:

- On **FRONTEND-12** you see: `is blocked by ← INFRA-99`
- On **INFRA-99** you see: `blocks → FRONTEND-12`

### 2. Root cause (root issue causes the observed effect)

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-link.py create EFFECT-1 ROOT-2 --type Cause
# Created: ROOT-2 causes EFFECT-1 (link-type: Cause)
```

After creation:

- On **EFFECT-1** you see: `is caused by ← ROOT-2`
- On **ROOT-2** you see: `causes → EFFECT-1`

### 3. Side effect (a change affects an unrelated component)

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-link.py create AFFECTED-3 CHANGE-4 --type "Side effect"
# Created: CHANGE-4 affects AFFECTED-3 (link-type: Side effect)
```

After creation:

- On **AFFECTED-3** you see: `is affected by ← CHANGE-4`
- On **CHANGE-4** you see: `affects → AFFECTED-3`

## Real-world reference

The `netresearch-jira` skill bundles a [linking-conventions reference](https://github.com/netresearch/netresearch-jira-skill/blob/main/skills/netresearch-jira/references/linking-conventions.md) with concrete `CHILD`/`PARENT` examples for the Netresearch Jira instance. The direction semantics there agree with this document and serve as a sanity check before you call `create`.

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
