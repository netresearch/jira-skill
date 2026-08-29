# Troubleshooting Guide

## When to load

Load this reference whenever any script returns a non-zero exit code related to authentication, SSL, connectivity, or environment configuration — typically surfaced as HTTP 401/403, certificate errors, or `JIRA_URL` not set. Also load it before building a `--json | jq` pipeline: the two most common failures there (stream pollution and payload shape) are documented below.

## Setup Validation

Always start with:
```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-validate.py --verbose
```

### Exit Codes
| Code | Meaning | Action |
|------|---------|--------|
| 0 | All checks passed | Ready to use |
| 1 | Runtime dependency missing | Install `uv` |
| 2 | Environment config error | Check `~/.env.jira` |
| 3 | Connectivity/auth failure | Verify credentials |

## Configuration

Scripts load configuration in priority order:
1. Explicit `--env-file` parameter (if provided)
2. `~/.jira/profiles.json` (if exists) — supports multiple Jira instances with auto-resolution from issue key, URL, or `.jira-profile` file (see `references/multi-profile.md`)
3. `~/.env.jira` file (legacy single-instance config)
4. Environment variables (fallback for missing values)

You can use any of these approaches. For multiple Jira instances, use `~/.jira/profiles.json`.

### Option A: Environment File

Create `~/.env.jira`:

### Jira Cloud
```bash
JIRA_URL=https://yourcompany.atlassian.net
JIRA_USERNAME=your-email@example.com
JIRA_API_TOKEN=your-api-token-here
```

### Jira Server/Data Center
```bash
JIRA_URL=https://jira.yourcompany.com
JIRA_PERSONAL_TOKEN=your-personal-access-token
```

### Option B: Environment Variables

Export variables directly (useful in CI/CD or when credentials are managed externally):

```bash
# Jira Cloud
export JIRA_URL=https://yourcompany.atlassian.net
export JIRA_USERNAME=your-email@example.com
export JIRA_API_TOKEN=your-api-token-here

# Or Jira Server/DC
export JIRA_URL=https://jira.yourcompany.com
export JIRA_PERSONAL_TOKEN=your-personal-access-token
```

## Common Errors

### "jq: parse error: Invalid numeric literal at line 1, column 10"

**Cause**: `uv run` prints `Installed N packages in Xms` on a cold cache. uv writes that notice to **stderr**, so a plain `--json | jq` pipeline is unaffected — the line only reaches `jq` when stderr has been folded into the pipe: an explicit `2>&1 |`, a wrapper or CI step that combines streams, or an agent harness that captures merged output. Column 10 is the character after `Installed`, which is the fingerprint of this specific cause; the scripts themselves are not the source — warnings and errors go to stderr (`output.py:warning()` / `error()`) and `--json` mode suppresses `✓` lines in the commands you would pipe. (`output.py:success()` does print to stdout, and a few write paths call it unguarded — `jira-create.py project --bootstrap-issues` is one — so pipe write commands with care.)

**Fix**: keep stderr out of a JSON pipe. Where the streams must stay merged, filter the notice:

```bash
# Wrong — merged streams put uv's install notice on jq's stdin
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-board.py --json list --project PROJ 2>&1 | jq -c '.[]'

# Correct — leave stderr on the terminal
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-board.py --json list --project PROJ | jq -c '.[]'

# Correct — merged output is unavoidable, so drop the notice
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-board.py --json list --project PROJ 2>&1 \
  | grep -v '^Installed' | jq -c '.[]'
```

A script's first invocation warms **its own** environment, so later calls to *that* script are silent. Each script warms separately — uv keys the environment per script, so warming `jira-issue.py` does not silence `jira-search.py` even though their PEP 723 dependency lists are byte-identical. The warm state lives in the uv cache, not the shell session, so it also survives across sessions.

### "Configuration errors: Missing required"

**Cause**: Required variables not found in file or environment.

**Fix**:
1. Check `~/.env.jira` exists with correct values, OR
2. Verify environment variables are exported
3. Variable names are case-sensitive
4. No quotes around values needed in `.env.jira`

### "Failed to connect to Jira"

**Cause**: Network, URL, or SSL issues.

**Fix**:
1. Verify URL is correct (include `https://`)
2. Test URL in browser
3. Check VPN if on corporate network
4. For self-signed certs, may need `JIRA_VERIFY_SSL=false`

### "401 Unauthorized"

**Cause**: Invalid credentials.

**Cloud Fix**:
1. Generate new API token at https://id.atlassian.com/manage-profile/security/api-tokens
2. Use email as `JIRA_USERNAME`, not display name

**Server/DC Fix**:
1. Create PAT in Jira: Profile → Personal Access Tokens
2. Use only `JIRA_PERSONAL_TOKEN`, not username/password

### "403 Forbidden"

**Cause**: Valid auth but no permission.

**Fix**:
1. Verify account has project access
2. Check if IP allowlisting blocks API access
3. Confirm API access not disabled by admin

### "No such option: --json"

**Cause**: Flag placed after subcommand.

**Fix**: Move flags before subcommand:
```bash
# Wrong
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-issue.py get PROJ-123 --json

# Correct
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-issue.py --json get PROJ-123
```

### "Cannot index array with string" (`--json` payload shape)

**Cause**: the flag placement above is right but the jq path is wrong. `--json` emits a **bare array** for list-style subcommands — there is no `{"issues": [...]}` envelope to index. `jira-search.py` unwraps the API response itself — `results.get("issues", [])` — and hands the plain list to `format_output(..., as_json=True)`, which dumps it as-is.

