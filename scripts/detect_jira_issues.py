#!/usr/bin/env python3
"""
UserPromptSubmit hook to detect Jira issue keys in user messages.
Provides context about detected issues, suggests using the jira skill,
and resolves Jira profiles when multi-profile support is configured.
"""

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

# Jira issue key pattern: PROJECT-123
# Common project prefixes for Netresearch
ISSUE_KEY_PATTERN = r"\b([A-Z][A-Z0-9_]+-\d+)\b"

# Jira URL patterns
JIRA_URL_PATTERNS = [
    r"https?://jira\.[^/]+/browse/([A-Z][A-Z0-9_]+-\d+)",
    r"https?://[^/]+\.atlassian\.net/browse/([A-Z][A-Z0-9_]+-\d+)",
]

# Full URL pattern to extract hosts
JIRA_HOST_PATTERN = r"(https?://(?:jira\.[^\s/]+|[^\s/]+\.atlassian\.net))"

PROFILES_FILE = Path.home() / ".jira" / "profiles.json"


def _normalize_netloc(url: str) -> str:
    """Normalize a URL's netloc by lowercasing and stripping default ports."""
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    scheme = parsed.scheme.lower()
    if scheme == 'https' and host.endswith(':443'):
        host = host[:-4]
    elif scheme == 'http' and host.endswith(':80'):
        host = host[:-3]
    return host


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


def extract_jira_hosts(text: str) -> list[str]:
    """Extract unique Jira host URLs from text."""
    hosts = set()
    for match in re.finditer(JIRA_HOST_PATTERN, text):
        # Strip trailing punctuation that the regex may have captured
        # (e.g., "https://jira.example.com)." → "https://jira.example.com")
        raw = match.group(1).rstrip('/').rstrip('.,;:!?)\'"')
        parsed = urlparse(raw)
        if parsed.netloc:
            hosts.add(f"{parsed.scheme}://{parsed.netloc}")
    return sorted(hosts)


def resolve_profile_suggestion(issue_keys: list[str], hosts: list[str]) -> str | None:
    """Try to resolve a profile name from issue keys or hosts.

    Returns:
        Profile name suggestion, or None if no match or no profiles configured.
    """
    if not PROFILES_FILE.exists():
        return None

    try:
        data = json.loads(PROFILES_FILE.read_text())
    except json.JSONDecodeError:
        return None

    # Validate expected structure: must be a dict with a 'profiles' dict
    if not isinstance(data, dict):
        return None

    profiles = data.get('profiles', {})
    if not isinstance(profiles, dict) or not profiles:
        return None

    # Try host matching first (normalize default ports for reliable comparison)
    for host_url in hosts:
        input_host = _normalize_netloc(host_url)
        for name, prof in profiles.items():
            prof_host = _normalize_netloc(prof.get('url', ''))
            if prof_host and prof_host == input_host:
                return name

    # Try project key matching
    for key in issue_keys:
        prefix_match = re.match(r'^([A-Z][A-Z0-9_]+)-\d+$', key)
        if prefix_match:
            prefix = prefix_match.group(1)
            matches = [name for name, prof in profiles.items()
                       if isinstance(prof.get('projects'), list) and prefix in prof['projects']]
            if len(matches) == 1:
                return matches[0]

    return None


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

    # Extract issue keys and hosts
    issue_keys = extract_issue_keys(prompt)
    hosts = extract_jira_hosts(prompt)

    if issue_keys:
        keys_str = ", ".join(issue_keys)

        # Try to resolve profile
        profile_name = resolve_profile_suggestion(issue_keys, hosts)

        profile_hint = ""
        if profile_name:
            profile_hint = f"\nSuggested profile: {profile_name}\nUse: --profile {profile_name}"

        print(f"""<system-reminder>
Detected Jira issue reference(s): {keys_str}
{profile_hint}
The jira-integration skill can help:
- Fetch issue details: jira-issue.py get KEY
- Search issues: jira-search.py query "JQL"
- Transition status: jira-transition.py do KEY "Status"
- Add comments: jira-comment.py add KEY "text"
- Log work: jira-worklog.py add KEY "2h"

Use Jira wiki markup (not Markdown) for descriptions and comments.
</system-reminder>""")


if __name__ == "__main__":
    main()
