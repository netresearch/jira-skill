#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "atlassian-python-api>=3.41.0",
#     "click>=8.1.0",
#     "requests>=2.28.0",
# ]
# ///
"""Jira environment validation - verify runtime, configuration, and connectivity."""

import shutil
import subprocess
import sys
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════════════
# Shared library import (TR1.1.1 - PYTHONPATH approach)
# ═══════════════════════════════════════════════════════════════════════════════
_script_dir = Path(__file__).parent
_lib_path = _script_dir.parent / "lib"
if _lib_path.exists():
    sys.path.insert(0, str(_lib_path.parent))

import click
import requests
from lib.config import load_env, validate_config, get_auth_mode, DEFAULT_ENV_FILE
from lib.client import get_jira_client
from lib.output import success, error, warning

# ═══════════════════════════════════════════════════════════════════════════════
# Exit Codes (TR2.3)
# ═══════════════════════════════════════════════════════════════════════════════
EXIT_SUCCESS = 0
EXIT_RUNTIME_ERROR = 1
EXIT_CONFIG_ERROR = 2
EXIT_CONNECTION_ERROR = 3


def check_runtime(verbose: bool = False) -> bool:
    """Check runtime dependencies (D7)."""
    checks_passed = True

    # Check uv/uvx
    uv_path = shutil.which('uv')
    if uv_path:
        if verbose:
            # Get version
            result = subprocess.run(['uv', '--version'], capture_output=True, text=True)
            version = result.stdout.strip() if result.returncode == 0 else 'unknown'
            success(f"uv found: {uv_path} ({version})")
    else:
        error(
            "Runtime check failed: 'uv' command not found",
            "To install uv, run:\n"
            "    curl -LsSf https://astral.sh/uv/install.sh | sh\n\n"
            "  Or visit: https://docs.astral.sh/uv/getting-started/installation/"
        )
        checks_passed = False

    # Check Python version
    py_version = sys.version_info
    if py_version >= (3, 10):
        if verbose:
            success(f"Python version: {py_version.major}.{py_version.minor}.{py_version.micro}")
    else:
        error(
            f"Python version {py_version.major}.{py_version.minor} < 3.10 required",
            "Please upgrade Python to 3.10 or later"
        )
        checks_passed = False

    return checks_passed


def check_environment(env_file: str | None, verbose: bool = False) -> dict | None:
    """Check environment configuration."""
    try:
        config = load_env(env_file)
        errors = validate_config(config)

        if errors:
            for err in errors:
                error(f"Configuration error: {err}")
            return None

        if verbose:
            path = Path(env_file) if env_file else DEFAULT_ENV_FILE
            success(f"Environment file: {path}")
            success(f"JIRA_URL: {config['JIRA_URL']}")

            # Show auth mode-specific credentials
            auth_mode = get_auth_mode(config)
            if auth_mode == 'pat':
                success("Auth mode: Personal Access Token (Server/DC)")
                success("JIRA_PERSONAL_TOKEN: ******* (hidden)")
            else:
                success("Auth mode: Username + API Token (Cloud)")
                success(f"JIRA_USERNAME: {config.get('JIRA_USERNAME', 'N/A')}")
                success("JIRA_API_TOKEN: ******* (hidden)")

            if 'JIRA_CLOUD' in config:
                success(f"JIRA_CLOUD: {config['JIRA_CLOUD']}")

        return config

    except FileNotFoundError as e:
        error(str(e))
        return None


def check_connectivity(config: dict, project: str | None, verbose: bool = False) -> bool:
    """Check connectivity and authentication."""
    url = config['JIRA_URL']

    # Test server reachability
    try:
        response = requests.head(url, timeout=10, allow_redirects=True)
        if verbose:
            success(f"Server reachable: {url} (status: {response.status_code})")
    except requests.exceptions.Timeout:
        error(
            f"Connection timeout: {url}",
            "The server did not respond within 10 seconds.\n"
            "  Check your network connection and JIRA_URL."
        )
        return False
    except requests.exceptions.ConnectionError as e:
        error(
            f"Connection failed: {url}",
            f"Could not connect to the server.\n  Error: {e}"
        )
        return False

    # Test authentication
    try:
        client = get_jira_client()
        user = client.myself()

        if verbose:
            display_name = user.get('displayName', user.get('name', 'Unknown'))
            email = user.get('emailAddress', 'N/A')
            success(f"Authenticated as: {display_name} ({email})")
        else:
            success("Authentication successful")

    except Exception as e:
        error(
            "Authentication failed",
            f"Could not authenticate with the provided credentials.\n  Error: {e}"
        )
        return False

    # Test project access (optional)
    if project:
        try:
            proj = client.project(project)
            if verbose:
                success(f"Project access: {project} ({proj.get('name', 'Unknown')})")
            else:
                success(f"Project access verified: {project}")
        except Exception as e:
            warning(f"Could not access project {project}: {e}")
            # Don't fail on project access - might just be wrong key

    return True


@click.command()
@click.option('--verbose', '-v', is_flag=True, help='Show detailed output')
@click.option('--project', '-p', help='Verify access to specific project')
@click.option('--env-file', type=click.Path(exists=False), help='Path to environment file')
def main(verbose: bool, project: str | None, env_file: str | None):
    """Validate Jira environment configuration.

    Checks runtime dependencies, environment configuration, and connectivity
    to ensure the Jira CLI scripts will work correctly.

    Exit codes:
      0 - All checks passed
      1 - Runtime dependency missing
      2 - Environment configuration error
      3 - Connectivity/authentication failure
    """
    if verbose:
        click.echo("=" * 60)
        click.echo("Jira Environment Validation")
        click.echo("=" * 60)
        click.echo()

    # Check 1: Runtime
    if verbose:
        click.echo("Runtime Checks:")
    if not check_runtime(verbose):
        sys.exit(EXIT_RUNTIME_ERROR)
    if verbose:
        click.echo()

    # Check 2: Environment
    if verbose:
        click.echo("Environment Checks:")
    config = check_environment(env_file, verbose)
    if config is None:
        sys.exit(EXIT_CONFIG_ERROR)
    if verbose:
        click.echo()

    # Check 3: Connectivity
    if verbose:
        click.echo("Connectivity Checks:")
    if not check_connectivity(config, project, verbose):
        sys.exit(EXIT_CONNECTION_ERROR)
    if verbose:
        click.echo()

    # All passed
    if verbose:
        click.echo("=" * 60)
    success("All validation checks passed!")
    sys.exit(EXIT_SUCCESS)


if __name__ == '__main__':
    main()
