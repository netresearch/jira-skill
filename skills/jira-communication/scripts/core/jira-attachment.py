#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "atlassian-python-api>=3.41.0,<4",
#     "click>=8.1.0,<9",
#     "requests>=2.31.0,<3",
# ]
# ///
"""Jira attachment operations - download and upload attachments."""

import json
import mimetypes
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
from lib.client import (
    AuthenticationError,
    CaptchaError,
    LazyJiraClient,
    SessionExpiredError,
    _handle_response,
    _sanitize_error,
)
from lib.config import load_config, normalize_netloc
from lib.output import error, success, warning

# Chunk size for streaming large file downloads (1 MB)
CHUNK_SIZE = 1048576

# Timeout for attachment downloads (connect_timeout, read_timeout)
DOWNLOAD_TIMEOUT = (10, 300)

# Uploads can be large — keep connect timeout low but allow long reads.
UPLOAD_TIMEOUT = (10, 300)


# ═══════════════════════════════════════════════════════════════════════════════
# Security Helpers
# ═══════════════════════════════════════════════════════════════════════════════


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

    return normalize_netloc(attachment_url) == normalize_netloc(jira_url)


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
# Download Helpers (shared by `download` and `download-all`)
# ═══════════════════════════════════════════════════════════════════════════════


class DownloadError(Exception):
    """Raised for download-level anomalies (CDN redirects, TLS downgrade)."""


def _build_auth(config: dict) -> tuple[tuple[str, str] | None, dict]:
    """Build (auth, headers) for an authenticated Jira request.

    Personal access tokens go in a Bearer header; Cloud uses basic auth.
    """
    if "JIRA_PERSONAL_TOKEN" in config:
        return None, {"Authorization": f"Bearer {config['JIRA_PERSONAL_TOKEN']}"}
    return (config["JIRA_USERNAME"], config["JIRA_API_TOKEN"]), {}


