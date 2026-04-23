# Attachments — Upload and Download

## When to load

Load this reference whenever the user wants to attach a file to an issue, download an attachment, or work with attachment URLs (including any concerns about path traversal, size limits, or SSRF).

## Upload

```bash
# Simple upload
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-attachment.py add PROJ-123 screenshot.png

# Preview (no upload, just show what would be sent)
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-attachment.py add PROJ-123 /tmp/report.pdf --dry-run

# Multiple files
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-attachment.py add PROJ-123 a.png b.png c.pdf
```

The script resolves relative paths against the current working directory and refuses paths escaping the cwd (`..` segments) unless `--allow-absolute` is passed.

## Download

`jira-attachment.py download` takes two positional arguments: the attachment URL and the output file path. Find the URL via `jira-issue.py get --json` (the `fields.attachment[].content` field carries the download URL).

```bash
# Positional: full URL (or /rest/api/2/attachment/content/<id>) + output file
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-attachment.py download \
    "https://jira.example.com/rest/api/2/attachment/content/12345" \
    ./attachments/report.pdf
```

## Safety guarantees

- **Path traversal**: output paths are constrained to the current working directory — the script rejects targets that resolve outside cwd.
