"""Tests for jira-setup.py — write_profile() and validate_credentials()."""

import importlib.util
import json
import stat
import sys
from pathlib import Path
from unittest import mock

# Add scripts to path for lib imports
_test_dir = Path(__file__).parent
_scripts_path = _test_dir.parent / "skills" / "jira-communication" / "scripts"
sys.path.insert(0, str(_scripts_path))

from lib.client import JIRA_TIMEOUT

# Import jira-setup.py (hyphenated filename requires importlib)
_core_path = _scripts_path / "core"
_spec = importlib.util.spec_from_file_location(
    "jira_setup", _core_path / "jira-setup.py"
)
jira_setup = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(jira_setup)


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: Corrupt profiles.json handling in write_profile()
# ═══════════════════════════════════════════════════════════════════════════════

class TestWriteProfileCorruptJson:
    """write_profile() must create backup when profiles.json is corrupted."""

    def test_corrupt_json_creates_backup(self, tmp_path):
        """Corrupt profiles.json should be renamed to .json.bak."""
        profiles_dir = tmp_path / ".jira"
        profiles_dir.mkdir()
        profiles_file = profiles_dir / "profiles.json"
        corrupt_content = "not valid json {{{"
        profiles_file.write_text(corrupt_content)

        profile_data = {
            'url': 'https://jira.example.com',
            'auth': 'pat',
            'token': 'new-token',
        }

        with mock.patch.object(jira_setup, 'PROFILES_FILE', profiles_file):
            jira_setup.write_profile('rescue', profile_data)

        backup_file = profiles_dir / "profiles.json.bak"
        assert backup_file.exists()
        assert backup_file.read_text() == corrupt_content

    def test_corrupt_json_writes_fresh_profile(self, tmp_path):
        """After backup, a fresh profiles.json with the new profile should be written."""
        profiles_dir = tmp_path / ".jira"
        profiles_dir.mkdir()
        profiles_file = profiles_dir / "profiles.json"
        profiles_file.write_text("{broken json")

        profile_data = {
            'url': 'https://jira.example.com',
            'auth': 'pat',
            'token': 'new-token',
        }

        with mock.patch.object(jira_setup, 'PROFILES_FILE', profiles_file):
            jira_setup.write_profile('rescue', profile_data)

        assert profiles_file.exists()
        data = json.loads(profiles_file.read_text())
        assert data['version'] == 1
        assert 'rescue' in data['profiles']
        assert data['profiles']['rescue']['url'] == 'https://jira.example.com'
        assert data['profiles']['rescue']['token'] == 'new-token'
        assert data['default'] == 'rescue'

    def test_corrupt_json_new_file_has_restricted_permissions(self, tmp_path):
        """The newly written profiles.json must have 0600 permissions."""
        profiles_dir = tmp_path / ".jira"
        profiles_dir.mkdir()
        profiles_file = profiles_dir / "profiles.json"
        profiles_file.write_text("{invalid}")

        profile_data = {
            'url': 'https://jira.example.com',
            'auth': 'pat',
            'token': 'test',
        }

        with mock.patch.object(jira_setup, 'PROFILES_FILE', profiles_file):
            jira_setup.write_profile('test', profile_data)

        file_mode = stat.S_IMODE(profiles_file.stat().st_mode)
        assert file_mode == 0o600


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: write_profile() handles valid JSON with invalid structure
# ═══════════════════════════════════════════════════════════════════════════════

