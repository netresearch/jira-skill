"""Tests for multi-profile configuration support in config.py."""

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

# Add lib to path for imports
_test_dir = Path(__file__).parent
_lib_path = _test_dir.parent / "skills" / "jira-communication" / "scripts"
sys.path.insert(0, str(_lib_path))

from lib.config import (
    is_cloud_url,
    load_config,
    load_env,
    load_profiles,
    profile_to_config,
    resolve_profile,
    validate_config,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

SAMPLE_PROFILES = {
    "version": 1,
    "default": "netresearch",
    "profiles": {
        "netresearch": {
            "url": "https://jira.netresearch.de",
            "auth": "pat",
            "token": "NzA0NjY5...",
            "projects": ["NRS", "OPSMKK", "MKK"]
        },
        "mkk": {
            "url": "https://jira.meine-krankenkasse.de",
            "auth": "pat",
            "token": "MTExNTAw...",
            "projects": ["WEB", "INFRA"]
        },
        "cloud": {
            "url": "https://company.atlassian.net",
            "auth": "cloud",
            "username": "user@example.com",
            "api_token": "cloud-token-123",
            "projects": ["CLOUD"]
        }
    }
}


@pytest.fixture
def profiles_dir(tmp_path):
    """Create a temporary ~/.jira directory with profiles.json."""
    jira_dir = tmp_path / ".jira"
    jira_dir.mkdir()
    profiles_file = jira_dir / "profiles.json"
    profiles_file.write_text(json.dumps(SAMPLE_PROFILES, indent=2))
    profiles_file.chmod(0o600)
    return jira_dir


@pytest.fixture
def env_file(tmp_path):
    """Create a temporary .env.jira file."""
    env = tmp_path / ".env.jira"
    env.write_text(
        "JIRA_URL=https://jira.legacy.example.com\n"
        "JIRA_PERSONAL_TOKEN=legacy-token-abc\n"
    )
    return env


@pytest.fixture
def project_dir(tmp_path):
    """Create a project directory with .jira-profile."""
    proj = tmp_path / "project"
    proj.mkdir()
    (proj / ".jira-profile").write_text("mkk\n")
    return proj


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: load_profiles()
# ═══════════════════════════════════════════════════════════════════════════════

class TestLoadProfiles:
    def test_load_valid_profiles(self, profiles_dir):
        with mock.patch('lib.config.PROFILES_FILE', profiles_dir / "profiles.json"):
            data = load_profiles()
            assert data['version'] == 1
            assert data['default'] == 'netresearch'
            assert 'netresearch' in data['profiles']
            assert 'mkk' in data['profiles']
            assert 'cloud' in data['profiles']

    def test_load_nonexistent_raises_file_not_found(self, tmp_path):
        with mock.patch('lib.config.PROFILES_FILE', tmp_path / "nonexistent.json"):
            with pytest.raises(FileNotFoundError):
                load_profiles()

    def test_load_invalid_json_raises_value_error(self, tmp_path):
        bad_file = tmp_path / "profiles.json"
        bad_file.write_text("not valid json {{{")
        with mock.patch('lib.config.PROFILES_FILE', bad_file):
            with pytest.raises(ValueError, match="Invalid JSON"):
                load_profiles()

    def test_load_missing_profiles_key_raises_value_error(self, tmp_path):
        bad_file = tmp_path / "profiles.json"
        bad_file.write_text(json.dumps({"version": 1}))
        with mock.patch('lib.config.PROFILES_FILE', bad_file):
            with pytest.raises(ValueError, match="missing 'profiles' key"):
                load_profiles()

    def test_load_empty_profiles_raises_value_error(self, tmp_path):
        bad_file = tmp_path / "profiles.json"
        bad_file.write_text(json.dumps({"version": 1, "profiles": {}}))
        with mock.patch('lib.config.PROFILES_FILE', bad_file):
            with pytest.raises(ValueError, match="No profiles defined"):
                load_profiles()


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: resolve_profile()
# ═══════════════════════════════════════════════════════════════════════════════

class TestResolveProfile:
    def test_explicit_profile_name(self, profiles_dir):
        with mock.patch('lib.config.PROFILES_FILE', profiles_dir / "profiles.json"):
            result = resolve_profile(profile='mkk')
            assert result['name'] == 'mkk'
            assert result['url'] == 'https://jira.meine-krankenkasse.de'
            assert result['auth'] == 'pat'

    def test_explicit_profile_not_found(self, profiles_dir):
        with mock.patch('lib.config.PROFILES_FILE', profiles_dir / "profiles.json"):
            with pytest.raises(ValueError, match="Profile 'nonexistent' not found"):
                resolve_profile(profile='nonexistent')

    def test_url_host_matching(self, profiles_dir):
        with mock.patch('lib.config.PROFILES_FILE', profiles_dir / "profiles.json"):
            result = resolve_profile(url='https://jira.meine-krankenkasse.de/browse/WEB-1381')
            assert result['name'] == 'mkk'

    def test_url_host_matching_cloud(self, profiles_dir):
        with mock.patch('lib.config.PROFILES_FILE', profiles_dir / "profiles.json"):
            result = resolve_profile(url='https://company.atlassian.net/browse/CLOUD-42')
            assert result['name'] == 'cloud'

    def test_issue_key_project_matching(self, profiles_dir):
        with mock.patch('lib.config.PROFILES_FILE', profiles_dir / "profiles.json"):
            result = resolve_profile(issue_key='WEB-1381')
            assert result['name'] == 'mkk'

    def test_issue_key_project_matching_nrs(self, profiles_dir):
        with mock.patch('lib.config.PROFILES_FILE', profiles_dir / "profiles.json"):
            result = resolve_profile(issue_key='NRS-4167')
            assert result['name'] == 'netresearch'

    def test_issue_key_ambiguous_raises_error(self, tmp_path):
        """When the same project prefix exists in multiple profiles."""
        jira_dir = tmp_path / ".jira"
        jira_dir.mkdir()
        ambiguous = {
            "version": 1,
            "profiles": {
                "a": {"url": "https://a.example.com", "auth": "pat", "token": "x", "projects": ["WEB"]},
                "b": {"url": "https://b.example.com", "auth": "pat", "token": "y", "projects": ["WEB"]},
            }
        }
        profiles_file = jira_dir / "profiles.json"
        profiles_file.write_text(json.dumps(ambiguous))

        with mock.patch('lib.config.PROFILES_FILE', profiles_file):
            with pytest.raises(ValueError, match="WEB found in profiles"):
                resolve_profile(issue_key='WEB-100')

    def test_directory_context_jira_profile(self, profiles_dir, project_dir):
        with mock.patch('lib.config.PROFILES_FILE', profiles_dir / "profiles.json"):
            result = resolve_profile(project_dir=str(project_dir))
            assert result['name'] == 'mkk'

    def test_default_profile_fallback(self, profiles_dir):
        with mock.patch('lib.config.PROFILES_FILE', profiles_dir / "profiles.json"):
            result = resolve_profile()
            assert result['name'] == 'netresearch'  # default

    def test_no_default_raises_error(self, tmp_path):
        jira_dir = tmp_path / ".jira"
        jira_dir.mkdir()
        no_default = {
            "version": 1,
            "profiles": {
                "a": {"url": "https://a.example.com", "auth": "pat", "token": "x"},
            }
        }
        profiles_file = jira_dir / "profiles.json"
        profiles_file.write_text(json.dumps(no_default))

        with mock.patch('lib.config.PROFILES_FILE', profiles_file):
            with pytest.raises(ValueError, match="Could not resolve profile"):
                resolve_profile(issue_key='UNKNOWN-999')

    def test_priority_explicit_over_url(self, profiles_dir):
        """Explicit --profile takes precedence over URL matching."""
        with mock.patch('lib.config.PROFILES_FILE', profiles_dir / "profiles.json"):
            result = resolve_profile(
                profile='netresearch',
                url='https://jira.meine-krankenkasse.de/browse/WEB-1'
            )
            assert result['name'] == 'netresearch'

    def test_priority_url_over_issue_key(self, profiles_dir):
        """URL matching takes precedence over issue key matching."""
        with mock.patch('lib.config.PROFILES_FILE', profiles_dir / "profiles.json"):
            # NRS is in netresearch, but URL points to mkk
            result = resolve_profile(
                url='https://jira.meine-krankenkasse.de/browse/NRS-1',
                issue_key='NRS-1'
            )
            assert result['name'] == 'mkk'


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: profile_to_config()
# ═══════════════════════════════════════════════════════════════════════════════

class TestProfileToConfig:
    def test_pat_profile(self):
        prof = {
            "url": "https://jira.example.com",
            "auth": "pat",
            "token": "my-token-123"
        }
        config = profile_to_config(prof)
        assert config['JIRA_URL'] == 'https://jira.example.com'
        assert config['JIRA_PERSONAL_TOKEN'] == 'my-token-123'
        assert 'JIRA_USERNAME' not in config

    def test_cloud_profile(self):
        prof = {
            "url": "https://company.atlassian.net",
            "auth": "cloud",
            "username": "user@example.com",
            "api_token": "cloud-token"
        }
        config = profile_to_config(prof)
        assert config['JIRA_URL'] == 'https://company.atlassian.net'
        assert config['JIRA_USERNAME'] == 'user@example.com'
        assert config['JIRA_API_TOKEN'] == 'cloud-token'
        assert 'JIRA_PERSONAL_TOKEN' not in config

    def test_missing_url_raises_value_error(self):
        """Profile without 'url' should raise ValueError."""
        prof = {"auth": "pat", "token": "my-token-123"}
        with pytest.raises(ValueError, match="missing required 'url' field"):
            profile_to_config(prof)

    def test_empty_url_raises_value_error(self):
        """Profile with empty 'url' should raise ValueError."""
        prof = {"url": "", "auth": "pat", "token": "my-token-123"}
        with pytest.raises(ValueError, match="missing required 'url' field"):
            profile_to_config(prof)

    def test_missing_token_raises_value_error(self):
        """PAT profile without 'token' should raise ValueError."""
        prof = {"url": "https://jira.example.com", "auth": "pat"}
        with pytest.raises(ValueError, match="missing required 'token' field"):
            profile_to_config(prof)

    def test_empty_token_raises_value_error(self):
        """PAT profile with empty 'token' should raise ValueError."""
        prof = {"url": "https://jira.example.com", "auth": "pat", "token": ""}
        with pytest.raises(ValueError, match="missing required 'token' field"):
            profile_to_config(prof)

    def test_missing_cloud_credentials_raises_value_error(self):
        """Cloud profile without 'username'/'api_token' should raise ValueError."""
        prof = {"url": "https://company.atlassian.net", "auth": "cloud"}
        with pytest.raises(ValueError, match="missing required 'username' and/or 'api_token'"):
            profile_to_config(prof)

    def test_partial_cloud_credentials_raises_value_error(self):
        """Cloud profile with only 'username' but no 'api_token' should raise ValueError."""
        prof = {"url": "https://company.atlassian.net", "auth": "cloud", "username": "user@example.com"}
        with pytest.raises(ValueError, match="missing required 'username' and/or 'api_token'"):
            profile_to_config(prof)

    def test_config_validates(self):
        """Config produced by profile_to_config should pass validate_config."""
        prof = {
            "url": "https://jira.example.com",
            "auth": "pat",
            "token": "my-token-123"
        }
        config = profile_to_config(prof)
        errors = validate_config(config)
        assert errors == []


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: is_cloud_url()
# ═══════════════════════════════════════════════════════════════════════════════

class TestIsCloudUrl:
    def test_atlassian_cloud_url(self):
        assert is_cloud_url('https://company.atlassian.net') is True

    def test_atlassian_cloud_with_path(self):
        assert is_cloud_url('https://company.atlassian.net/browse/PROJ-1') is True

    def test_bare_atlassian_net(self):
        assert is_cloud_url('https://atlassian.net') is True

    def test_server_url(self):
        assert is_cloud_url('https://jira.example.com') is False

    def test_malicious_subdomain(self):
        """Must not match domains like attacker-atlassian.net.evil.com."""
        assert is_cloud_url('https://attacker-atlassian.net.evil.com') is False

    def test_contains_but_not_ends_with(self):
        """Must not match domains that merely contain 'atlassian.net'."""
        assert is_cloud_url('https://fake-atlassian.net.attacker.com') is False


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: load_config()
# ═══════════════════════════════════════════════════════════════════════════════

class TestLoadConfig:
    def test_env_file_takes_precedence(self, profiles_dir, env_file):
        """--env-file always wins over profiles."""
        with mock.patch('lib.config.PROFILES_FILE', profiles_dir / "profiles.json"):
            config = load_config(env_file=str(env_file))
            assert config['JIRA_URL'] == 'https://jira.legacy.example.com'
            assert config['JIRA_PERSONAL_TOKEN'] == 'legacy-token-abc'

    def test_profile_resolution_when_profiles_exist(self, profiles_dir):
        with mock.patch('lib.config.PROFILES_FILE', profiles_dir / "profiles.json"):
            config = load_config(profile='mkk')
            assert config['JIRA_URL'] == 'https://jira.meine-krankenkasse.de'

    def test_issue_key_resolution(self, profiles_dir):
        with mock.patch('lib.config.PROFILES_FILE', profiles_dir / "profiles.json"):
            config = load_config(issue_key='WEB-1381')
            assert config['JIRA_URL'] == 'https://jira.meine-krankenkasse.de'

    def test_url_resolution(self, profiles_dir):
        with mock.patch('lib.config.PROFILES_FILE', profiles_dir / "profiles.json"):
            config = load_config(url='https://company.atlassian.net/browse/CLOUD-1')
            assert config['JIRA_URL'] == 'https://company.atlassian.net'
            assert config['JIRA_USERNAME'] == 'user@example.com'

    def test_legacy_fallback_no_profiles(self, tmp_path, env_file):
        """Without profiles.json, falls back to ~/.env.jira."""
        with mock.patch('lib.config.PROFILES_FILE', tmp_path / "nonexistent.json"):
            with mock.patch('lib.config.DEFAULT_ENV_FILE', env_file):
                config = load_config()
                assert config['JIRA_URL'] == 'https://jira.legacy.example.com'

    def test_explicit_profile_without_profiles_file_raises(self, tmp_path):
        with mock.patch('lib.config.PROFILES_FILE', tmp_path / "nonexistent.json"):
            with pytest.raises(FileNotFoundError, match="does not exist"):
                load_config(profile='test')


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: resolve_profile() warns about unknown .jira-profile reference
# ═══════════════════════════════════════════════════════════════════════════════

class TestResolveProfileJiraProfileWarning:
    """resolve_profile() should warn when .jira-profile references an unknown profile."""

    def test_unknown_jira_profile_warns(self, profiles_dir, capsys):
        """A .jira-profile with a name not in profiles.json should emit a warning."""
        proj = profiles_dir.parent / "myproject"
        proj.mkdir()
        (proj / ".jira-profile").write_text("nonexistent\n")

        with mock.patch('lib.config.PROFILES_FILE', profiles_dir / "profiles.json"):
            result = resolve_profile(project_dir=str(proj))

        # Should fall through to default profile
        assert result['name'] == 'netresearch'
        # Should warn about the unknown profile name
        captured = capsys.readouterr()
        assert 'nonexistent' in captured.err

    def test_valid_jira_profile_no_warning(self, profiles_dir, capsys):
        """A .jira-profile with a valid name should not emit any warning."""
        proj = profiles_dir.parent / "myproject"
        proj.mkdir()
        (proj / ".jira-profile").write_text("mkk\n")

        with mock.patch('lib.config.PROFILES_FILE', profiles_dir / "profiles.json"):
            result = resolve_profile(project_dir=str(proj))

        assert result['name'] == 'mkk'
        captured = capsys.readouterr()
        assert captured.err == ''


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: load_env() handles 'export' prefix (F12)
# ═══════════════════════════════════════════════════════════════════════════════

class TestLoadEnvExportPrefix:
    """load_env() must strip 'export' prefix from shell-style env files."""

    def test_export_prefix_stripped(self, tmp_path):
        """Lines like 'export JIRA_URL=...' must parse correctly."""
        env_file = tmp_path / ".env.jira"
        env_file.write_text(
            "export JIRA_URL=https://jira.example.com\n"
            "export JIRA_PERSONAL_TOKEN=my-token\n"
        )
        config = load_env(str(env_file))
        assert config['JIRA_URL'] == 'https://jira.example.com'
        assert config['JIRA_PERSONAL_TOKEN'] == 'my-token'

    def test_mixed_export_and_plain(self, tmp_path):
        """Mix of 'export' and plain lines should both parse correctly."""
        env_file = tmp_path / ".env.jira"
        env_file.write_text(
            "JIRA_URL=https://jira.example.com\n"
            "export JIRA_PERSONAL_TOKEN=my-token\n"
        )
        config = load_env(str(env_file))
        assert config['JIRA_URL'] == 'https://jira.example.com'
        assert config['JIRA_PERSONAL_TOKEN'] == 'my-token'
