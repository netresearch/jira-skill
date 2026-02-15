#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "atlassian-python-api>=3.41.0,<4",
#     "click>=8.1.0,<9",
#     "requests>=2.31.0,<3",
# ]
# ///
"""Jira attachment operations - download attachments."""

import json
import sys
from pathlib import Path
from urllib.parse import urlparse

# ═══════════════════════════════════════════════════════════════════════════════
# Shared library import (TR1.1.1 - PYTHONPATH approach)
# ═══════════════════════════════════════════════════════════════════════════════
_script_dir = Path(__file__).parent
_lib_path = _script_dir.parent / "lib"
if _lib_path.exists():
    sys.path.insert(0, str(_lib_path.parent))

import click
import requests
from lib.config import load_config
from lib.output import error, success

# Chunk size for streaming large file downloads (1 MB)
CHUNK_SIZE = 1048576

# Timeout for attachment downloads (connect_timeout, read_timeout)
DOWNLOAD_TIMEOUT = (10, 300)


# ═══════════════════════════════════════════════════════════════════════════════
# Security Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _normalize_netloc(url: str) -> str:
    """Normalize a URL's netloc by lowercasing and stripping default ports.

    Default ports (:443 for https, :80 for http) are removed so that
    ``https://jira.example.com:443`` matches ``https://jira.example.com``.
    """
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    scheme = parsed.scheme.lower()
    if scheme == 'https' and host.endswith(':443'):
        host = host[:-4]
    elif scheme == 'http' and host.endswith(':80'):
        host = host[:-3]
    return host


def validate_attachment_url(attachment_url: str, jira_url: str) -> bool:
    """Validate that an attachment URL points to the configured Jira host.

    Prevents SSRF attacks where a malicious URL could exfiltrate Jira
    credentials to an attacker-controlled server.

    Args:
        attachment_url: The attachment URL to validate
        jira_url: The configured JIRA_URL to validate against

    Returns:
        True if the URL is safe to request with credentials
    """
    # Relative paths are always safe — they get prefixed with JIRA_URL
    if not attachment_url.startswith(("http://", "https://")):
        return True

    return _normalize_netloc(attachment_url) == _normalize_netloc(jira_url)


def validate_output_path(output_file: str, working_dir: str) -> Path | None:
    """Validate output path against path traversal attacks.

    Ensures the resolved output path stays within the working directory.

    Args:
        output_file: The requested output file path
        working_dir: The working directory to constrain output to

    Returns:
        Resolved Path if valid, None if path traversal detected
    """
    work = Path(working_dir).resolve()
    output_path = (work / output_file).resolve() if not Path(output_file).is_absolute() else Path(output_file).resolve()

    try:
        output_path.relative_to(work)
    except ValueError:
        return None
    return output_path


# ═══════════════════════════════════════════════════════════════════════════════
# CLI Definition
# ═══════════════════════════════════════════════════════════════════════════════

@click.group()
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
@click.option('--quiet', '-q', is_flag=True, help='Minimal output')
@click.option('--env-file', type=click.Path(), help='Environment file path')
@click.option('--profile', '-P', help='Jira profile name from ~/.jira/profiles.json')
@click.option('--debug', is_flag=True, help='Show debug information on errors')
@click.pass_context
def cli(ctx, output_json: bool, quiet: bool, env_file: str | None, profile: str | None, debug: bool):
    """Jira attachment operations.

    Download attachments from Jira issues.
    """
    ctx.ensure_object(dict)
    ctx.obj['json'] = output_json
    ctx.obj['quiet'] = quiet
    ctx.obj['env_file'] = env_file
    ctx.obj['profile'] = profile
    ctx.obj['debug'] = debug