class TestWriteProfileInvalidStructure:
    """write_profile() must backup and start fresh when JSON is valid but structure
    is wrong (e.g., a list instead of dict, or missing 'profiles' key)."""

    def test_json_list_creates_backup_and_fresh_profile(self, tmp_path):
        """profiles.json containing a JSON list should be backed up."""
        profiles_dir = tmp_path / ".jira"
        profiles_dir.mkdir()
        profiles_file = profiles_dir / "profiles.json"
        list_content = json.dumps(["not", "a", "dict"])
        profiles_file.write_text(list_content)

        profile_data = {
            'url': 'https://jira.example.com',
            'auth': 'pat',
            'token': 'new-token',
        }

        with mock.patch.object(jira_setup, 'PROFILES_FILE', profiles_file):
            jira_setup.write_profile('rescue', profile_data)

        backup_file = profiles_dir / "profiles.json.bak"
        assert backup_file.exists()
        assert backup_file.read_text() == list_content
        data = json.loads(profiles_file.read_text())
        assert 'rescue' in data['profiles']

    def test_json_missing_profiles_key_creates_backup(self, tmp_path):
        """profiles.json without 'profiles' key should be backed up."""
        profiles_dir = tmp_path / ".jira"
        profiles_dir.mkdir()
        profiles_file = profiles_dir / "profiles.json"
        bad_content = json.dumps({"version": 1, "other": "stuff"})
        profiles_file.write_text(bad_content)

        profile_data = {
            'url': 'https://jira.example.com',
            'auth': 'pat',
            'token': 'new-token',
        }

        with mock.patch.object(jira_setup, 'PROFILES_FILE', profiles_file):
            jira_setup.write_profile('rescue', profile_data)

        backup_file = profiles_dir / "profiles.json.bak"
        assert backup_file.exists()
        data = json.loads(profiles_file.read_text())
        assert 'rescue' in data['profiles']

    def test_profiles_key_not_dict_creates_backup(self, tmp_path):
        """profiles.json where 'profiles' is a string should be backed up."""
        profiles_dir = tmp_path / ".jira"
        profiles_dir.mkdir()
        profiles_file = profiles_dir / "profiles.json"
        bad_content = json.dumps({"version": 1, "profiles": "not a dict"})
        profiles_file.write_text(bad_content)

        profile_data = {
            'url': 'https://jira.example.com',
            'auth': 'pat',
            'token': 'new-token',
        }

        with mock.patch.object(jira_setup, 'PROFILES_FILE', profiles_file):
            jira_setup.write_profile('rescue', profile_data)

        backup_file = profiles_dir / "profiles.json.bak"
        assert backup_file.exists()
        data = json.loads(profiles_file.read_text())
        assert 'rescue' in data['profiles']


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: write_profile() handles existing .json.bak file
# ═══════════════════════════════════════════════════════════════════════════════

