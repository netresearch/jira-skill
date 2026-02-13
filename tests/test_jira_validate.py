"""Tests for jira-validate.py — validate_all_profiles() function."""

import importlib.util
import json
import sys
from pathlib import Path
from unittest import mock

# Add scripts to path for lib imports
_test_dir = Path(__file__).parent
_scripts_path = _test_dir.parent / "skills" / "jira-communication" / "scripts"
sys.path.insert(0, str(_scripts_path))

# Import jira-validate.py (hyphenated filename requires importlib)
_core_path = _scripts_path / "core"
_spec = importlib.util.spec_from_file_location(
    "jira_validate", _core_path / "jira-validate.py"
)
jira_validate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(jira_validate)


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

SINGLE_PROFILE = {
    "version": 1,
    "default": "test",
    "profiles": {
        "test": {
            "url": "https://jira.example.com",
            "auth": "pat",
            "token": "test-token",
        }
    }
}


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: HTTP status threshold in validate_all_profiles()
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidateAllProfilesHttpThreshold:
    """HTTP 4xx responses must be reported as errors, not OK."""

    def _run_with_status(self, tmp_path, status_code, capsys):
        """Run validate_all_profiles with a mocked HTTP status code."""
        profiles_file = tmp_path / "profiles.json"
        profiles_file.write_text(json.dumps(SINGLE_PROFILE))

        mock_response = mock.Mock()
        mock_response.status_code = status_code

        with mock.patch('lib.config.PROFILES_FILE', profiles_file), \
             mock.patch('requests.head', return_value=mock_response):
            exit_code = jira_validate.validate_all_profiles(output_json=True)

        captured = capsys.readouterr()
        results = json.loads(captured.out)
        return exit_code, results[0]['Status']

    def test_http_200_is_ok(self, tmp_path, capsys):
        code, status = self._run_with_status(tmp_path, 200, capsys)
        assert status == 'OK'
        assert code == 0

    def test_http_301_is_ok(self, tmp_path, capsys):
        code, status = self._run_with_status(tmp_path, 301, capsys)
        assert status == 'OK'
        assert code == 0

    def test_http_399_is_ok(self, tmp_path, capsys):
        """Boundary: 399 is the last OK status."""
        code, status = self._run_with_status(tmp_path, 399, capsys)
        assert status == 'OK'
        assert code == 0

    def test_http_400_is_error(self, tmp_path, capsys):
        """Boundary: 400 is the first error status."""
        code, status = self._run_with_status(tmp_path, 400, capsys)
        assert status == 'HTTP 400'
        assert code != 0

    def test_http_401_is_ok(self, tmp_path, capsys):
        """401 means reachable but unauthenticated — counts as OK."""
        code, status = self._run_with_status(tmp_path, 401, capsys)
        assert status == 'OK'

    def test_http_403_is_ok(self, tmp_path, capsys):
        """403 means reachable but forbidden — counts as OK."""
        code, status = self._run_with_status(tmp_path, 403, capsys)
        assert status == 'OK'

    def test_http_500_is_error(self, tmp_path, capsys):
        code, status = self._run_with_status(tmp_path, 500, capsys)
        assert status == 'HTTP 500'
        assert code != 0


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: Profile with missing URL in validate_all_profiles()
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidateAllProfilesMissingUrl:
    """validate_all_profiles() must not crash when a profile is missing 'url'."""

    def test_profile_missing_url_shows_config_error(self, tmp_path, capsys):
        """A profile without 'url' should show CONFIG ERROR, not crash."""
        profiles_data = {
            "version": 1,
            "default": "broken",
            "profiles": {
                "broken": {
                    "auth": "pat",
                    "token": "broken-token",
                }
            }
        }
        profiles_file = tmp_path / "profiles.json"
        profiles_file.write_text(json.dumps(profiles_data))

        with mock.patch('lib.config.PROFILES_FILE', profiles_file):
            exit_code = jira_validate.validate_all_profiles(output_json=True)

        captured = capsys.readouterr()
        results = json.loads(captured.out)

        assert len(results) == 1
        assert results[0]['Profile'] == 'broken'
        assert results[0]['Status'] == 'CONFIG ERROR'
        assert results[0]['URL'] == 'N/A'
        assert exit_code != 0

    def test_mixed_valid_and_broken_profiles(self, tmp_path, capsys):
        """Loop must continue past broken profiles and still check all remaining ones."""
        profiles_data = {
            "version": 1,
            "default": "good",
            "profiles": {
                "good": {
                    "url": "https://jira.example.com",
                    "auth": "pat",
                    "token": "test-token",
                },
                "broken": {
                    "auth": "pat",
                    "token": "broken-token",
                }
            }
        }
        profiles_file = tmp_path / "profiles.json"
        profiles_file.write_text(json.dumps(profiles_data))

        mock_response = mock.Mock()
        mock_response.status_code = 200

        with mock.patch('lib.config.PROFILES_FILE', profiles_file), \
             mock.patch('requests.head', return_value=mock_response):
            exit_code = jira_validate.validate_all_profiles(output_json=True)

        captured = capsys.readouterr()
        results = json.loads(captured.out)

        # Both profiles must appear in results (loop didn't crash on broken profile)
        assert len(results) == 2
        result_map = {r['Profile']: r for r in results}
        assert result_map['good']['Status'] == 'OK'
        assert result_map['broken']['Status'] == 'CONFIG ERROR'
        assert exit_code != 0


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: check_environment() handles ValueError from profile_to_config()
# ═══════════════════════════════════════════════════════════════════════════════

