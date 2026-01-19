#!/usr/bin/env python3
"""
UserPromptSubmit hook to detect Jira issue keys in user messages.
Provides context about detected issues and suggests using the jira skill.
"""

import sys
import re
import json

# Jira issue key pattern: PROJECT-123
# Common project prefixes for Netresearch
ISSUE_KEY_PATTERN = r"\b([A-Z][A-Z0-9_]+-\d+)\b"

# Jira URL patterns
JIRA_URL_PATTERNS = [
    r"https?://jira\.[^/]+/browse/([A-Z][A-Z0-9_]+-\d+)",
    r"https?://[^/]+\.atlassian\.net/browse/([A-Z][A-Z0-9_]+-\d+)",
]


def extract_issue_keys(text: str) -> list[str]:
    """Extract unique Jira issue keys from text."""
    keys = set()

    # Direct issue keys
    for match in re.finditer(ISSUE_KEY_PATTERN, text):
        keys.add(match.group(1))

    # Issue keys from URLs
    for pattern in JIRA_URL_PATTERNS:
        for match in re.finditer(pattern, text):
            keys.add(match.group(1))

    return sorted(keys)


def main():
    try:
        input_data = sys.stdin.read()
    except Exception:
        return

    if not input_data:
        return

    # Parse user prompt
    try:
        data = json.loads(input_data)
        prompt = data.get("prompt", "") or data.get("content", "") or data.get("message", "")
    except (json.JSONDecodeError, TypeError):
        prompt = input_data

    if not prompt:
        return

    # Extract issue keys
    issue_keys = extract_issue_keys(prompt)

    if issue_keys:
        keys_str = ", ".join(issue_keys)
        print(f"""<system-reminder>
Detected Jira issue reference(s): {keys_str}

The jira-integration skill can help:
- Fetch issue details with jira_get_issue
- Search related issues with jira_search
- Update issue status/comments
- Use Jira wiki markup for formatting

Use the mcp-atlassian MCP server for API operations if available.
</system-reminder>""")


if __name__ == "__main__":
    main()