class TestWriteProfileExistingBackup:
    """write_profile() must replace existing .json.bak when creating a new backup."""

    def test_existing_bak_is_replaced(self, tmp_path):
        """When .json.bak already exists, it should be replaced by the new backup."""
        profiles_dir = tmp_path / ".jira"
        profiles_dir.mkdir()
        profiles_file = profiles_dir / "profiles.json"
        corrupt_content = "not valid json {{{"
        profiles_file.write_text(corrupt_content)

        backup_file = profiles_dir / "profiles.json.bak"
        backup_file.write_text("old backup content")

        profile_data = {
            'url': 'https://jira.example.com',
            'auth': 'pat',
            'token': 'new-token',
        }

        with mock.patch.object(jira_setup, 'PROFILES_FILE', profiles_file):
            jira_setup.write_profile('rescue', profile_data)

        assert backup_file.exists()
        assert backup_file.read_text() == corrupt_content
        data = json.loads(profiles_file.read_text())
        assert 'rescue' in data['profiles']


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: validate_url() treats reachable status codes as success
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidateUrlStatusCodes:
    """validate_url() must treat 405 as reachable (server rejects HEAD but is up)."""

    def test_405_falls_back_to_get_and_succeeds(self):
        """On HEAD 405, validate_url falls back to GET and reports reachable."""
        head_resp = mock.Mock(status_code=405)
        get_resp = mock.Mock(status_code=200)
        with mock.patch.object(jira_setup.requests, 'head', return_value=head_resp), \
             mock.patch.object(jira_setup.requests, 'get', return_value=get_resp):
            ok, msg = jira_setup.validate_url('https://jira.example.com')
        assert ok is True
        assert 'reachable' in msg.lower()

    def test_405_falls_back_to_get_with_auth_required(self):
        """On HEAD 405 + GET 401, server is reachable but needs auth."""
        head_resp = mock.Mock(status_code=405)
        get_resp = mock.Mock(status_code=401)
        with mock.patch.object(jira_setup.requests, 'head', return_value=head_resp), \
             mock.patch.object(jira_setup.requests, 'get', return_value=get_resp):
            ok, msg = jira_setup.validate_url('https://jira.example.com')
        assert ok is True
        assert 'authentication' in msg.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: validate_credentials() passes timeout (F6 regression)
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidateCredentialsTimeout:
    """validate_credentials() must pass JIRA_TIMEOUT to the Jira constructor."""

    def test_cloud_client_uses_timeout(self):
        """Cloud auth Jira() call must include timeout=JIRA_TIMEOUT."""
        with mock.patch.object(jira_setup, 'Jira') as MockJira:
            MockJira.return_value.myself.return_value = {'displayName': 'Test'}
            jira_setup.validate_credentials(
                'https://x.atlassian.net', 'cloud',
                username='u', api_token='t'
            )
            assert MockJira.call_args[1].get('timeout') == JIRA_TIMEOUT

    def test_server_client_uses_timeout(self):
        """Server/DC auth Jira() call must include timeout=JIRA_TIMEOUT."""
        with mock.patch.object(jira_setup, 'Jira') as MockJira:
            MockJira.return_value.myself.return_value = {'displayName': 'Test'}
            jira_setup.validate_credentials(
                'https://jira.example.com', 'server',
                personal_token='pat-123'
            )
            assert MockJira.call_args[1].get('timeout') == JIRA_TIMEOUT


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: validate_credentials() handles string response from myself()
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidateCredentialsMyselfString:
    """Some Jira Server/DC instances return a string from myself() instead of dict."""

    def test_myself_returns_string(self):
        """validate_credentials() must handle string response from myself()."""
        with mock.patch.object(jira_setup, 'Jira') as MockJira:
            MockJira.return_value.myself.return_value = 'jdoe'
            ok, msg = jira_setup.validate_credentials(
                'https://jira.example.com', 'server',
                personal_token='pat-123'
            )
        assert ok is True
        assert 'jdoe' in msg

    def test_myself_returns_html_2fa_page(self):
        """2FA/Secure Login returns HTML instead of JSON — must be detected as auth failure."""
        html = '<!DOCTYPE html><html><head><title>Secure Login</title></head><body>PIN required</body></html>'
        with mock.patch.object(jira_setup, 'Jira') as MockJira:
            MockJira.return_value.myself.return_value = html
            ok, msg = jira_setup.validate_credentials(
                'https://jira.example.com', 'server',
                personal_token='pat-123'
            )
        assert ok is False
        assert '2fa' in msg.lower() or 'secure login' in msg.lower() or 'two-factor' in msg.lower()

    def test_myself_returns_dict_with_display_name(self):
        """Standard dict response with displayName works as before."""
        with mock.patch.object(jira_setup, 'Jira') as MockJira:
            MockJira.return_value.myself.return_value = {
                'displayName': 'Rico Sonntag',
                'emailAddress': 'rico@example.com'
            }
            ok, msg = jira_setup.validate_credentials(
                'https://jira.example.com', 'server',
                personal_token='pat-123'
            )
        assert ok is True
        assert 'Rico Sonntag' in msg
        assert 'rico@example.com' in msg


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: validate_credentials() sanitizes error messages (F3 regression)
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidateCredentialsSanitization:
    """validate_credentials() must not leak credentials in error messages."""

    def test_token_in_exception_is_redacted(self):
        """If Jira raises with token value, it must be redacted in the returned message."""
        with mock.patch.object(jira_setup, 'Jira') as MockJira:
            MockJira.side_effect = Exception("Failed: token=superSecret123 is invalid")
            ok, msg = jira_setup.validate_credentials(
                'https://jira.example.com', 'server',
                personal_token='superSecret123'
            )
            assert not ok
            assert 'superSecret123' not in msg
