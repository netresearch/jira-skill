"""Environment configuration handling for Jira CLI scripts."""

import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

# === INLINE_START: config ===


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

DEFAULT_ENV_FILE = Path.home() / ".env.jira"
PROFILES_FILE = Path.home() / ".jira" / "profiles.json"

# Cloud authentication: JIRA_USERNAME + JIRA_API_TOKEN
# Server/DC authentication: JIRA_PERSONAL_TOKEN (PAT)
REQUIRED_URL = 'JIRA_URL'
CLOUD_VARS = ['JIRA_USERNAME', 'JIRA_API_TOKEN']
SERVER_VARS = ['JIRA_PERSONAL_TOKEN']
OPTIONAL_VARS = ['JIRA_CLOUD']
ALL_VARS = [REQUIRED_URL] + CLOUD_VARS + SERVER_VARS + OPTIONAL_VARS


def load_env(env_file: str | None = None) -> dict:
    """Load configuration from file with environment variable fallback.

    Priority order:
    1. Explicit env_file parameter (must exist if specified)
    2. ~/.env.jira (if exists)
    3. Environment variables (fallback for missing values)

    Supports two authentication modes:
    - Cloud: JIRA_URL + JIRA_USERNAME + JIRA_API_TOKEN
    - Server/DC: JIRA_URL + JIRA_PERSONAL_TOKEN

    Args:
        env_file: Path to environment file. If specified, file must exist.

    Returns:
        Dictionary of configuration values

    Raises:
        FileNotFoundError: If explicit env_file doesn't exist
    """
    config = {}
    path = Path(env_file) if env_file else DEFAULT_ENV_FILE

    # Load from file if it exists (or raise if explicitly specified but missing)
    if path.exists():
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, _, value = line.partition('=')
                    key = key.strip()
                    # Strip optional 'export' prefix (bash compatibility)
                    if key.startswith('export '):
                        key = key[7:].strip()
                    config[key] = value.strip().strip('"').strip("'")
    elif env_file:
        # Explicit file was specified but doesn't exist
        raise FileNotFoundError(f"Environment file not found: {path}")

    # Fill in missing values from environment variables
    for var in ALL_VARS:
        if var not in config and var in os.environ:
            config[var] = os.environ[var]

    return config


