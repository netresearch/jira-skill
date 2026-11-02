# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Tests for detect_jira_issues.py hook script."""

import json
import os
import sys
from pathlib import Path
from unittest import mock

import pytest

# Add scripts directory to path
_test_dir = Path(__file__).parent
_scripts_dir = _test_dir.parent / "scripts"
sys.path.insert(0, str(_scripts_dir))

from detect_jira_issues import (
    extract_issue_keys,
    extract_jira_hosts,
    resolve_profile_suggestion,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Tests: extract_issue_keys()
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractIssueKeys:
    def test_single_key(self):
        assert extract_issue_keys("Fix WEB-1381") == ["WEB-1381"]

    def test_multiple_keys(self):
        assert extract_issue_keys("WEB-1381 and NRS-4167") == ["NRS-4167", "WEB-1381"]

    def test_key_from_url(self):
        # Uses a non-placeholder key: PROJ-123 is a denylisted doc placeholder.
        keys = extract_issue_keys("https://jira.example.com/browse/WEB-1381")
        assert "WEB-1381" in keys

    def test_key_from_atlassian_url(self):
        keys = extract_issue_keys("https://company.atlassian.net/browse/CLOUD-42")
        assert "CLOUD-42" in keys

    def test_no_keys(self):
        assert extract_issue_keys("No issues here") == []

    def test_deduplicates(self):
        keys = extract_issue_keys("WEB-1381 see WEB-1381 again")
        assert keys == ["WEB-1381"]

    def test_underscore_in_prefix(self):
        keys = extract_issue_keys("FIX_ME-123 is an issue")
        assert "FIX_ME-123" in keys


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: extract_issue_keys() denylist — non-Jira PREFIX-123 false positives
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractIssueKeysDenylist:
    """PREFIX-123 shapes that are not Jira keys must not trigger detection."""

    NON_JIRA_TOKENS = [
        "CWE-918",
        "CVE-2024-1234",
        "UTF-8",
        "SHA-256",
        "ISO-8601",
        "RFC-2119",
        "MD5-7",
        "AES-256",
        "TLS-12",
        "PROJ-456",  # PROJ-/EXAMPLE- placeholders blocked by prefix, any number
        "EXAMPLE-99",
        "PROJ-123",  # literal doc placeholder
        "ABC-123",  # literal doc placeholder
        "GPL-2.0",  # SPDX license identifiers
        "AGPL-3.0",
        "LGPL-2.1",
        "MPL-2.0",
        "EPL-2.0",
        "EUPL-1.2",
        "CDDL-1.0",
        "BSL-1.0",  # Boost Software License
        "BUSL-1.1",  # Business Source License
    ]

    REAL_KEYS = [
        "NRS-4477",
        "JIRA-42",
        "WEB-1381",
        "FIX_ME-123",
    ]

    @pytest.mark.parametrize("token", NON_JIRA_TOKENS)
    def test_non_jira_token_not_detected(self, token):
        assert extract_issue_keys(f"see {token} for details") == []

    @pytest.mark.parametrize("key", REAL_KEYS)
    def test_real_key_still_detected(self, key):
        assert key in extract_issue_keys(f"work on {key} today")

    def test_security_ids_filtered_real_key_kept_in_same_text(self):
        text = "CWE-918 and CVE-2024-1234 relate to NRS-4477 and UTF-8 / SHA-256 encoding"
        assert extract_issue_keys(text) == ["NRS-4477"]

    def test_license_survey_line_detects_nothing(self):
        """A license survey line names an SPDX identifier and no ticket.

        Copied from the subagent report that made the prompt hook print
        "Detected Jira issue reference(s): GPL-2" on 2026-09-29.
        """
        text = (
            "- **„Open Core“ bei Planio:** Kern ist Redmine unter GPL-2.0, dazu "
            "nicht veröffentlichte Planio-Funktionen. „proprietär“ wäre ebenso "
            "vertretbar."
        )
        assert extract_issue_keys(text) == []

    def test_placeholder_filtered_from_url_too(self):
        """The PROJ-123 placeholder is filtered even inside a Jira /browse/ URL."""
        assert extract_issue_keys("https://jira.example.com/browse/PROJ-123") == []


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: extract_jira_hosts()
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractJiraHosts:
    def test_server_url(self):
        hosts = extract_jira_hosts("Check https://jira.example.com/browse/PROJ-1")
        expected = "https://jira.example.com"
        assert any(h == expected for h in hosts)

    def test_cloud_url(self):
        hosts = extract_jira_hosts("See https://company.atlassian.net/browse/CLOUD-1")
        expected = "https://company.atlassian.net"
        assert any(h == expected for h in hosts)

    def test_multiple_hosts(self):
        text = "https://jira.a.com/browse/A-1 and https://jira.b.com/browse/B-2"
        hosts = extract_jira_hosts(text)
        assert len(hosts) == 2

    def test_no_hosts(self):
        assert extract_jira_hosts("No URLs here WEB-123") == []

    def test_trailing_punctuation_stripped(self):
        """URLs with trailing punctuation like ').' should be cleaned."""
        hosts = extract_jira_hosts("see https://jira.example.com).")
        assert hosts == ["https://jira.example.com"]

    def test_trailing_comma_stripped(self):
        """URLs followed by comma should be cleaned."""
        hosts = extract_jira_hosts("check https://jira.example.com, and more")
        assert hosts == ["https://jira.example.com"]


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: resolve_profile_suggestion()
# ═══════════════════════════════════════════════════════════════════════════════

SAMPLE_PROFILES = {
    "version": 1,
    "default": "netresearch",
    "profiles": {
        "netresearch": {
            "url": "https://jira.netresearch.de",
            "auth": "pat",
            "token": "x",
            "projects": ["NRS", "OPSMKK"],
        },
        "mkk": {"url": "https://jira.meine-krankenkasse.de", "auth": "pat", "token": "y", "projects": ["WEB", "INFRA"]},
    },
}


class TestResolveProfileSuggestion:
    def test_resolve_via_host(self, tmp_path):
        profiles_file = tmp_path / "profiles.json"
        profiles_file.write_text(json.dumps(SAMPLE_PROFILES))

        with mock.patch("detect_jira_issues.PROFILES_FILE", profiles_file):
            result = resolve_profile_suggestion(issue_keys=["WEB-1"], hosts=["https://jira.meine-krankenkasse.de"])
            assert result == "mkk"

    def test_resolve_via_project_key(self, tmp_path):
        profiles_file = tmp_path / "profiles.json"
        profiles_file.write_text(json.dumps(SAMPLE_PROFILES))

        with mock.patch("detect_jira_issues.PROFILES_FILE", profiles_file):
            result = resolve_profile_suggestion(issue_keys=["NRS-4167"], hosts=[])
            assert result == "netresearch"

    def test_no_profiles_file(self, tmp_path):
        with mock.patch("detect_jira_issues.PROFILES_FILE", tmp_path / "nonexistent.json"):
            result = resolve_profile_suggestion(["WEB-1"], [])
            assert result is None

    def test_no_match(self, tmp_path):
        profiles_file = tmp_path / "profiles.json"
        profiles_file.write_text(json.dumps(SAMPLE_PROFILES))

        with mock.patch("detect_jira_issues.PROFILES_FILE", profiles_file):
            result = resolve_profile_suggestion(issue_keys=["UNKNOWN-999"], hosts=[])
            assert result is None

    def test_host_takes_priority_over_key(self, tmp_path):
        """Host matching should resolve before project key matching."""
        profiles_file = tmp_path / "profiles.json"
        profiles_file.write_text(json.dumps(SAMPLE_PROFILES))

        with mock.patch("detect_jira_issues.PROFILES_FILE", profiles_file):
            # NRS belongs to netresearch, but host is mkk
            result = resolve_profile_suggestion(issue_keys=["NRS-1"], hosts=["https://jira.meine-krankenkasse.de"])
            assert result == "mkk"

    def test_ambiguous_project_key_returns_none(self, tmp_path):
        """When same project key is in multiple profiles, return None (no suggestion)."""
        ambiguous = {
            "version": 1,
            "profiles": {
                "a": {"url": "https://a.com", "auth": "pat", "token": "x", "projects": ["WEB"]},
                "b": {"url": "https://b.com", "auth": "pat", "token": "y", "projects": ["WEB"]},
            },
        }
        profiles_file = tmp_path / "profiles.json"
        profiles_file.write_text(json.dumps(ambiguous))

        with mock.patch("detect_jira_issues.PROFILES_FILE", profiles_file):
            result = resolve_profile_suggestion(["WEB-100"], [])
            assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: resolve_profile_suggestion() with malformed profiles.json
# ═══════════════════════════════════════════════════════════════════════════════


class TestResolveProfileSuggestionMalformed:
    """resolve_profile_suggestion() must not crash on unexpected JSON shapes."""

    def test_json_is_list_returns_none(self, tmp_path):
        """profiles.json containing a JSON list instead of dict."""
        profiles_file = tmp_path / "profiles.json"
        profiles_file.write_text(json.dumps(["not", "a", "dict"]))

        with mock.patch("detect_jira_issues.PROFILES_FILE", profiles_file):
            result = resolve_profile_suggestion(["WEB-1"], [])
            assert result is None

    def test_profiles_key_is_list_returns_none(self, tmp_path):
        """profiles.json where 'profiles' value is a list instead of dict."""
        profiles_file = tmp_path / "profiles.json"
        profiles_file.write_text(json.dumps({"profiles": ["not", "a", "dict"]}))

        with mock.patch("detect_jira_issues.PROFILES_FILE", profiles_file):
            result = resolve_profile_suggestion(["WEB-1"], [])
            assert result is None

    def test_profiles_key_is_string_returns_none(self, tmp_path):
        """profiles.json where 'profiles' value is a string."""
        profiles_file = tmp_path / "profiles.json"
        profiles_file.write_text(json.dumps({"profiles": "not a dict"}))

        with mock.patch("detect_jira_issues.PROFILES_FILE", profiles_file):
            result = resolve_profile_suggestion(["WEB-1"], [])
            assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: main() hook output references current architecture
# ═══════════════════════════════════════════════════════════════════════════════


class TestMainOutput:
    """main() hook output must reference current script architecture, not old MCP."""

    def _run_hook(self, prompt_text, tmp_path, capsys):
        """Run detect_jira_issues.main() with mocked stdin."""
        input_data = json.dumps({"prompt": prompt_text})
        fake_profiles = tmp_path / "nonexistent" / "profiles.json"
        with mock.patch("sys.stdin") as mock_stdin, mock.patch("detect_jira_issues.PROFILES_FILE", fake_profiles):
            mock_stdin.read.return_value = input_data
            from detect_jira_issues import main

            main()
        return capsys.readouterr()

    def test_output_does_not_reference_mcp(self, tmp_path, capsys):
        """Hook output must not reference obsolete MCP architecture."""
        captured = self._run_hook("Check WEB-1381", tmp_path, capsys)
        assert "mcp-atlassian" not in captured.out.lower()
        assert "jira_get_issue" not in captured.out
        assert "jira_search" not in captured.out

    def test_output_references_script_names(self, tmp_path, capsys):
        """Hook output should mention actual script names."""
        captured = self._run_hook("Check WEB-1381", tmp_path, capsys)
        assert "jira-issue.py" in captured.out
        assert "jira-search.py" in captured.out

    def test_output_uses_uv_run(self, tmp_path, capsys):
        """Hook output must use 'uv run', never bare 'python3' invocation."""
        captured = self._run_hook("Check WEB-1381", tmp_path, capsys)
        assert "uv run" in captured.out
        # Every script reference should be prefixed with 'uv run'
        for script in ["jira-issue.py", "jira-comment.py", "jira-search.py"]:
            assert "uv run" in captured.out.split(script)[0].split("\n")[-1]

    def test_output_includes_full_paths(self, tmp_path, capsys):
        """Hook output must include full paths to scripts, not bare filenames."""
        captured = self._run_hook("Check WEB-1381", tmp_path, capsys)
        assert "/core/jira-issue.py" in captured.out
        assert "/workflow/jira-comment.py" in captured.out

    def test_output_warns_against_python3(self, tmp_path, capsys):
        """Hook output should warn against using python3 directly."""
        captured = self._run_hook("Check WEB-1381", tmp_path, capsys)
        assert "never" in captured.out.lower() and "python3" in captured.out

    def test_output_routes_to_the_skill_not_only_to_scripts(self, tmp_path, capsys):
        """The scripts are the skill's execution layer, never an alternative to it.

        Presenting them as an equivalent path ("… or run scripts directly")
        cost a service record its version field: the conventions live in the
        skill, and only the scripts were used.
        """
        captured = self._run_hook("Check WEB-1381", tmp_path, capsys)
        assert "Invoke the jira-communication skill" in captured.out
        assert "or run scripts directly" not in captured.out
        assert "not a substitute for it" in captured.out

    def test_output_names_the_netresearch_skill(self, tmp_path, capsys):
        """NR custom-field conventions live in a separate skill the hook must name."""
        captured = self._run_hook("Check WEB-1381", tmp_path, capsys)
        assert "netresearch-jira" in captured.out

    def test_output_points_at_the_full_field_read(self, tmp_path, capsys):
        """A record is brought up to date through its fields, not only its prose."""
        captured = self._run_hook("Check WEB-1381", tmp_path, capsys)
        assert "--json get" in captured.out


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: main() stays silent for task notifications and names a key once per
# session (#276)
# ═══════════════════════════════════════════════════════════════════════════════

# The prompt Claude Code passes to the hook when a background subagent reports
# back, as captured from a real session (Claude Code 2.1.316). The hook input
# carries no other field that marks the frame.
SUBAGENT_REPORT = """<task-notification>
<task-id>a1d923bd7b082510e</task-id>
<tool-use-id>toolu_01RPbRuTfnu5ebqqPEamQACW</tool-use-id>
<output-file>/tmp/claude-1000/project/session/tasks/a1d923bd7b082510e.output</output-file>
<status>completed</status>
<summary>Agent "Probe report" finished</summary>
<result>Updated WEB-1381 and checked NRS-4167.</result>
</task-notification>"""


class TestSessionNoise:
    """The hook speaks for prompts the user typed, once per key and session."""

    SESSION = "01dd3f54-f309-4a12-88a6-ccffa583560d"

    @pytest.fixture(autouse=True)
    def _isolated_state(self, tmp_path):
        self.state_dir = tmp_path / "state"
        with (
            mock.patch("detect_jira_issues.STATE_DIR", self.state_dir),
            mock.patch("detect_jira_issues.PROFILES_FILE", tmp_path / "nonexistent" / "profiles.json"),
        ):
            yield

    def _run(self, capsys, prompt, session_id=SESSION, event="UserPromptSubmit"):
        payload = {"hook_event_name": event, "prompt": prompt}
        if session_id is not None:
            payload["session_id"] = session_id
        with mock.patch("sys.stdin") as mock_stdin:
            mock_stdin.read.return_value = json.dumps(payload)
            from detect_jira_issues import main

            main()
        return capsys.readouterr().out

    @staticmethod
    def _detected(out):
        for line in out.splitlines():
            if line.startswith("Detected Jira issue reference(s): "):
                return line.removeprefix("Detected Jira issue reference(s): ").split(", ")
        return []

    def test_subagent_report_stays_silent(self, capsys):
        assert self._run(capsys, SUBAGENT_REPORT) == ""

    def test_background_command_notification_stays_silent(self, capsys):
        prompt = (
            "<task-notification>\n<task-id>bjgrw5t5o</task-id>\n<status>completed</status>\n"
            '<summary>Background command "echo WEB-1381" completed (exit code 0)</summary>\n'
            "</task-notification>"
        )
        assert self._run(capsys, prompt) == ""

    def test_key_from_report_still_fires_when_user_types_it(self, capsys):
        """A silenced report must not mark its keys as already named."""
        self._run(capsys, SUBAGENT_REPORT)
        assert self._detected(self._run(capsys, "Look at WEB-1381")) == ["WEB-1381"]

    def test_typed_key_fires_once_per_session(self, capsys):
        assert self._detected(self._run(capsys, "Fix WEB-1381")) == ["WEB-1381"]
        assert self._run(capsys, "Did WEB-1381 work?") == ""

    def test_new_key_fires_with_only_the_new_key(self, capsys):
        self._run(capsys, "Fix WEB-1381")
        assert self._detected(self._run(capsys, "WEB-1381 and NRS-4167")) == ["NRS-4167"]

    def test_other_session_fires_again(self, capsys):
        self._run(capsys, "Fix WEB-1381")
        out = self._run(capsys, "Fix WEB-1381", session_id="9f0c2b8e-0000-4000-8000-000000000001")
        assert self._detected(out) == ["WEB-1381"]

    def test_without_session_id_fires_every_time(self, capsys):
        assert self._detected(self._run(capsys, "Fix WEB-1381", session_id=None)) == ["WEB-1381"]
        assert self._detected(self._run(capsys, "Fix WEB-1381", session_id=None)) == ["WEB-1381"]

    @pytest.mark.parametrize("session_id", ["../escape", "a/b", "", 42])
    def test_unusable_session_id_fires_every_time(self, capsys, session_id):
        assert self._detected(self._run(capsys, "Fix WEB-1381", session_id=session_id)) == ["WEB-1381"]
        assert self._detected(self._run(capsys, "Fix WEB-1381", session_id=session_id)) == ["WEB-1381"]
        assert not self.state_dir.exists() or list(self.state_dir.iterdir()) == []

    def test_corrupt_state_file_fails_open(self, capsys):
        self.state_dir.mkdir(mode=0o700)
        (self.state_dir / f"{self.SESSION}.json").write_text("{not json")
        assert self._detected(self._run(capsys, "Fix WEB-1381")) == ["WEB-1381"]

    def test_unwritable_state_dir_fails_open(self, capsys, tmp_path):
        blocker = tmp_path / "blocker"
        blocker.write_text("a file where the parent directory should be")
        with mock.patch("detect_jira_issues.STATE_DIR", blocker / "state"):
            assert self._detected(self._run(capsys, "Fix WEB-1381")) == ["WEB-1381"]
            assert self._detected(self._run(capsys, "Fix WEB-1381")) == ["WEB-1381"]

    @pytest.mark.skipif(not hasattr(os, "getuid"), reason="POSIX permissions")
    def test_state_dir_open_to_others_is_not_used(self, capsys):
        self.state_dir.mkdir(mode=0o700)
        self.state_dir.chmod(0o777)
        self._run(capsys, "Fix WEB-1381")
        assert self._detected(self._run(capsys, "Fix WEB-1381")) == ["WEB-1381"]
        assert list(self.state_dir.iterdir()) == []

    @pytest.mark.skipif(not hasattr(os, "getuid"), reason="POSIX permissions")
    def test_symlinked_state_dir_is_not_used(self, capsys, tmp_path):
        target = tmp_path / "elsewhere"
        target.mkdir(mode=0o700)
        self.state_dir.symlink_to(target)
        self._run(capsys, "Fix WEB-1381")
        assert self._detected(self._run(capsys, "Fix WEB-1381")) == ["WEB-1381"]
        assert list(target.iterdir()) == []

    @pytest.mark.skipif(not hasattr(os, "getuid"), reason="POSIX permissions")
    def test_state_dir_is_private(self, capsys):
        self._run(capsys, "Fix WEB-1381")
        assert self.state_dir.stat().st_mode & 0o777 == 0o700
        assert [p.name for p in self.state_dir.iterdir()] == [f"{self.SESSION}.json"]

    def test_notification_after_leading_whitespace_stays_silent(self, capsys):
        assert self._run(capsys, "\n  " + SUBAGENT_REPORT) == ""

    def test_typed_prompt_quoting_the_tag_still_fires(self, capsys):
        """Only a prompt that starts with the wrapper is a notification."""
        out = self._run(capsys, "Why did <task-notification> mention WEB-1381?")
        assert self._detected(out) == ["WEB-1381"]

    @pytest.mark.parametrize("source", ["compact", "clear"])
    def test_session_start_forgets_the_keys(self, capsys, source):
        """After compaction the earlier hint is gone from the context."""
        self._run(capsys, "Fix WEB-1381")
        payload = {"hook_event_name": "SessionStart", "source": source, "session_id": self.SESSION}
        with mock.patch("sys.stdin") as mock_stdin:
            mock_stdin.read.return_value = json.dumps(payload)
            from detect_jira_issues import main

            main()
        assert capsys.readouterr().out == ""
        assert self._detected(self._run(capsys, "Fix WEB-1381")) == ["WEB-1381"]

    def test_session_start_leaves_other_sessions_alone(self, capsys):
        self._run(capsys, "Fix WEB-1381")
        self._run(capsys, "", session_id="9f0c2b8e-0000-4000-8000-000000000001", event="SessionStart")
        assert self._run(capsys, "Fix WEB-1381") == ""

    def test_session_id_with_trailing_newline_is_not_used(self, capsys):
        session_id = self.SESSION + "\n"
        assert self._detected(self._run(capsys, "Fix WEB-1381", session_id=session_id)) == ["WEB-1381"]
        assert self._detected(self._run(capsys, "Fix WEB-1381", session_id=session_id)) == ["WEB-1381"]

    def test_keys_are_recorded_only_after_the_hint_is_printed(self, capsys):
        """A run that dies while printing must not mark the key as named."""
        with mock.patch("builtins.print", side_effect=BrokenPipeError):
            with pytest.raises(BrokenPipeError):
                self._run(capsys, "Fix WEB-1381")
        assert self._detected(self._run(capsys, "Fix WEB-1381")) == ["WEB-1381"]

    def test_windows_mode_bits_do_not_disable_dedup(self, capsys):
        """Windows reads every writable directory as 0o777 and has no getuid."""
        self.state_dir.mkdir()
        self.state_dir.chmod(0o777)
        with mock.patch("detect_jira_issues.POSIX_OWNERSHIP", False):
            assert self._detected(self._run(capsys, "Fix WEB-1381")) == ["WEB-1381"]
            assert self._run(capsys, "Fix WEB-1381") == ""