Shapes across the scripts (verify with `| jq -r 'type'` rather than assuming):

| Subcommand | Top-level JSON | jq path |
|---|---|---|
| `search query`, `comment list`, `version list`, `board list`, `transition list`, `link list`, `link list-types`, `weblink list`, `worklog list`, `sprint list`, `fields search`, `user search` | array | `.[]` |
| `issue get` | object | `.key`, `.fields.…` (comments live at `.fields.comment.comments`) |
| `issue work / qa / qa-fail` | object | `.key`, `.comments[]` |
| `issue act` | object | `.key`, `.transitions[]` |
| `watchers list` | object — the one *list* subcommand that wraps its result | `.watchers[]`, `.watchCount` |
| `jira-qa-gather.py KEY` | object (bundle, like `work`) | `.siblings[]`, `.comments[]`, `.worklogs[]` |

**Fix**: index the array directly.

```bash
# Wrong — exits 5 with: Cannot index array with string "issues"
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-search.py --json query "project = OPS" | jq -r '.issues[].key'

# Correct
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-search.py --json query "project = OPS" | jq -r '.[].key'
```

Confirm any shape you are unsure of with `… --json <cmd> | jq -r 'type'` before building the pipeline on top of it.

### "No such option: -f" / "-n" (query options before the subcommand)

**Cause**: The inverse of the error above — a *subcommand* option placed before the subcommand. `-f/--fields`, `-n/--max-results`, and `--order-by` belong to `query`, so they must come **after** the `query` token (before or after the positional JQL is fine), never before it. Global options (`--json`, `-q`) go before the subcommand. A stub that ignores argument order hides this — verify the ordering against the live tool.

**Fix**: Put query flags after the `query` subcommand:
```bash
# Wrong — -f before the `query` subcommand → "Error: No such option: -f" (exit 2)
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-search.py --json -f key,status query "project = OPS"

# Correct — global flags before `query`; query flags after `query`,
# either before or after the JQL both work
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-search.py --json query "project = OPS" -f key,status -n 500
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-search.py --json query -f key,status -n 500 "project = OPS"
```

### "Transition 'X' not available" (passing the transition ID)

**Cause**: `jira-transition.py do` expects the **target status name**, not the numeric transition ID that `jira-transition.py list` prints in its leftmost column.

**Fix**: Pass the destination status, in quotes:
```bash
# Wrong — 311 is the transition ID from `list`
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-transition.py do PROJ-123 311

# Correct — the To-Status name
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-transition.py do PROJ-123 "Resolved"
```
When two transitions share a name but differ by icon (e.g. "✅ QA" → Resolved vs "❌ QA" → Reopened), disambiguate by passing the **target status** ("Resolved" / "Reopened"), which is unique.

### "Issue does not exist"

**Cause**: Wrong key or no permission.

**Fix**:
1. Verify issue key spelling and case
2. Confirm you have "Browse" permission on project
3. Check if issue was moved/deleted

### "Field 'xyz' cannot be set"

**Cause**: Field not editable or wrong format.

**Fix**:
1. Use `jira-fields.py search xyz` to find correct field ID
2. Check field is on the edit screen for that issue type
3. Verify field format (some need `{"name": "value"}`)

**`resolution` is the common special case.** On workflows whose terminal transition screens omit the field, both `jira-transition.py do KEY "…" --resolution Done` and a follow-up `jira-issue.py update --fields-json '{"resolution": {"name": "Done"}}'` fail with this error. Retry the transition without `--resolution` — see *"When the screen rejects `--resolution`"* in `intent-verbs.md`.

## Debug Mode

Add `--debug` for full stack traces:
```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-issue.py --debug get PROJ-123
```

## Auth Mode Detection

Scripts auto-detect auth mode:
- If `JIRA_PERSONAL_TOKEN` set → Server/DC PAT auth
- If `JIRA_USERNAME` + `JIRA_API_TOKEN` set → Cloud basic auth
- URL containing `.atlassian.net` → Cloud mode

Override with `JIRA_CLOUD=true` or `JIRA_CLOUD=false`.

## `{task}` inline checkboxes CAN be ticked via API — use the tasklist endpoint

The `{task:id=NN}…{task}` checkboxes in Jira Server descriptions (maintenance tickets) store their state in a plugin database, not in the description text. They toggle fine with a PAT — but only via the **Task List** REST API:

| Method | Path | Body | Result |
| ------ | ---- | ---- | ------ |
| `GET` | `/rest/tasklist/1.0/tasks/<id>` | (none) | XML `<checked>true\|false</checked>` |
| `POST` | `/rest/tasklist/1.0/tasks/<id>/updateselection` | form `checked=true\|false` | HTTP 204 |

An earlier version of this section claimed the boxes need a browser session. That conclusion came from probing the WRONG endpoint: `/rest/inline-tasks/1.0/task/<id>` does 302-redirect PATs to `login.jsp` — but that is a different plugin's route, not the one these checkboxes use (re-confirmed 2026-08-12: inline-tasks 302s while the tasklist POST answers 204 with the same PAT). Curl gotchas: a JSON body returns 415 and a `?checked=` query param is ignored — the form body (`--data-urlencode checked=true`) is authoritative, and `curl` exits 0 even on a 4xx, so judge success by `-w %{http_code}` == 204, not the exit code.

Tick a box only when its work is verifiably done — the checkboxes are a progress signal, not a close-everything button.
