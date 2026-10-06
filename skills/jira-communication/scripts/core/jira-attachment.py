#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "atlassian-python-api>=3.41.0,<4",
#     "click>=8.1.0,<9",
#     "requests>=2.31.0,<3",
#     "urllib3>=1.26,<3",
# ]
# ///
"""Jira attachment operations - download and upload attachments."""

import json
import mimetypes
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

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
from lib.config import load_config
from lib.output import error, success, warning
from urllib3.util import parse_url

# Chunk size for streaming large file downloads (1 MB)
CHUNK_SIZE = 1048576

# Timeout for attachment downloads (connect_timeout, read_timeout)
DOWNLOAD_TIMEOUT = (10, 300)

# Uploads can be large — keep connect timeout low but allow long reads.
UPLOAD_TIMEOUT = (10, 300)


# ═══════════════════════════════════════════════════════════════════════════════
# Security Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _https_origin(url: str) -> tuple[str, int] | None:
    """Return (hostname, port) of an https URL, or None for any other URL.

    The hostname is lowercased and excludes userinfo; a missing port is the
    https default. The URL is parsed both with urllib and with urllib3, the
    parser requests uses to send it; a URL the two read differently, or one
    with a malformed port, yields None.
    """
    try:
        parsed = urlparse(url)
        sent = parse_url(url)
        port = parsed.port or 443
    except ValueError:  # LocationParseError is a ValueError
        return None
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        return None
    sent_host = _bare_host(sent.host)
    if (sent.scheme or "").lower() != "https" or sent_host != _urllib3_host(parsed.hostname):
        return None
    if (sent.port or 443) != port:
        return None
    return sent_host, port


def _bare_host(host: str | None) -> str:
    """Lowercase host without the brackets urllib3 keeps around an IPv6 literal."""
    return (host or "").lower().removeprefix("[").removesuffix("]")


def _urllib3_host(hostname: str) -> str | None:
    """urllib's hostname in the form urllib3 sends it (IDNA-encoded, lowercased).

    Comparing in urllib3's form keeps an internationalised JIRA_URL working:
    urllib reports such a host in Unicode, urllib3 sends its IDNA encoding.
    """
    literal = f"[{hostname}]" if ":" in hostname else hostname
    try:
        return _bare_host(parse_url(f"https://{literal}/").host)
    except ValueError:  # LocationParseError is a ValueError
        return None


def resolve_attachment_url(attachment_url: str, jira_url: str) -> str | None:
    """Resolve an attachment URL against JIRA_URL and check where it points.

    A value without scheme and host is resolved as a path below JIRA_URL
    (keeping a context path such as ``/jira``); any other value is resolved
    with ``urljoin``. The resolved URL is accepted only if it uses https and
    its host and port equal those of JIRA_URL, because the request carries
    the Jira credentials.

    Args:
        attachment_url: Absolute URL, path, or path relative to JIRA_URL
        jira_url: The configured JIRA_URL

    Returns:
        The resolved URL, or None if it must not be requested with credentials
    """
    if not isinstance(attachment_url, str) or not attachment_url.strip():
        return None
    base = jira_url.rstrip("/") + "/"
    try:
        parsed = urlparse(attachment_url)
        if not parsed.scheme and not parsed.netloc and not attachment_url.startswith("//"):
            resolved = urljoin(base, attachment_url.lstrip("/"))
        else:
            resolved = urljoin(base, attachment_url)
    except ValueError:
        # urllib rejects some malformed authorities (e.g. an invalid IPv6
        # literal) by raising; such a value is not requested.
        return None

    target = _https_origin(resolved)
    if target is None or target != _https_origin(jira_url):
        return None
    return resolved


def validate_attachment_url(attachment_url: str, jira_url: str) -> bool:
    """Return True if the attachment URL may be requested with Jira credentials."""
    return resolve_attachment_url(attachment_url, jira_url) is not None


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
        try:
            redirect_url = urljoin(url, response.headers["Location"])
        except ValueError as exc:
            raise DownloadError("unparsable redirect location") from exc
        # Follow only https redirects; the request below carries no credentials.
        if _https_origin(redirect_url) is None:
            raise DownloadError("refusing non-https redirect")
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
        if urlparse(attachment_url).scheme.lower() in ("http", "https"):
            config = load_config(env_file=ctx.obj["env_file"], profile=ctx.obj.get("profile"), url=attachment_url)
        else:
            config = load_config(env_file=ctx.obj["env_file"], profile=ctx.obj.get("profile"))
        jira_url = config["JIRA_URL"]

        # Credentials go only to the configured Jira host over https
        url = resolve_attachment_url(attachment_url, jira_url)
        if url is None:
            error(
                f"Attachment URL must resolve to an https URL on the JIRA_URL host "
                f"'{urlparse(jira_url).netloc}': {attachment_url}"
            )
            sys.exit(1)

        # Determine authentication method
        auth, headers = _build_auth(config)

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
            content_url = resolve_attachment_url(att.get("content"), jira_url)
            if content_url is None:
                warning(f"Skipping {filename}: content URL is not an https URL on the JIRA_URL host")
                continue

            try:
                _stream_to_path(content_url, jira_url, auth, headers, dest)
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
