#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "atlassian-python-api>=3.41.0,<4",
#     "click>=8.1.0,<9",
#     "requests>=2.31.0,<3",
# ]
# ///
"""Interactive Jira credential setup - configure authentication interactively."""

import os
import sys
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════════════
# Shared library import (TR1.1.1 - PYTHONPATH approach)
# ═══════════════════════════════════════════════════════════════════════════════
_script_dir = Path(__file__).parent
_lib_path = _script_dir.parent / "lib"
if _lib_path.exists():
    sys.path.insert(0, str(_lib_path.parent))

import json

import click
import requests
from atlassian import Jira
from lib.client import JIRA_TIMEOUT, _sanitize_error
from lib.config import DEFAULT_ENV_FILE, PROFILES_FILE, is_cloud_url, load_env
from lib.output import error, success, warning

# ═══════════════════════════════════════════════════════════════════════════════
# Exit Codes
# ═══════════════════════════════════════════════════════════════════════════════
EXIT_SUCCESS = 0
EXIT_USER_ABORT = 1
EXIT_VALIDATION_FAILED = 2


def detect_jira_type(url: str) -> str:
    """Detect if URL is Jira Cloud or Server/Data Center.

    Args:
        url: Jira instance URL

    Returns:
        'cloud' for Atlassian Cloud, 'server' for Server/DC
    """
    return 'cloud' if is_cloud_url(url) else 'server'


def validate_url(url: str) -> tuple[bool, str]:
    """Validate Jira URL is reachable.

    Args:
        url: URL to validate

    Returns:
        Tuple of (success, message)
    """
    if not url.startswith(('http://', 'https://')):
        return False, "URL must start with http:// or https://"

    try:
        response = requests.head(url, timeout=10, allow_redirects=True)
        status = response.status_code
        # 405 = HEAD not allowed — fall back to GET
        if status == 405:
            response = requests.get(url, timeout=10, allow_redirects=True, stream=True)
            response.close()
            status = response.status_code
        if status < 400:
            return True, f"Server reachable (status: {status})"
        if status in (401, 403):
            return True, f"Server reachable, authentication required (status: {status})"
        if status < 500:
            return False, f"Client error when contacting server (status: {status})"
        return False, f"Server error (status: {status})"
    except requests.exceptions.Timeout:
        return False, "Connection timeout - server did not respond"
    except requests.exceptions.ConnectionError as e:
        return False, f"Connection failed: {_sanitize_error(str(e))}"


def validate_credentials(url: str, auth_type: str, **kwargs) -> tuple[bool, str]:
    """Validate Jira credentials by attempting authentication.

    Args:
        url: Jira instance URL
        auth_type: 'cloud' or 'server'
        **kwargs: Authentication credentials

    Returns:
        Tuple of (success, message/user_info)
    """
    try:
        if auth_type == 'cloud':
            client = Jira(
                url=url,
                username=kwargs['username'],
                password=kwargs['api_token'],
                cloud=True,
                timeout=JIRA_TIMEOUT,
            )
        else:
            client = Jira(
                url=url,
                token=kwargs['personal_token'],
                timeout=JIRA_TIMEOUT,
            )

        user = client.myself()
        if isinstance(user, dict):
            display_name = user.get('displayName', user.get('name', 'Unknown'))
            email = user.get('emailAddress', '')
        else:
            user_str = str(user) if user else ''
            # Detect HTML response (2FA/Secure Login intercept)
            if user_str.lstrip().startswith(('<!DOCTYPE', '<html', '<HTML')):
                return False, (
                    "Two-factor authentication (2FA/Secure Login) intercepted the API call. "
                    "Your PAT may not bypass 2FA on this instance. "
                    "Check Jira admin settings or create a new PAT with API access."
                )
            display_name = user_str or 'Unknown'
            email = ''
        return True, f"{display_name}" + (f" ({email})" if email else "")

    except Exception as e:
        error_msg = _sanitize_error(str(e))
        if '401' in error_msg or 'Unauthorized' in error_msg:
            return False, "Authentication failed - invalid credentials"
        if '403' in error_msg or 'Forbidden' in error_msg:
            return False, "Access denied - check permissions"
        return False, f"Connection error: {error_msg}"


