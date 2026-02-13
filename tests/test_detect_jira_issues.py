"""Tests for detect_jira_issues.py hook script."""

import json
import sys
from pathlib import Path
from unittest import mock

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
        keys = extract_issue_keys("https://jira.example.com/browse/PROJ-123")
        assert "PROJ-123" in keys

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
            "projects": ["NRS", "OPSMKK"]
        },
        "mkk": {
            "url": "https://jira.meine-krankenkasse.de",
            "auth": "pat",
            "token": "y",
            "projects": ["WEB", "INFRA"]
        }
    }
}


class TestResolveProfileSuggestion:
    def test_resolve_via_host(self, tmp_path):
        profiles_file = tmp_path / "profiles.json"
        profiles_file.write_text(json.dumps(SAMPLE_PROFILES))

        with mock.patch('detect_jira_issues.PROFILES_FILE', profiles_file):
            result = resolve_profile_suggestion(
                issue_keys=["WEB-1"],
                hosts=["https://jira.meine-krankenkasse.de"]
            )
            assert result == "mkk"

    def test_resolve_via_project_key(self, tmp_path):
        profiles_file = tmp_path / "profiles.json"
        profiles_file.write_text(json.dumps(SAMPLE_PROFILES))

        with mock.patch('detect_jira_issues.PROFILES_FILE', profiles_file):
            result = resolve_profile_suggestion(
                issue_keys=["NRS-4167"],
                hosts=[]
            )
            assert result == "netresearch"

    def test_no_profiles_file(self, tmp_path):
        with mock.patch('detect_jira_issues.PROFILES_FILE', tmp_path / "nonexistent.json"):
            result = resolve_profile_suggestion(["WEB-1"], [])
            assert result is None

    def test_no_match(self, tmp_path):
        profiles_file = tmp_path / "profiles.json"
        profiles_file.write_text(json.dumps(SAMPLE_PROFILES))

        with mock.patch('detect_jira_issues.PROFILES_FILE', profiles_file):
            result = resolve_profile_suggestion(
                issue_keys=["UNKNOWN-999"],
                hosts=[]
            )
            assert result is None

    def test_host_takes_priority_over_key(self, tmp_path):
        """Host matching should resolve before project key matching."""
        profiles_file = tmp_path / "profiles.json"
        profiles_file.write_text(json.dumps(SAMPLE_PROFILES))

        with mock.patch('detect_jira_issues.PROFILES_FILE', profiles_file):
            # NRS belongs to netresearch, but host is mkk
            result = resolve_profile_suggestion(
                issue_keys=["NRS-1"],
                hosts=["https://jira.meine-krankenkasse.de"]
            )
            assert result == "mkk"

    def test_ambiguous_project_key_returns_none(self, tmp_path):
        """When same project key is in multiple profiles, return None (no suggestion)."""
        ambiguous = {
            "version": 1,
            "profiles": {
                "a": {"url": "https://a.com", "auth": "pat", "token": "x", "projects": ["WEB"]},
                "b": {"url": "https://b.com", "auth": "pat", "token": "y", "projects": ["WEB"]},
            }
        }
        profiles_file = tmp_path / "profiles.json"
        profiles_file.write_text(json.dumps(ambiguous))

        with mock.patch('detect_jira_issues.PROFILES_FILE', profiles_file):
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

        with mock.patch('detect_jira_issues.PROFILES_FILE', profiles_file):
            result = resolve_profile_suggestion(["WEB-1"], [])
            assert result is None

    def test_profiles_key_is_list_returns_none(self, tmp_path):
        """profiles.json where 'profiles' value is a list instead of dict."""
        profiles_file = tmp_path / "profiles.json"
        profiles_file.write_text(json.dumps({"profiles": ["not", "a", "dict"]}))

        with mock.patch('detect_jira_issues.PROFILES_FILE', profiles_file):
            result = resolve_profile_suggestion(["WEB-1"], [])
            assert result is None

    def test_profiles_key_is_string_returns_none(self, tmp_path):
        """profiles.json where 'profiles' value is a string."""
        profiles_file = tmp_path / "profiles.json"
        profiles_file.write_text(json.dumps({"profiles": "not a dict"}))

        with mock.patch('detect_jira_issues.PROFILES_FILE', profiles_file):
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
        with mock.patch('sys.stdin') as mock_stdin, \
             mock.patch('detect_jira_issues.PROFILES_FILE', fake_profiles):
            mock_stdin.read.return_value = input_data
            from detect_jira_issues import main
            main()
        return capsys.readouterr()

    def test_output_does_not_reference_mcp(self, tmp_path, capsys):
        """Hook output must not reference obsolete MCP architecture."""
        captured = self._run_hook("Check WEB-1381", tmp_path, capsys)
        assert 'mcp-atlassian' not in captured.out.lower()
        assert 'jira_get_issue' not in captured.out
        assert 'jira_search' not in captured.out

    def test_output_references_script_names(self, tmp_path, capsys):
        """Hook output should mention actual script names."""
        captured = self._run_hook("Check WEB-1381", tmp_path, capsys)
        assert 'jira-issue.py' in captured.out
        assert 'jira-search.py' in captured.out
