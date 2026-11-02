#!/usr/bin/env -S uv run --script
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

"""
UserPromptSubmit hook to detect Jira issue keys in user messages.
Provides context about detected issues, suggests using the jira skill,
and resolves Jira profiles when multi-profile support is configured.

The hook stays silent for background-task reports (subagent results,
finished background commands) and names each key at most once per
session. Registered for SessionStart after compaction or /clear,
it forgets the keys of that session, because the earlier hint is no
longer in the model's context.
"""

import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

# Claude Code also runs UserPromptSubmit for the reports of background
# subagents and the completions of background commands. Their hook input
# carries the same fields as a typed prompt (session_id, cwd, prompt_id,
# permission_mode, hook_event_name, prompt) and nothing that marks the
# origin; the only signal is the wrapper the prompt text starts with.
TASK_NOTIFICATION_TAG = "<task-notification>"

# Windows has no getuid and reports no POSIX owner or mode bits.
POSIX_OWNERSHIP = hasattr(os, "getuid")


def _default_state_dir() -> Path | None:
    """Return the per-user directory for the per-session key records.

    POSIX: a 0700 directory in the temp dir, named after the uid; owner and
    mode are checked before each use. Windows: the temp dir can be a shared
    one (TEMP may point at %SYSTEMROOT%\\Temp) and mode bits say nothing, so
    the state lives under %LOCALAPPDATA%, which belongs to the user profile;
    without it there is no deduplication.
    """
    if POSIX_OWNERSHIP:
        return Path(tempfile.gettempdir()) / f"jira-skill-hook-{os.getuid()}"
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return None
    return Path(local_app_data) / "jira-skill" / "hook-state"


STATE_DIR = _default_state_dir()

# Session ids are UUIDs; anything else is not used as a file name.
SESSION_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,128}")

# Jira issue key pattern: PROJECT-123
# Common project prefixes for Netresearch
ISSUE_KEY_PATTERN = r"\b([A-Z][A-Z0-9_]+-\d+)\b"

# PREFIX-123 shapes that look like issue keys but never are: security
# identifiers (CVE-2024, CWE-918, GHSA-…), encodings/standards/crypto
# (UTF-8, SHA-256, ISO-8601, RFC-2119, MD5-…, AES-256, TLS-12), and the
# universal doc placeholders PROJ-/EXAMPLE- (any number, e.g. PROJ-456),
# and SPDX license identifiers with a version (GPL, AGPL, LGPL, MPL, EPL,
# EUPL, CDDL, BSL for the Boost Software License and BUSL for the Business
# Source License), which a license survey lists by the dozen. BSD stays
# detectable: it is a real project key.
NON_JIRA_KEY_PREFIXES = frozenset(
    {"CVE", "CWE", "GHSA", "ISO", "RFC", "UTF", "SHA", "MD5", "AES", "TLS", "PROJ", "EXAMPLE"}
    | {"GPL", "AGPL", "LGPL", "MPL", "EPL", "EUPL", "CDDL", "BSL", "BUSL"}
)

# Literal placeholder keys used in docs and examples (not real tickets).
PLACEHOLDER_KEYS = frozenset({"ABC-123"})

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
    if scheme == "https" and host.endswith(":443"):
        host = host[:-4]
    elif scheme == "http" and host.endswith(":80"):
        host = host[:-3]
    return host


def _is_jira_key(key: str) -> bool:
    """Return False for PREFIX-123 shapes that are never real Jira issue keys.

    Filters out literal doc placeholders (PROJ-123) and non-Jira identifier
    classes such as security IDs (CVE-2024-1234, CWE-918) and encodings or
    standards (UTF-8, SHA-256, ISO-8601, RFC-2119). Real project keys such as
    NRS-4477 are kept.
    """
    if key in PLACEHOLDER_KEYS:
        return False
    prefix = key.rsplit("-", 1)[0]
    return prefix not in NON_JIRA_KEY_PREFIXES