class TestCheckEnvironmentValueError:
    """check_environment() must catch ValueError from stricter profile_to_config()."""

    def test_profile_missing_token_returns_none(self, tmp_path):
        """A profile with missing 'token' must return None, not raise ValueError."""
        profiles_data = {
            "version": 1,
            "default": "broken",
            "profiles": {
                "broken": {
                    "url": "https://jira.example.com",
                    "auth": "pat",
                    # token intentionally missing
                }
            }
        }
        profiles_file = tmp_path / "profiles.json"
        profiles_file.write_text(json.dumps(profiles_data))

        with mock.patch('lib.config.PROFILES_FILE', profiles_file):
            result = jira_validate.check_environment(env_file=None, profile='broken')

        assert result is None

    def test_cloud_profile_missing_api_token_returns_none(self, tmp_path):
        """A cloud profile with missing credentials must return None, not raise."""
        profiles_data = {
            "version": 1,
            "default": "broken",
            "profiles": {
                "broken": {
                    "url": "https://company.atlassian.net",
                    "auth": "cloud",
                    "username": "user@example.com",
                    # api_token intentionally missing
                }
            }
        }
        profiles_file = tmp_path / "profiles.json"
        profiles_file.write_text(json.dumps(profiles_data))

        with mock.patch('lib.config.PROFILES_FILE', profiles_file):
            result = jira_validate.check_environment(env_file=None, profile='broken')

        assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: Exit code semantics in validate_all_profiles()
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidateAllProfilesExitCodes:
    """validate_all_profiles() must return EXIT_CONFIG_ERROR (2) for pure config
    errors and EXIT_CONNECTION_ERROR (3) for connectivity errors."""

    def test_pure_config_error_returns_exit_code_2(self, tmp_path, capsys):
        """All profiles have config errors → exit code 2 (not 3)."""
        profiles_data = {
            "version": 1,
            "profiles": {
                "broken": {
                    "auth": "pat",
                    # missing url and token
                }
            }
        }
        profiles_file = tmp_path / "profiles.json"
        profiles_file.write_text(json.dumps(profiles_data))

        with mock.patch('lib.config.PROFILES_FILE', profiles_file):
            exit_code = jira_validate.validate_all_profiles(output_json=True)

        assert exit_code == jira_validate.EXIT_CONFIG_ERROR

    def test_connectivity_error_returns_exit_code_3(self, tmp_path, capsys):
        """Unreachable server → exit code 3."""
        profiles_file = tmp_path / "profiles.json"
        profiles_file.write_text(json.dumps(SINGLE_PROFILE))

        with mock.patch('lib.config.PROFILES_FILE', profiles_file), \
             mock.patch('requests.head', side_effect=Exception("timeout")):
            exit_code = jira_validate.validate_all_profiles(output_json=True)

        assert exit_code == jira_validate.EXIT_CONNECTION_ERROR

    def test_mixed_config_and_connectivity_returns_exit_code_3(self, tmp_path, capsys):
        """Config error + connectivity error → exit code 3 (connectivity takes precedence)."""
        profiles_data = {
            "version": 1,
            "profiles": {
                "good_but_unreachable": {
                    "url": "https://jira.example.com",
                    "auth": "pat",
                    "token": "test-token",
                },
                "broken_config": {
                    "auth": "pat",
                    # missing url and token
                }
            }
        }
        profiles_file = tmp_path / "profiles.json"
        profiles_file.write_text(json.dumps(profiles_data))

        with mock.patch('lib.config.PROFILES_FILE', profiles_file), \
             mock.patch('requests.head', side_effect=Exception("timeout")):
            exit_code = jira_validate.validate_all_profiles(output_json=True)

        assert exit_code == jira_validate.EXIT_CONNECTION_ERROR


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: check_environment() verbose output reflects actual config source
# ═══════════════════════════════════════════════════════════════════════════════

class TestCheckEnvironmentVerboseOutput:
    """check_environment() verbose output must show profile info when profiles.json
    is used, not misleading 'Environment file: ~/.env.jira'."""

    def test_verbose_shows_default_profile_when_profiles_exist(self, tmp_path, capsys):
        """When no --env-file and no --profile but profiles.json exists,
        verbose output should show the resolved default profile name."""
        profiles_data = {
            "version": 1,
            "default": "myprofile",
            "profiles": {
                "myprofile": {
                    "url": "https://jira.example.com",
                    "auth": "pat",
                    "token": "test-token",
                }
            }
        }
        profiles_file = tmp_path / "profiles.json"
        profiles_file.write_text(json.dumps(profiles_data))

        with mock.patch('lib.config.PROFILES_FILE', profiles_file):
            config = jira_validate.check_environment(
                env_file=None, profile=None, verbose=True
            )

        assert config is not None
        captured = capsys.readouterr()
        # Verbose output should mention the resolved profile name
        assert 'myprofile' in captured.out
        # Should NOT show misleading "Environment file" message
        assert 'Environment file' not in captured.out

    def test_verbose_shows_env_file_when_no_profiles(self, tmp_path, capsys):
        """When profiles.json does not exist and no args, show env file path."""
        # Create a minimal .env.jira
        env_file = tmp_path / ".env.jira"
        env_file.write_text("JIRA_URL=https://jira.example.com\nJIRA_PERSONAL_TOKEN=tok\n")

        # Point to nonexistent profiles.json so profiles path is skipped
        fake_profiles = tmp_path / "nonexistent" / "profiles.json"

        with mock.patch('lib.config.PROFILES_FILE', fake_profiles), \
             mock.patch('lib.config.DEFAULT_ENV_FILE', env_file):
            config = jira_validate.check_environment(
                env_file=None, profile=None, verbose=True
            )

        assert config is not None
        captured = capsys.readouterr()
        assert 'Environment file' in captured.out