@cli.command()
@click.argument('attachment_url')
@click.argument('output_file')
@click.pass_context
def download(ctx, attachment_url: str, output_file: str):
    """Download a Jira attachment.

    ATTACHMENT_URL: Full URL or attachment ID/content path

    OUTPUT_FILE: Output file path

    Examples:

      jira-attachment download https://example.atlassian.net/rest/api/2/attachment/content/12345 file.zip

      jira-attachment download /rest/api/2/attachment/content/12345 file.zip
    """
    try:
        # Load config for authentication (pass URL for host-based profile resolution)
        if attachment_url.startswith(("http://", "https://")):
            config = load_config(env_file=ctx.obj['env_file'], profile=ctx.obj.get('profile'), url=attachment_url)
        else:
            config = load_config(env_file=ctx.obj['env_file'], profile=ctx.obj.get('profile'))
        jira_url = config['JIRA_URL']

        # SSRF protection: validate attachment URL host matches JIRA_URL
        if not validate_attachment_url(attachment_url, jira_url):
            att_host = urlparse(attachment_url).netloc
            jira_host = urlparse(jira_url).netloc
            error(f"Attachment URL host '{att_host}' does not match JIRA_URL host '{jira_host}'")
            sys.exit(1)

        # Determine authentication method
        if 'JIRA_PERSONAL_TOKEN' in config:
            auth_token = config['JIRA_PERSONAL_TOKEN']
            auth = None
            headers = {'Authorization': f'Bearer {auth_token}'}
        else:
            username = config['JIRA_USERNAME']
            api_token = config['JIRA_API_TOKEN']
            auth = (username, api_token)
            headers = {}

        # Build full URL if needed
        if attachment_url.startswith(("http://", "https://")):
            url = attachment_url
        else:
            url = jira_url + attachment_url

        # Path traversal protection: validate output path
        safe_path = validate_output_path(output_file, Path.cwd())
        if safe_path is None:
            error(f"Output path escapes working directory: {output_file}")
            sys.exit(1)

        parent_dir = safe_path.parent
        if not parent_dir.exists():
            error(f"Directory does not exist: {parent_dir}")
            sys.exit(1)

        if safe_path.exists() and not safe_path.is_file():
            error(f"Output path exists and is not a file: {output_file}")
            sys.exit(1)

        # Download with authentication (explicit verify and timeout).
        # First request uses allow_redirects=False to handle CDN redirects
        # safely — Jira Cloud stores attachments in S3/CDN which returns 302.
        # We follow exactly one redirect but strip credentials to avoid
        # leaking them to the CDN host.
        response = requests.get(
            url,
            auth=auth,
            headers=headers,
            allow_redirects=False,
            stream=True,
            verify=True,
            timeout=DOWNLOAD_TIMEOUT,
        )

        # Follow one CDN redirect without forwarding credentials
        if response.status_code in (301, 302, 303, 307, 308) and 'Location' in response.headers:
            redirect_url = response.headers['Location']
            # Reject HTTP downgrade — prevents MITM on non-TLS redirects
            if redirect_url.startswith('http://'):
                error("Download failed: refusing HTTP redirect (TLS downgrade)")
                sys.exit(1)
            response = requests.get(
                redirect_url,
                allow_redirects=False,
                stream=True,
                verify=True,
                timeout=DOWNLOAD_TIMEOUT,
            )

        # Reject unexpected redirect (e.g., CDN chain with >1 hop) —
        # without this check, the 302 HTML body would be silently saved as the file.
        if 300 <= response.status_code < 400:
            error(f"Download failed: unexpected redirect (status {response.status_code})")
            sys.exit(1)

        response.raise_for_status()

        # Write to file
        with open(safe_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                f.write(chunk)

        if ctx.obj['quiet']:
            print(str(safe_path))
        elif ctx.obj['json']:
            print(json.dumps({'status': 'success', 'file': str(safe_path)}))
        else:
            success(f"Downloaded to: {safe_path}")

    except KeyError as e:
        if ctx.obj['debug']:
            raise
        error(f"Missing required configuration: {e}")
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        if ctx.obj['debug']:
            raise
        error(f"Download failed: {e}")
        sys.exit(1)
    except Exception as e:
        if ctx.obj['debug']:
            raise
        error(f"Failed to download attachment: {e}")
        sys.exit(1)


if __name__ == '__main__':
    cli()