def extract_issue_keys(text: str) -> list[str]:
    """Extract unique Jira issue keys from text."""
    keys = set()

    # Direct issue keys
    for match in re.finditer(ISSUE_KEY_PATTERN, text):
        key = match.group(1)
        if _is_jira_key(key):
            keys.add(key)

    # Issue keys from URLs (inherently Jira, but stay consistent and drop
    # placeholder/non-Jira shapes like .../browse/PROJ-123 too).
    for pattern in JIRA_URL_PATTERNS:
        for match in re.finditer(pattern, text):
            key = match.group(1)
            if _is_jira_key(key):
                keys.add(key)

    return sorted(keys)


def extract_jira_hosts(text: str) -> list[str]:
    """Extract unique Jira host URLs from text."""
    hosts = set()
    for match in re.finditer(JIRA_HOST_PATTERN, text):
        # Strip trailing punctuation that the regex may have captured
        # (e.g., "https://jira.example.com)." → "https://jira.example.com")
        raw = match.group(1).rstrip("/").rstrip(".,;:!?)'\"")
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

    profiles = data.get("profiles", {})
    if not isinstance(profiles, dict) or not profiles:
        return None

    # Try host matching first (normalize default ports for reliable comparison)
    for host_url in hosts:
        input_host = _normalize_netloc(host_url)
        for name, prof in profiles.items():
            prof_host = _normalize_netloc(prof.get("url", ""))
            if prof_host and prof_host == input_host:
                return name

    # Try project key matching
    for key in issue_keys:
        prefix_match = re.match(r"^([A-Z][A-Z0-9_]+)-\d+$", key)
        if prefix_match:
            prefix = prefix_match.group(1)
            matches = [
                name
                for name, prof in profiles.items()
                if isinstance(prof.get("projects"), list) and prefix in prof["projects"]
            ]
            if len(matches) == 1:
                return matches[0]

    return None


def is_task_notification(prompt: str) -> bool:
    """Return True for a background-task report Claude Code submits itself."""
    return prompt.lstrip().startswith(TASK_NOTIFICATION_TAG)


def _state_file(session_id: object) -> Path | None:
    """Return the state file for a session, or None if it cannot be used safely.

    Refuses a malformed session id and a state directory that is a symlink,
    belongs to another user, or is open to group or others.
    """
    if STATE_DIR is None:
        return None
    if not isinstance(session_id, str) or not SESSION_ID_PATTERN.fullmatch(session_id):
        return None
    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = STATE_DIR.lstat()
    if not stat.S_ISDIR(info.st_mode):
        return None
    # Windows reads every writable directory as 0o777; there the location
    # under %LOCALAPPDATA% keeps the state per user (see _default_state_dir).
    if POSIX_OWNERSHIP and (info.st_uid != os.getuid() or info.st_mode & 0o077):
        return None
    return STATE_DIR / f"{session_id}.json"


def _read_seen(state_file: Path) -> set[str] | None:
    """Return the keys recorded in a state file, or None if it is unreadable."""
    try:
        seen = json.loads(state_file.read_text())
    except FileNotFoundError:
        return set()
    if not isinstance(seen, list):
        return None
    return {key for key in seen if isinstance(key, str)}


def filter_unseen_keys(session_id: object, issue_keys: list[str]) -> list[str]:
    """Return the keys not yet named in this session.

    Fails open: without a usable session id or state file, every key counts
    as unseen, which is the behaviour without deduplication.
    """
    try:
        state_file = _state_file(session_id)
        seen = _read_seen(state_file) if state_file else None
    except Exception:
        return issue_keys
    if seen is None:
        return issue_keys
    return [key for key in issue_keys if key not in seen]


def record_seen_keys(session_id: object, issue_keys: list[str]) -> None:
    """Add keys to the session's record; any failure leaves it unchanged."""
    try:
        state_file = _state_file(session_id)
        if state_file is None:
            return
        seen = _read_seen(state_file) or set()
        # Write to a temporary file and rename it over the state file, so a
        # concurrent reader never sees a partly written file.
        fd, tmp_name = tempfile.mkstemp(dir=STATE_DIR, prefix=".tmp-", suffix=".json")
        try:
            with os.fdopen(fd, "w") as handle:
                json.dump(sorted(seen | set(issue_keys)), handle)
            os.replace(tmp_name, state_file)
        finally:
            # After a successful replace the temporary name no longer exists.
            Path(tmp_name).unlink(missing_ok=True)
    except Exception:
        return