def write_env_file(path: Path, config: dict) -> None:
    """Write configuration to environment file.

    Security note: Credentials are stored in clear text, similar to standard
    credential files like ~/.netrc, ~/.npmrc, or ~/.aws/credentials. The file
    is protected by restrictive filesystem permissions (0600 - owner read/write
    only). This is an intentional design choice following common CLI tool patterns.

    Args:
        path: Path to write
        config: Configuration dictionary
    """
    lines = [
        "# Jira CLI Configuration",
        "# Generated by jira-setup.py",
        "# Security: This file contains credentials and is protected by 0600 permissions",
        "",
    ]

    for key, value in config.items():
        if value:
            lines.append(f"{key}={value}")

    lines.append("")

    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f:
        f.write("\n".join(lines))
    os.chmod(path, 0o600)


def write_profile(profile_name: str, profile_data: dict) -> None:
    """Write or update a profile in ~/.jira/profiles.json.

    Args:
        profile_name: Name for the profile
        profile_data: Profile configuration dict (url, auth, token/credentials, projects)
    """
    profiles_dir = PROFILES_FILE.parent

    # Load existing or create new
    if PROFILES_FILE.exists():
        try:
            data = json.loads(PROFILES_FILE.read_text())
        except json.JSONDecodeError:
            warning(f"{PROFILES_FILE} is corrupted. Creating backup and starting fresh.")
            PROFILES_FILE.replace(PROFILES_FILE.with_suffix('.json.bak'))
            data = {'version': 1, 'profiles': {}}
        else:
            # Validate structure: must be a dict with a 'profiles' dict
            if not isinstance(data, dict) or not isinstance(data.get('profiles'), dict):
                warning(f"{PROFILES_FILE} has invalid structure. Creating backup and starting fresh.")
                PROFILES_FILE.replace(PROFILES_FILE.with_suffix('.json.bak'))
                data = {'version': 1, 'profiles': {}}
    else:
        profiles_dir.mkdir(parents=True, exist_ok=True)
        data = {'version': 1, 'profiles': {}}

    # Update profile
    data['profiles'][profile_name] = profile_data

    # Set default if first profile
    if 'default' not in data or not data['default']:
        data['default'] = profile_name

    # Write with restricted permissions from creation (no race condition)
    fd = os.open(PROFILES_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f:
        f.write(json.dumps(data, indent=2) + '\n')
    os.chmod(PROFILES_FILE, 0o600)


def migrate_env_to_profile() -> None:
    """Migrate ~/.env.jira to ~/.jira/profiles.json."""
    if not DEFAULT_ENV_FILE.exists():
        error(f"No env file found at {DEFAULT_ENV_FILE}")
        sys.exit(EXIT_VALIDATION_FAILED)

    if PROFILES_FILE.exists():
        click.echo(f"⚠ Profiles file already exists: {PROFILES_FILE}")
        if not click.confirm("Add legacy config as 'default' profile?", default=False):
            click.echo("\nMigration cancelled.")
            sys.exit(EXIT_USER_ABORT)

    config = load_env()

    url = config.get('JIRA_URL', '')
    profile_data = {'url': url}

    if config.get('JIRA_PERSONAL_TOKEN'):
        profile_data['auth'] = 'pat'
        profile_data['token'] = config['JIRA_PERSONAL_TOKEN']
    else:
        profile_data['auth'] = 'cloud'
        profile_data['username'] = config.get('JIRA_USERNAME', '')
        profile_data['api_token'] = config.get('JIRA_API_TOKEN', '')

    profile_data['projects'] = []

    write_profile('default', profile_data)
    success(f"Migrated {DEFAULT_ENV_FILE} → {PROFILES_FILE} (profile: 'default')")
    click.echo()
    click.echo("You can now add project keys to the profile:")
    click.echo(f'  Edit {PROFILES_FILE} and add project keys to "projects": []')


@click.command()
@click.option('--url', help='Jira instance URL (will prompt if not provided)')
@click.option('--type', 'jira_type', type=click.Choice(['cloud', 'server', 'auto']),
              default='auto', help='Jira deployment type')
@click.option('--output', '-o', type=click.Path(), default=str(DEFAULT_ENV_FILE),
              help=f'Output file path (default: {DEFAULT_ENV_FILE})')
@click.option('--force', '-f', is_flag=True, help='Overwrite existing file without prompting')
@click.option('--test-only', is_flag=True, help='Test credentials without saving')
@click.option('--profile', '-P', help='Save as named profile in ~/.jira/profiles.json')
@click.option('--projects', help='Comma-separated project keys for the profile')
@click.option('--migrate', is_flag=True, help='Migrate ~/.env.jira to profiles.json')
def main(url: str | None, jira_type: str, output: str, force: bool, test_only: bool,
         profile: str | None, projects: str | None, migrate: bool):
    """Interactive Jira credential setup.

    Guides you through configuring Jira authentication credentials
    and validates them before saving to ~/.env.jira or ~/.jira/profiles.json.

    Supports both Jira Cloud (username + API token) and
    Jira Server/Data Center (Personal Access Token).

    \b
    Examples:
      # Interactive setup (legacy env file)
      uv run scripts/core/jira-setup.py

      # Setup as named profile
      uv run scripts/core/jira-setup.py --profile mkk --url https://jira.example.com

      # Pre-fill URL
      uv run scripts/core/jira-setup.py --url https://company.atlassian.net

      # Test credentials without saving
      uv run scripts/core/jira-setup.py --test-only

      # Migrate existing .env.jira to profiles.json
      uv run scripts/core/jira-setup.py --migrate
    """
    # Handle migration mode
    if migrate:
        click.echo()
        click.echo("=" * 60)
        click.echo("  Migrate ~/.env.jira → ~/.jira/profiles.json")
        click.echo("=" * 60)
        click.echo()
        migrate_env_to_profile()
        sys.exit(EXIT_SUCCESS)

    click.echo()
    click.echo("=" * 60)
    if profile:
        click.echo(f"  Jira Profile Setup: {profile}")
    else:
        click.echo("  Jira Credential Setup")
    click.echo("=" * 60)
    click.echo()

    # For non-profile mode, check existing env file
    if not profile:
        output_path = Path(output)
        if output_path.exists() and not force and not test_only:
            click.echo(f"⚠ Configuration file already exists: {output_path}")
            if not click.confirm("Do you want to overwrite it?", default=False):
                click.echo("\nSetup cancelled.")
                sys.exit(EXIT_USER_ABORT)
            click.echo()

    # Step 1: Get Jira URL
    click.echo("Step 1: Jira Instance URL")
    click.echo("-" * 40)

    if url:
        click.echo(f"Using provided URL: {url}")
    else:
        click.echo("Enter your Jira instance URL.")
        click.echo("Examples:")
        click.echo("  - https://company.atlassian.net (Jira Cloud)")
        click.echo("  - https://jira.company.com (Jira Server/DC)")
        click.echo()
        url = click.prompt("Jira URL", type=str).strip().rstrip('/')

    # Warn about non-HTTPS URLs
    if url.startswith('http://') and not url.startswith('http://localhost'):
        warning("Using HTTP without TLS. Credentials will be transmitted in plaintext.")

    # Validate URL
    click.echo()
    click.echo("Validating URL...", nl=False)
    url_ok, url_msg = validate_url(url)
    if url_ok:
        click.echo(f" ✓ {url_msg}")
    else:
        click.echo(" ✗")
        error(f"URL validation failed: {url_msg}")
        sys.exit(EXIT_VALIDATION_FAILED)

    # Step 2: Detect/confirm Jira type
    click.echo()
    click.echo("Step 2: Authentication Type")
    click.echo("-" * 40)

    if jira_type == 'auto':
        detected = detect_jira_type(url)
        click.echo(f"Detected Jira type: {detected.upper()}")

        if detected == 'cloud':
            click.echo("  → Using Username + API Token authentication")
        else:
            click.echo("  → Using Personal Access Token (PAT) authentication")

        if not click.confirm("Is this correct?", default=True):
            jira_type = click.prompt(
                "Select type",
                type=click.Choice(['cloud', 'server']),
                default=detected
            )
        else:
            jira_type = detected

    click.echo()

    # Step 3: Get credentials
    click.echo("Step 3: Credentials")
    click.echo("-" * 40)

    config = {'JIRA_URL': url}

    if jira_type == 'cloud':
        click.echo("Jira Cloud authentication requires:")
        click.echo("  1. Your Atlassian account email")
        click.echo("  2. An API token (create at https://id.atlassian.com/manage-profile/security/api-tokens)")
        click.echo()

        username = click.prompt("Email address", type=str).strip()
        api_token = click.prompt("API Token", type=str, hide_input=True).strip()

        config['JIRA_USERNAME'] = username
        config['JIRA_API_TOKEN'] = api_token

        # Validate
        click.echo()
        click.echo("Validating credentials...", nl=False)
        cred_ok, cred_msg = validate_credentials(url, 'cloud',
                                                  username=username,
                                                  api_token=api_token)
    else:
        click.echo("Jira Server/Data Center authentication requires:")
        click.echo("  - A Personal Access Token (PAT)")
        click.echo("  - Create one in Jira: Profile → Personal Access Tokens → Create token")
        click.echo()

        personal_token = click.prompt("Personal Access Token", type=str, hide_input=True).strip()

        config['JIRA_PERSONAL_TOKEN'] = personal_token

        # Validate
        click.echo()
        click.echo("Validating credentials...", nl=False)
        cred_ok, cred_msg = validate_credentials(url, 'server',
                                                  personal_token=personal_token)

    if cred_ok:
        click.echo(" ✓")
        success(f"Authenticated as: {cred_msg}")
    else:
        click.echo(" ✗")
        error(f"Authentication failed: {cred_msg}")

        if jira_type == 'cloud':
            click.echo()
            click.echo("Troubleshooting tips:")
            click.echo("  1. Verify your email address is correct")
            click.echo("  2. Generate a new API token at:")
            click.echo("     https://id.atlassian.com/manage-profile/security/api-tokens")
            click.echo("  3. Make sure you're using the token, not your password")
        else:
            click.echo()
            click.echo("Troubleshooting tips:")
            click.echo("  1. Create a new PAT in Jira: Profile → Personal Access Tokens")
            click.echo("  2. Ensure the token has not expired")
            click.echo("  3. Check that you have access to the Jira instance")

        sys.exit(EXIT_VALIDATION_FAILED)

    # Step 4: Save configuration
    if test_only:
        click.echo()
        click.echo("=" * 60)
        success("Credentials validated successfully!")
        click.echo("(--test-only mode: not saving to file)")
        sys.exit(EXIT_SUCCESS)

    click.echo()
    click.echo("Step 4: Save Configuration")
    click.echo("-" * 40)

    if profile:
        # Profile mode: save to ~/.jira/profiles.json
        click.echo(f"Profile '{profile}' will be saved to: {PROFILES_FILE}")
        click.echo("File permissions will be set to 600 (owner read/write only)")

        # Get project keys
        project_list = []
        if projects:
            project_list = [p.strip() for p in projects.split(',') if p.strip()]
        else:
            click.echo()
            proj_input = click.prompt(
                "Project keys (comma-separated, e.g. WEB,INFRA)",
                type=str, default='', show_default=False
            ).strip()
            if proj_input:
                project_list = [p.strip() for p in proj_input.split(',') if p.strip()]

        if click.confirm("Save profile?", default=True):
            profile_data = {'url': url}

            if jira_type == 'cloud':
                profile_data['auth'] = 'cloud'
                profile_data['username'] = config['JIRA_USERNAME']
                profile_data['api_token'] = config['JIRA_API_TOKEN']
            else:
                profile_data['auth'] = 'pat'
                profile_data['token'] = config['JIRA_PERSONAL_TOKEN']

            if project_list:
                profile_data['projects'] = project_list

            write_profile(profile, profile_data)
            click.echo()
            click.echo("=" * 60)
            success(f"Profile '{profile}' saved to {PROFILES_FILE}")
            click.echo()
            click.echo("You can now use the Jira CLI scripts:")
            click.echo(f"  uv run scripts/core/jira-validate.py --profile {profile} --verbose")
            click.echo(f"  uv run scripts/core/jira-issue.py --profile {profile} get PROJ-123")
            if project_list:
                click.echo(f"\n  Auto-resolution enabled for projects: {', '.join(project_list)}")
        else:
            click.echo("\nProfile not saved.")
            sys.exit(EXIT_USER_ABORT)
    else:
        # Legacy mode: save to env file
        output_path = Path(output)
        click.echo(f"Configuration will be saved to: {output_path}")
        click.echo("File permissions will be set to 600 (owner read/write only)")

        if click.confirm("Save configuration?", default=True):
            write_env_file(output_path, config)
            click.echo()
            click.echo("=" * 60)
            success(f"Configuration saved to {output_path}")
            click.echo()
            click.echo("You can now use the Jira CLI scripts:")
            click.echo("  uv run scripts/core/jira-validate.py --verbose")
            click.echo("  uv run scripts/core/jira-issue.py get PROJ-123")
        else:
            click.echo("\nConfiguration not saved.")
            sys.exit(EXIT_USER_ABORT)

    sys.exit(EXIT_SUCCESS)


if __name__ == '__main__':
    main()
