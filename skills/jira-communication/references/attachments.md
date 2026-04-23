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

```bash
# By issue key — lists attachments and prompts for selection
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-attachment.py download PROJ-123

# By attachment ID (found in `jira-issue.py get --json`)
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-attachment.py download --id 12345

# By direct URL — constrained to the configured Jira host
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-attachment.py download \
    --url "https://jira.example.com/secure/attachment/12345/file.pdf"
```

## Safety guarantees

- **Host pinning**: `--url` downloads reject any host that does not match the active profile's `JIRA_URL` — an SSRF protection. The script prints the rejection reason in `--debug` mode.
- **Path traversal**: Output paths are normalized; downloads refuse targets outside the chosen `--output` directory.
- **Size cap**: Default 100 MB per download. Override with `--max-bytes N`. The script streams to disk, so memory use is constant.