def forget_session(session_id: object) -> None:
    """Drop the session's record, so its keys are named again."""
    try:
        state_file = _state_file(session_id)
        if state_file is not None:
            state_file.unlink(missing_ok=True)
    except Exception:
        return


def main():
    try:
        input_data = sys.stdin.read()
    except Exception:
        return

    if not input_data:
        return

    # Parse user prompt
    session_id = None
    try:
        data = json.loads(input_data)
        prompt = data.get("prompt", "") or data.get("content", "") or data.get("message", "")
        session_id = data.get("session_id")
        event = data.get("hook_event_name")
    except (json.JSONDecodeError, TypeError):
        prompt = input_data
        event = None

    # After compaction or /clear the earlier hint has left the
    # model's context; forget the session's keys so they are named again.
    if event == "SessionStart":
        forget_session(session_id)
        return

    if not prompt:
        return

    # A background subagent's report quotes keys the user did not type. Stay
    # silent and leave the session state alone, so a key that only appeared
    # in a report still fires once the user names it.
    if is_task_notification(prompt):
        return

    # Extract issue keys and hosts
    issue_keys = extract_issue_keys(prompt)
    hosts = extract_jira_hosts(prompt)

    if issue_keys:
        issue_keys = filter_unseen_keys(session_id, issue_keys)

    if issue_keys:
        keys_str = ", ".join(issue_keys)

        # Try to resolve profile
        profile_name = resolve_profile_suggestion(issue_keys, hosts)

        profile_hint = ""
        if profile_name:
            profile_hint = f"\nSuggested profile: {profile_name}\nUse: --profile {profile_name}"

        # Resolve the plugin root so commands include absolute paths.
        # During hook execution CLAUDE_PLUGIN_ROOT is set by the harness;
        # fall back to deriving it from this script's own location.
        plugin_root = os.environ.get(
            "CLAUDE_PLUGIN_ROOT",
            str(Path(__file__).resolve().parent.parent),
        )
        scripts_dir = f"{plugin_root}/skills/jira-communication/scripts"

        print(f"""<system-reminder>
Detected Jira issue reference(s): {keys_str}
{profile_hint}
Invoke the jira-communication skill with the Skill tool before acting. The
commands below are its execution layer, not a substitute for it: the skill
carries the conventions the scripts do not — which fields a project expects,
wiki markup, the QA checklist. Netresearch-specific conventions (custom field
IDs, per-project workflow states) live in the separate netresearch-jira skill;
invoke that one too when the key belongs to an NR project.

Commands (always uv run, NOT python3):

- Fetch issue details: uv run {scripts_dir}/core/jira-issue.py get KEY
- Full context (description + all comments): uv run {scripts_dir}/core/jira-issue.py work KEY
- Search issues: uv run {scripts_dir}/core/jira-search.py query "JQL"
- Create an issue: uv run {scripts_dir}/workflow/jira-create.py issue PROJ "Summary" --type Task
- Transition status: uv run {scripts_dir}/workflow/jira-transition.py do KEY "Status"
- Set fields (assignee, custom fields): uv run {scripts_dir}/core/jira-issue.py update KEY --fields-json '{{"assignee": {{"name": "username"}}}}'
- Read EVERY populated field, not just the description: uv run {scripts_dir}/core/jira-issue.py --json get KEY
- Add comments: uv run {scripts_dir}/workflow/jira-comment.py add KEY "text"
- Log work: uv run {scripts_dir}/core/jira-worklog.py add KEY "2h"

IMPORTANT: Always use `uv run`, never `python3` — scripts declare inline
dependencies (PEP 723) that uv resolves automatically.

Use Jira wiki markup (not Markdown) for descriptions and comments.

Bringing a record up to date means its fields, not only its prose — read them
with --json get before deciding what was stale.
</system-reminder>""")
        # Record only after printing: a run killed before this point names the
        # keys again next time instead of never.
        record_seen_keys(session_id, issue_keys)


if __name__ == "__main__":
    main()