def validate_config(config: dict) -> list:
    """Validate configuration has all required variables.

    Supports two authentication modes:
    - Cloud: JIRA_URL + JIRA_USERNAME + JIRA_API_TOKEN
    - Server/DC: JIRA_URL + JIRA_PERSONAL_TOKEN

    Args:
        config: Configuration dictionary

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []

    # JIRA_URL is always required
    if REQUIRED_URL not in config or not config[REQUIRED_URL]:
        errors.append(f"Missing required variable: {REQUIRED_URL}")

    # Validate URL format
    if REQUIRED_URL in config and config[REQUIRED_URL]:
        url = config[REQUIRED_URL]
        if not url.startswith(('http://', 'https://')):
            errors.append(f"JIRA_URL must start with http:// or https://: {url}")

    # Check for valid authentication configuration
    has_cloud_auth = all(config.get(var) for var in CLOUD_VARS)
    has_server_auth = config.get('JIRA_PERSONAL_TOKEN')

    if not has_cloud_auth and not has_server_auth:
        errors.append(
            "Missing authentication credentials. Provide either:\n"
            "    - JIRA_USERNAME + JIRA_API_TOKEN (for Cloud)\n"
            "    - JIRA_PERSONAL_TOKEN (for Server/DC)"
        )

    return errors


def get_auth_mode(config: dict) -> str:
    """Determine authentication mode from config.

    Args:
        config: Configuration dictionary

    Returns:
        'cloud' for Cloud auth, 'pat' for Personal Access Token
    """
    if config.get('JIRA_PERSONAL_TOKEN'):
        return 'pat'
    return 'cloud'


def load_profiles() -> dict:
    """Load and validate profiles from ~/.jira/profiles.json.

    Returns:
        Parsed profiles dictionary

    Raises:
        FileNotFoundError: If profiles.json doesn't exist
        ValueError: If profiles.json is invalid
    """
    if not PROFILES_FILE.exists():
        raise FileNotFoundError(f"Profiles file not found: {PROFILES_FILE}")

    try:
        data = json.loads(PROFILES_FILE.read_text())
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {PROFILES_FILE}: {e}") from e

    if not isinstance(data, dict) or 'profiles' not in data:
        raise ValueError(f"Invalid profiles format: missing 'profiles' key in {PROFILES_FILE}")

    if not isinstance(data['profiles'], dict) or not data['profiles']:
        raise ValueError(f"No profiles defined in {PROFILES_FILE}")

    return data


def resolve_profile(issue_key: str | None = None, url: str | None = None,
                    profile: str | None = None, project_dir: str | None = None) -> dict:
    """Resolve a Jira profile using the priority algorithm.

    Priority:
    1. Explicit profile name
    2. Full Jira URL → match host against profile.url
    3. Ticket key → match project prefix against profiles[].projects
    4. .jira-profile file in project directory
    5. Default profile from profiles.json

    Args:
        issue_key: Jira issue key (e.g. WEB-1381)
        url: Full Jira URL
        profile: Explicit profile name
        project_dir: Project directory path to check for .jira-profile

    Returns:
        Profile configuration dictionary with 'name' key added

    Raises:
        FileNotFoundError: If profiles.json doesn't exist
        ValueError: If profile cannot be resolved or is ambiguous
    """
    data = load_profiles()
    profiles = data['profiles']

    # Step 1: Explicit profile name
    if profile:
        if profile not in profiles:
            available = ', '.join(sorted(profiles.keys()))
            raise ValueError(f"Profile '{profile}' not found. Available: {available}")
        result = dict(profiles[profile])
        result['name'] = profile
        return result

    # Step 2: Full Jira URL → match host (normalized to strip default ports)
    if url:
        input_host = _normalize_netloc(url)
        if input_host:
            for name, prof in profiles.items():
                prof_host = _normalize_netloc(prof.get('url', ''))
                if prof_host and prof_host == input_host:
                    result = dict(prof)
                    result['name'] = name
                    return result

    # Step 3: Ticket key → match project prefix
    if issue_key:
        match = re.match(r'^([A-Z][A-Z0-9_]+)-\d+$', issue_key)
        if match:
            prefix = match.group(1)
            matching_profiles = []
            for name, prof in profiles.items():
                projects = prof.get('projects')
                if isinstance(projects, list) and prefix in projects:
                    matching_profiles.append(name)

            if len(matching_profiles) == 1:
                result = dict(profiles[matching_profiles[0]])
                result['name'] = matching_profiles[0]
                return result
            elif len(matching_profiles) > 1:
                names = ', '.join(sorted(matching_profiles))
                raise ValueError(
                    f"{prefix} found in profiles: {names}. Use --profile to disambiguate."
                )

    # Step 4: .jira-profile file in project directory
    if project_dir:
        profile_file = Path(project_dir) / '.jira-profile'
        if profile_file.exists():
            dir_profile = profile_file.read_text().strip()
            if dir_profile in profiles:
                result = dict(profiles[dir_profile])
                result['name'] = dir_profile
                return result
            else:
                print(
                    f"⚠ .jira-profile references unknown profile '{dir_profile}', skipping",
                    file=sys.stderr,
                )

    # Step 5: Default profile
    default_name = data.get('default')
    if default_name and default_name in profiles:
        result = dict(profiles[default_name])
        result['name'] = default_name
        return result

    # No match found
    available = ', '.join(sorted(profiles.keys()))
    raise ValueError(
        f"Could not resolve profile. Available profiles: {available}. "
        f"Use --profile to specify one."
    )


def is_cloud_url(url: str) -> bool:
    """Check if a Jira URL points to Atlassian Cloud.

    Uses strict domain matching: must be exactly 'atlassian.net' or end with
    '.atlassian.net'. This prevents bypass via malicious domains like
    'attacker-atlassian.net.evil.com'.

    Args:
        url: Jira instance URL

    Returns:
        True if the URL is an Atlassian Cloud instance
    """
    netloc = urlparse(url).netloc.lower()
    return netloc == 'atlassian.net' or netloc.endswith('.atlassian.net')


def profile_to_config(prof: dict) -> dict:
    """Convert a profile dict to the env-style config dict used by the client.

    Args:
        prof: Profile dictionary from profiles.json

    Returns:
        Config dictionary compatible with validate_config/get_jira_client

    Raises:
        ValueError: If required fields are missing
    """
    url = prof.get('url')
    if not url:
        raise ValueError("Profile is missing required 'url' field")
    config = {'JIRA_URL': url}

    auth = prof.get('auth', 'pat')
    if auth == 'cloud':
        if not prof.get('username') or not prof.get('api_token'):
            raise ValueError("Profile is missing required 'username' and/or 'api_token' fields for cloud auth")
        config['JIRA_USERNAME'] = prof['username']
        config['JIRA_API_TOKEN'] = prof['api_token']
    else:
        if not prof.get('token'):
            raise ValueError("Profile is missing required 'token' field for PAT auth")
        config['JIRA_PERSONAL_TOKEN'] = prof['token']

    return config


def load_config(profile: str | None = None, env_file: str | None = None,
                issue_key: str | None = None, url: str | None = None) -> dict:
    """Unified configuration loader combining profiles and legacy env files.

    Priority:
    1. Explicit --env-file → legacy env file behavior
    2. profiles.json exists → profile resolution
    3. Legacy fallback → ~/.env.jira

    Args:
        profile: Explicit profile name
        env_file: Explicit env file path
        issue_key: Issue key for auto-resolution
        url: Jira URL for auto-resolution

    Returns:
        Config dictionary ready for get_jira_client
    """
    # --env-file always takes precedence
    if env_file:
        return load_env(env_file)

    # Try profile resolution if profiles.json exists
    if PROFILES_FILE.exists():
        try:
            cwd = os.getcwd()
        except OSError:
            cwd = None

        prof = resolve_profile(
            issue_key=issue_key,
            url=url,
            profile=profile,
            project_dir=cwd,
        )
        return profile_to_config(prof)

    # Explicit --profile but no profiles.json
    if profile:
        raise FileNotFoundError(
            f"Profile '{profile}' requested but {PROFILES_FILE} does not exist.\n"
            f"  Run: uv run scripts/core/jira-setup.py --profile {profile}"
        )

    # Legacy fallback
    return load_env()

# === INLINE_END: config ===
