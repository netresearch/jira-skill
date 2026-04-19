"""Shared utilities for Jira CLI scripts."""

from .output import extract_adf_text, format_json, format_output, format_table

try:
    from .client import LazyJiraClient, get_jira_client, is_account_id
except (ImportError, TypeError):
    LazyJiraClient = None
    get_jira_client = None
    is_account_id = None

try:
    from .config import (
        get_auth_mode,
        load_config,
        load_env,
        load_profiles,
        profile_to_config,
        resolve_profile,
        validate_config,
    )
except (ImportError, TypeError):
    get_auth_mode = None
    load_config = None
    load_env = None
    load_profiles = None
    profile_to_config = None
    resolve_profile = None
    validate_config = None

__all__ = [
    "get_jira_client",
    "LazyJiraClient",
    "is_account_id",
    "load_env",
    "load_config",
    "load_profiles",
    "resolve_profile",
    "profile_to_config",
    "validate_config",
    "get_auth_mode",
    "format_output",
    "format_json",
    "format_table",
    "extract_adf_text",
]
