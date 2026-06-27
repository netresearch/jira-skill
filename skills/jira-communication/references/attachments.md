# Attachments — Upload and Download

## When to load

Load this reference whenever the user wants to attach a file to an issue, download an attachment, or work with attachment URLs (including any concerns about path traversal, size limits, or SSRF).

## Upload

```bash
# Simple upload (single file per invocation)
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-attachment.py add PROJ-123 screenshot.png

# Preview (no upload, just show what would be sent)
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-attachment.py add PROJ-123 /tmp/report.pdf --dry-run

# Multiple files — call `add` once per file
for file in a.png b.png c.pdf; do
    uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-attachment.py add PROJ-123 "$file"
done
```

`jira-attachment.py add` takes a single `FILE_PATH` argument (absolute or relative) and only requires that the file exists and is readable. There is no `--allow-absolute` flag and no cwd-confinement on the upload side — validate paths in the caller if needed.

## Download

`jira-attachment.py download` takes two positional arguments: the attachment URL and the output file path. Find the URL via `jira-issue.py get --json` (the `fields.attachment[].content` field carries the download URL).

```bash
# Positional: full URL (or /rest/api/2/attachment/content/<id>) + output file
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-attachment.py download \
    "https://jira.example.com/rest/api/2/attachment/content/12345" \
    ./attachments/report.pdf
```

The output location is the **second positional argument** (`OUTPUT_FILE`), not an option. There is **no `--output-dir` flag** on `download` — passing one fails with `Error: No such option: --output-dir` (exit 2). To choose a directory, either include it in the `OUTPUT_FILE` path (as above) or use `download-all --dir <dir>` (the `--dir` flag exists only on the `download-all` subcommand, not on `download`).

### Verify the download succeeded

`jira-attachment.py download` carries Jira authentication (PAT via `Authorization: Bearer`, or Cloud basic auth) and refuses to save a redirect/login body as the file. But if an attachment is ever fetched **without** auth (e.g. a hand-rolled `curl`/`wget`, or a CDN redirect followed without credentials), the request lands on the login page or an empty response and you get a **0-byte file that looks like success**. Always check the size after downloading:

```bash
out=./attachments/report.pdf
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-attachment.py download "$url" "$out"
[ -s "$out" ] || { echo "ERROR: empty download — check authentication" >&2; exit 1; }
```

`[ -s FILE ]` is true only when the file exists and is non-empty. A 0-byte result almost always means the request was unauthenticated.

## Download all attachments

To grab every attachment on an issue in one call (no need to harvest URLs first), use `download-all`. Files are saved under `--dir` (default cwd) using their original Jira filenames; duplicate names are disambiguated with the attachment id, and a filename that would escape `--dir` is skipped.

```bash
# All attachments into the current directory
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-attachment.py download-all PROJ-123

# Into a specific directory (created if missing, must stay within cwd)
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-attachment.py download-all PROJ-123 --dir ./attachments

# Preview the list without downloading
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-attachment.py download-all PROJ-123 --dry-run
```

## Safety guarantees

- **Path traversal**: output paths are constrained to the current working directory — the script rejects targets that resolve outside cwd. `cd` to the target directory before downloading. `download-all` additionally strips path components from each Jira-supplied filename and constrains it within `--dir`.

## Don't use raw curl

Fetching `/secure/attachment/...` URLs with plain `curl` returns the Jira login page, not the file — attachment downloads need the authenticated session handling this script provides. Always use `jira-attachment.py download`.