def _stream_to_path(url: str, jira_url: str, auth, headers: dict, safe_path: Path) -> None:
    """Stream an attachment URL to safe_path with CDN-redirect protection.

    Follows exactly one CDN redirect without forwarding credentials, refuses
    TLS downgrades, and rejects unexpected redirect chains so a 302 HTML body
    is never written as the file. Raises DownloadError on redirect anomalies;
    propagates the typed auth errors from _handle_response().
    """
    response = requests.get(
        url,
        auth=auth,
        headers=headers,
        allow_redirects=False,
        stream=True,
        verify=True,
        timeout=DOWNLOAD_TIMEOUT,
    )

    # Follow one CDN redirect without forwarding credentials (Jira Cloud stores
    # attachments in S3/CDN which returns 302).
    if response.status_code in (301, 302, 303, 307, 308) and "Location" in response.headers:
        redirect_url = response.headers["Location"]
        # Reject HTTP downgrade — prevents MITM on non-TLS redirects
        if redirect_url.startswith("http://"):
            raise DownloadError("refusing HTTP redirect (TLS downgrade)")
        response = requests.get(
            redirect_url,
            allow_redirects=False,
            stream=True,
            verify=True,
            timeout=DOWNLOAD_TIMEOUT,
        )

    # Reject unexpected redirect (e.g., CDN chain with >1 hop) — without this
    # the 302 HTML body would be silently saved as the file.
    if 300 <= response.status_code < 400:
        raise DownloadError(f"unexpected redirect (status {response.status_code})")

    # _handle_response() raises typed errors for 401/403/session-expiry;
    # raise_for_status() handles the remaining 4xx/5xx.
    _handle_response(response, jira_url, url=getattr(response, "url", url))
    response.raise_for_status()

    with open(safe_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
            f.write(chunk)


def _report_download_error(ctx, exc: Exception) -> None:
    """Map a download exception to a user-facing message and exit non-zero."""
    if ctx.obj.get("debug"):
        raise exc
    if isinstance(exc, CaptchaError):
        raise exc
    if isinstance(exc, KeyError):
        # Config key names are non-sensitive metadata — no sanitization needed.
        error(f"Missing required configuration: {exc}")
    elif isinstance(exc, (SessionExpiredError, AuthenticationError)):
        error(_sanitize_error(str(exc)))
    elif isinstance(exc, (DownloadError, requests.exceptions.RequestException)):
        error(f"Download failed: {_sanitize_error(str(exc))}")
    else:
        error(f"Failed to download attachment: {_sanitize_error(str(exc))}")
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════════════
# CLI Definition
# ═══════════════════════════════════════════════════════════════════════════════


@click.group()
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option("--quiet", "-q", is_flag=True, help="Minimal output")
@click.option("--env-file", type=click.Path(), help="Environment file path")
@click.option("--profile", "-P", help="Jira profile name from ~/.jira/profiles.json")
@click.option("--debug", is_flag=True, help="Show debug information on errors")
@click.pass_context
def cli(ctx, output_json: bool, quiet: bool, env_file: str | None, profile: str | None, debug: bool):
    """Jira attachment operations.

    Download and upload Jira issue attachments.
    """
    ctx.ensure_object(dict)
    ctx.obj["json"] = output_json
    ctx.obj["quiet"] = quiet
    ctx.obj["env_file"] = env_file
    ctx.obj["profile"] = profile
    ctx.obj["debug"] = debug
    ctx.obj["client"] = LazyJiraClient(env_file=env_file, profile=profile)


@cli.command()
@click.argument("attachment_url")
@click.argument("output_file")
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
            config = load_config(env_file=ctx.obj["env_file"], profile=ctx.obj.get("profile"), url=attachment_url)
        else:
            config = load_config(env_file=ctx.obj["env_file"], profile=ctx.obj.get("profile"))
        jira_url = config["JIRA_URL"]

        # SSRF protection: validate attachment URL host matches JIRA_URL
        if not validate_attachment_url(attachment_url, jira_url):
            att_host = urlparse(attachment_url).netloc
            jira_host = urlparse(jira_url).netloc
            error(f"Attachment URL host '{att_host}' does not match JIRA_URL host '{jira_host}'")
            sys.exit(1)

        # Determine authentication method
        auth, headers = _build_auth(config)

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

        _stream_to_path(url, jira_url, auth, headers, safe_path)

        if ctx.obj["quiet"]:
            print(str(safe_path))
        elif ctx.obj["json"]:
            print(json.dumps({"status": "success", "file": str(safe_path)}))
        else:
            success(f"Downloaded to: {safe_path}")

    except Exception as e:
        _report_download_error(ctx, e)


@cli.command("download-all")
@click.argument("issue_key")
@click.option("--dir", "output_dir", default=".", help="Output directory (created if missing; must stay within cwd)")
@click.option("--dry-run", is_flag=True, help="List attachments without downloading")
@click.pass_context
def download_all(ctx, issue_key: str, output_dir: str, dry_run: bool):
    """Download all attachments of a Jira issue.

    ISSUE_KEY: The Jira issue key (e.g., PROJ-123)

    Files are saved under --dir using their original Jira filenames. Duplicate
    filenames are disambiguated with the attachment id. Files whose name would
    escape --dir are skipped.

    Examples:

      jira-attachment download-all PROJ-123

      jira-attachment download-all PROJ-123 --dir ./attachments

      jira-attachment download-all PROJ-123 --dry-run
    """
    try:
        config = load_config(env_file=ctx.obj["env_file"], profile=ctx.obj.get("profile"))
        jira_url = config["JIRA_URL"]
        auth, headers = _build_auth(config)

        # Path traversal protection: constrain output dir within cwd (matches `download`)
        safe_dir = validate_output_path(output_dir, Path.cwd())
        if safe_dir is None:
            error(f"Output directory escapes working directory: {output_dir}")
            sys.exit(1)

        # Fetch attachment metadata for the issue
        meta_response = requests.get(
            f"{jira_url}/rest/api/2/issue/{issue_key}",
            params={"fields": "attachment"},
            auth=auth,
            headers={**headers, "Accept": "application/json"},
            verify=True,
            timeout=DOWNLOAD_TIMEOUT,
        )
        _handle_response(meta_response, jira_url, url=getattr(meta_response, "url", None))
        meta_response.raise_for_status()
        attachments = (meta_response.json().get("fields") or {}).get("attachment") or []

        if not attachments:
            if ctx.obj["json"]:
                print(json.dumps({"status": "success", "issue": issue_key, "count": 0, "downloaded": []}))
            elif not ctx.obj["quiet"]:
                warning(f"No attachments on {issue_key}")
            return

        if dry_run:
            if ctx.obj["json"]:
                print(
                    json.dumps(
                        {
                            "status": "dry-run",
                            "issue": issue_key,
                            "count": len(attachments),
                            "attachments": [
                                {"id": att.get("id"), "filename": att.get("filename"), "size": att.get("size", 0)}
                                for att in attachments
                            ],
                        }
                    )
                )
            elif ctx.obj["quiet"]:
                for att in attachments:
                    print(att.get("filename"))
            else:
                warning(f"DRY RUN — {len(attachments)} attachment(s) on {issue_key}:")
                for att in attachments:
                    print(f"  {att.get('filename')} ({att.get('size', 0):,} bytes)")
            return

        safe_dir.mkdir(parents=True, exist_ok=True)
        downloaded: list[str] = []
        seen: set[str] = set()
        for att in attachments:
            # Strip any path components from the Jira-supplied filename (untrusted)
            filename = Path(att.get("filename", "")).name
            if not filename:
                warning(f"Skipping attachment with empty filename (id={att.get('id')})")
                continue
            # Disambiguate duplicate filenames so they don't overwrite each other
            if filename in seen:
                filename = f"{att.get('id', 'dup')}_{filename}"
            seen.add(filename)

            dest = validate_output_path(filename, str(safe_dir))
            if dest is None:
                warning(f"Skipping unsafe filename: {att.get('filename')!r}")
                continue

            # Per-file resilience: a single bad file (404/500/redirect anomaly)
            # must not abort the whole batch. Auth/session/CAPTCHA errors are NOT
            # caught here — they propagate and abort, since retrying is pointless.
            try:
                _stream_to_path(att["content"], jira_url, auth, headers, dest)
            except (DownloadError, requests.exceptions.RequestException) as e:
                warning(f"Skipping {filename}: {_sanitize_error(str(e))}")
                continue
            downloaded.append(str(dest))

        if ctx.obj["quiet"]:
            for path in downloaded:
                print(path)
        elif ctx.obj["json"]:
            print(
                json.dumps(
                    {"status": "success", "issue": issue_key, "count": len(downloaded), "downloaded": downloaded}
                )
            )
        else:
            success(f"Downloaded {len(downloaded)}/{len(attachments)} attachment(s) from {issue_key} to {safe_dir}")

    except Exception as e:
        _report_download_error(ctx, e)


@cli.command("add")
@click.argument("issue_key")
@click.argument("file_path", type=click.Path(exists=True, dir_okay=False, readable=True))
@click.option("--dry-run", is_flag=True, help="Validate file without uploading")
@click.pass_context
def add(ctx, issue_key: str, file_path: str, dry_run: bool):
    """Upload an attachment to a Jira issue.

    ISSUE_KEY: The Jira issue key (e.g., PROJ-123)

    FILE_PATH: Path to the file to attach

    Examples:

      jira-attachment add PROJ-123 screenshot.png

      jira-attachment add PROJ-123 /tmp/report.pdf --dry-run
    """
    client = ctx.obj["client"]
    client.with_context(issue_key=issue_key)

    path = Path(file_path)
    file_size = path.stat().st_size

    if dry_run:
        warning("DRY RUN — would upload:")
        print(f"  File: {path.name} ({file_size:,} bytes)")
        print(f"  Issue: {issue_key}")
        return

    try:
        mime_type, _ = mimetypes.guess_type(path.name)
        mime_type = mime_type or "application/octet-stream"

        url = f"{client.url}/rest/api/2/issue/{issue_key}/attachments"
        headers = {"X-Atlassian-Token": "nocheck"}
        with path.open("rb") as f:
            files = {"file": (path.name, f, mime_type)}
            response = client._session.post(url, files=files, headers=headers, timeout=UPLOAD_TIMEOUT)
        response.raise_for_status()
        result = response.json()

        if ctx.obj["quiet"]:
            if isinstance(result, list) and result and isinstance(result[0], dict):
                print(result[0].get("id", ""))
            else:
                print("")
        elif ctx.obj["json"]:
            print(json.dumps(result if isinstance(result, list) else [result], indent=2))
        else:
            success(f"Attached {path.name} ({file_size:,} bytes) to {issue_key}")

    except CaptchaError:
        raise
    except requests.HTTPError as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to upload attachment: {_sanitize_error(str(e))}")
        sys.exit(1)
    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to upload attachment: {_sanitize_error(str(e))}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
