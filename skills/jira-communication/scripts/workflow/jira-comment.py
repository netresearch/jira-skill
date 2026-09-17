#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "atlassian-python-api>=3.41.0,<4",
#     "click>=8.1.0,<9",
#     "requests>=2.31,<3",
# ]
# ///
"""Jira comment operations - add, edit, delete, and list issue comments."""

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
from lib.client import LazyJiraClient, _sanitize_error, fetch_comments_paginated
from lib.input import read_stdin_utf8
from lib.markup import escape_strikethrough, lint_ticket_language, lint_wiki_markup
from lib.output import error, extract_adf_text, format_output, success, warning
from lib.preview import preflight_render
from lib.users import check_mentions_cli, person_label


def _read_comment_text(comment_text: str, usage: str) -> str:
    """Return the comment body, reading stdin when the argument is ``-``.

    Extracted because `add` and `edit` carried a byte-identical copy of this
    apart from the usage line, and the pre-flight check pushed both functions
    past the cognitive-complexity gate.
    """
    if comment_text != "-":
        return comment_text

    if sys.stdin.isatty():
        error("'-' requires piped input but stdin is a terminal", suggestion=usage)
        sys.exit(1)

    max_size = 256 * 1024  # 256KB, above Jira's comment limit
    try:
        comment_text = read_stdin_utf8(max_size + 1)
    except UnicodeDecodeError:
        error(
            "stdin contains invalid text encoding (expected UTF-8)",
            suggestion="Ensure the piped file is valid UTF-8 text, not binary data.",
        )
        sys.exit(1)

    if len(comment_text) > max_size:
        error(
            f"stdin input exceeds maximum size ({max_size // 1024}KB)",
            suggestion="Jira comments have size limits. Consider attaching the content as a file.",
        )
        sys.exit(1)

    comment_text = comment_text.rstrip("\n")

    if not comment_text.strip():
        error(
            "No input received from stdin (empty or whitespace-only)",
            suggestion="Verify your piped command produces non-empty output.",
        )
        sys.exit(1)

    return comment_text


def _repair_markup(comment_text: str, auto_escape: bool) -> str:
    """Escape dashes Jira would render as strikethrough, and say what changed.

    This runs before the lint, and it is the reason the lint should now be
    quiet about dashes: a strikethrough span is not a judgement call, it is a
    mechanical defect with a mechanical repair. ``\\-`` prints as a plain
    hyphen, so the posted text reads exactly as written.

    Reporting the repair on stderr is deliberate - a silent rewrite of the
    user's text would be worse than the bug. ``--no-auto-escape`` turns it off -
    but not on its own: the lint and the render check each refuse the surviving
    span independently, so a deliberate strikethrough needs
    ``--no-auto-escape --force``.
    """
    if not auto_escape:
        return comment_text
    repaired = escape_strikethrough(comment_text)
    if repaired == comment_text:
        return comment_text
    changed = [
        (n, before, after)
        for n, (before, after) in enumerate(zip(comment_text.split("\n"), repaired.split("\n"), strict=True), 1)
        if before != after
    ]
    warning(
        f"auto-escaped {len(changed)} line(s) that Jira would have rendered struck through "
        f"(\\- prints as a plain hyphen; use --no-auto-escape to keep the markup as written)"
    )
    for n, _before, after in changed[:5]:
        warning(f"  line {n}: {after.strip()[:100]!r}")
    return repaired


def _check_rendering(
    comment_text: str,
    force: bool,
    issue_key: str | None,
    enabled: bool,
    env_file: str | None = None,
    profile: str | None = None,
) -> None:
    """Ask the instance how it will render this text, and refuse a mangled post.

    The lexical repair above handles what a model of the grammar CAN handle.
    This handles what it cannot, and the gap is not academic: Jira substitutes
    autolinked issue keys before text effects run, so
    ``{{OPS-899-Divergenzanalyse.pdf}}`` comes back with the key struck through
    on an instance where OPS-899 exists and clean on one where it does not.
    Escaping the dash does not help - measured - because the opener is
    positioned relative to the substituted link, not the source text. Asking
    the renderer is the only way to know, and it is one call.

    Advisory by construction. An unreachable, slow or absent renderer (the
    endpoint is Server/DC only) prints one warning and gets out of the way; it
    must never stop somebody posting a comment.
    """
    if not enabled:
        return

    verdict = preflight_render(comment_text, issue_key=issue_key, env_file=env_file, profile=profile)
    if not verdict.available:
        warning(f"render preview unavailable ({verdict.reason}) - relying on the local markup lint alone")
        return
    if not verdict.struck:
        return

    struck = "; ".join(repr(s[:80]) for s in verdict.struck[:3])
    if force:
        warning(f"rendering: Jira strikes through {struck}")
        return

    error(
        f"Jira renders part of this comment struck through: {struck}",
        suggestion=(
            "The local escape could not fix it - this usually means an autolinked issue key "
            "(a dash right after PROJ-123) or another macro creating the boundary. Rephrase, "
            "put the token in a {code} block, or re-run with --force to post it anyway."
        ),
    )
    sys.exit(1)


def _check_markup(comment_text: str, force: bool, issue_key: str | None = None) -> None:
    """Lint wiki markup and ticket language; abort on findings unless --force is given.

    The two kinds are labelled and explained separately: a language-only
    finding reported as a markup problem, with a suggestion about block tags,
    sends the reader looking for the wrong defect.
    """
    markup_findings = lint_wiki_markup(comment_text)
    language_findings = lint_ticket_language(comment_text, issue_key)
    if not markup_findings and not language_findings:
        return

    if force:
        for finding in markup_findings:
            warning(f"markup: {finding}")
        for finding in language_findings:
            warning(f"language: {finding}")
        return

    labelled = [f"markup: {f}" for f in markup_findings] + [f"language: {f}" for f in language_findings]
    hints = []
    if markup_findings:
        hints.append("Block tags are never inline; escape literal mentions as \\{code\\}.")
    if language_findings:
        hints.append("Re-resolve the language for this ticket; quoted user content stays verbatim.")
    hints.append("Re-run with --force to post anyway.")

    error("Comment lint found problems:\n  " + "\n  ".join(labelled), suggestion=" ".join(hints))
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════════════
# CLI Definition
# ═══════════════════════════════════════════════════════════════════════════════


# Backwards-compat alias for any external imports — implementation moved to lib.client.
_fetch_comments_paginated = fetch_comments_paginated


@click.group()
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option("--quiet", "-q", is_flag=True, help="Minimal output")
@click.option("--env-file", type=click.Path(), help="Environment file path")
@click.option("--profile", "-P", help="Jira profile name from ~/.jira/profiles.json")
@click.option("--debug", is_flag=True, help="Show debug information on errors")
@click.pass_context
def cli(ctx, output_json: bool, quiet: bool, env_file: str | None, profile: str | None, debug: bool):
    """Jira comment operations.

    Add, edit, delete, and list comments on Jira issues.
    Note: Comments should use Jira wiki markup syntax, not Markdown.
    """
    ctx.ensure_object(dict)
    ctx.obj["json"] = output_json
    ctx.obj["quiet"] = quiet
    ctx.obj["debug"] = debug
    ctx.obj["client"] = LazyJiraClient(env_file=env_file, profile=profile)
    # Kept so the render pre-flight resolves the SAME instance the write goes
    # to. Without them it falls back to ~/.env.jira, which under --profile is
    # either absent (silently degraded forever) or a DIFFERENT Jira - and a
    # clean preview from the wrong instance reads as a clean bill of health.
    ctx.obj["env_file"] = env_file
    ctx.obj["profile"] = profile


@cli.command()
@click.argument("issue_key")
@click.argument("comment_text")
@click.option("--force", is_flag=True, help="Post despite wiki-markup lint findings or a struck-through render preview")
@click.option(
    "--no-auto-escape",
    is_flag=True,
    help="Do not escape dashes Jira would render as strikethrough; add --force to actually post the span",
)
@click.option(
    "--no-preflight",
    is_flag=True,
    help="Skip the render-preview check against the Jira instance before posting",
)
@click.option("--no-verify-mentions", is_flag=True, help="Skip [~username] mention verification")
@click.pass_context
def add(
    ctx,
    issue_key: str,
    comment_text: str,
    force: bool,
    no_auto_escape: bool,
    no_preflight: bool,
    no_verify_mentions: bool,
):
    """Add a comment to an issue.

    ISSUE_KEY: The Jira issue key (e.g., PROJ-123)

    COMMENT_TEXT: Comment text (use Jira wiki markup, not Markdown).
    Use "-" to read from stdin (e.g., cat file.txt | jira-comment add PROJ-123 -)

    Note: Use Jira wiki syntax:
      - *bold* not **bold**
      - _italic_ not *italic*
      - {code}...{code} blocks for multi-line code, {{monospace}} for inline
      - [link text|url] for links, [^file.log] for attachments

    Block tags ({code}, {noformat}, {quote}, {panel}) must stand alone on
    their own line; literal mentions in prose must be escaped (\\{code\\}).

    Dashes Jira would render as a strikethrough span (``{{mono}}-Word ... zu-``)
    are escaped automatically before posting and reported on stderr; ``\\-``
    prints as a plain hyphen. --no-auto-escape keeps the markup verbatim; a
    deliberate strikethrough also needs --force, because the lint and the render
    check each still refuse the span.
    The comment is linted for this before posting (override with --force).

    [~username] mentions are verified against Jira before posting, so no
    separate user lookup is needed; an unknown username aborts with
    suggestions (skip with --no-verify-mentions).

    Examples:

      jira-comment add PROJ-123 "Fixed in commit abc123"

      jira-comment add PROJ-123 "See {{config.py}} for details"

      jira-comment add PROJ-123 "[~jane.doe] please review"

      cat comment.txt | jira-comment add PROJ-123 -
    """
    ctx.obj["client"].with_context(issue_key=issue_key)
    client = ctx.obj["client"]

    comment_text = _read_comment_text(comment_text, "Usage: cat comment.txt | jira-comment add PROJ-123 -")

    comment_text = _repair_markup(comment_text, auto_escape=not no_auto_escape)
    _check_markup(comment_text, force, issue_key)
    _check_rendering(
        comment_text,
        force,
        issue_key,
        enabled=not no_preflight,
        env_file=ctx.obj.get("env_file"),
        profile=ctx.obj.get("profile"),
    )
    check_mentions_cli(client, comment_text, skip=no_verify_mentions)

    try:
        result = client.issue_add_comment(issue_key, comment_text)

        if ctx.obj["quiet"]:
            print(result.get("id", "ok"))
        elif ctx.obj["json"]:
            format_output(result, as_json=True)
        else:
            success(f"Added comment to {issue_key}")
            print(f"  Comment ID: {result.get('id', 'N/A')}")

    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to add comment to {issue_key}: {_sanitize_error(str(e))}")
        sys.exit(1)


@cli.command()
@click.argument("issue_key")
@click.argument("comment_id")
@click.argument("comment_text")
@click.option("--force", is_flag=True, help="Post despite wiki-markup lint findings or a struck-through render preview")
@click.option(
    "--no-auto-escape",
    is_flag=True,
    help="Do not escape dashes Jira would render as strikethrough; add --force to actually post the span",
)
@click.option(
    "--no-preflight",
    is_flag=True,
    help="Skip the render-preview check against the Jira instance before posting",
)
@click.option("--no-verify-mentions", is_flag=True, help="Skip [~username] mention verification")
@click.pass_context
def edit(
    ctx,
    issue_key: str,
    comment_id: str,
    comment_text: str,
    force: bool,
    no_auto_escape: bool,
    no_preflight: bool,
    no_verify_mentions: bool,
):
    """Edit an existing comment on an issue.

    ISSUE_KEY: The Jira issue key (e.g., PROJ-123)

    COMMENT_ID: The ID of the comment to edit (use 'list' to find IDs)

    COMMENT_TEXT: New comment text (use Jira wiki markup, not Markdown).
    Use "-" to read from stdin (e.g., cat file.txt | jira-comment edit PROJ-123 12345 -).
    Linted for wiki-markup problems before posting (override with --force).

    Examples:

      jira-comment edit PROJ-123 12345 "Updated: fixed in commit abc123"

      jira-comment edit PROJ-123 12345 "h3. Findings\\n\\nUpdated analysis"

      cat comment.txt | jira-comment edit PROJ-123 12345 -
    """
    ctx.obj["client"].with_context(issue_key=issue_key)
    client = ctx.obj["client"]

    comment_text = _read_comment_text(comment_text, "Usage: cat comment.txt | jira-comment edit PROJ-123 12345 -")

    comment_text = _repair_markup(comment_text, auto_escape=not no_auto_escape)
    _check_markup(comment_text, force, issue_key)
    _check_rendering(
        comment_text,
        force,
        issue_key,
        enabled=not no_preflight,
        env_file=ctx.obj.get("env_file"),
        profile=ctx.obj.get("profile"),
    )
    check_mentions_cli(client, comment_text, skip=no_verify_mentions)

    try:
        result = client.issue_edit_comment(issue_key, comment_id, comment_text)

        if ctx.obj["quiet"]:
            if isinstance(result, dict):
                print(result.get("id", "ok"))
            else:
                print("ok")
        elif ctx.obj["json"]:
            format_output(result, as_json=True)
        else:
            success(f"Updated comment {comment_id} on {issue_key}")

    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to edit comment {comment_id} on {issue_key}: {_sanitize_error(str(e))}")
        sys.exit(1)


@cli.command()
@click.argument("issue_key")
@click.argument("comment_id")
@click.option("--dry-run", is_flag=True, help="Show what would be deleted without making changes")
@click.pass_context
def delete(ctx, issue_key: str, comment_id: str, dry_run: bool):
    """Delete a comment from an issue.

    Non-interactive: there is no confirmation prompt, the comment is deleted
    on the spot. Preview with --dry-run; no stdin is read.

    ISSUE_KEY: The Jira issue key (e.g., PROJ-123)

    COMMENT_ID: The ID of the comment to delete (use 'list' to find IDs)

    Examples:

      jira-comment delete PROJ-123 12345

      jira-comment delete PROJ-123 12345 --dry-run
    """
    ctx.obj["client"].with_context(issue_key=issue_key)
    client = ctx.obj["client"]

    if dry_run:
        warning("DRY RUN - No comment will be deleted")
        print(f"\nWould delete comment {comment_id} from {issue_key}")
        return

    try:
        url = f"rest/api/2/issue/{issue_key}/comment/{comment_id}"
        client.delete(url)

        if ctx.obj["quiet"]:
            print("ok")
        elif ctx.obj["json"]:
            format_output({"issue_key": issue_key, "comment_id": comment_id, "deleted": True}, as_json=True)
        else:
            success(f"Deleted comment {comment_id} from {issue_key}")

    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to delete comment {comment_id} from {issue_key}: {_sanitize_error(str(e))}")
        sys.exit(1)


@cli.command("list")
@click.argument("issue_key")
@click.option(
    "--limit",
    "-n",
    default=10,
    show_default=True,
    type=click.IntRange(min=0),
    help="Max comments to show (0 = all)",
)
@click.option("--truncate", type=int, metavar="N", help="Truncate comment body to N characters")
@click.pass_context
def list_comments(ctx, issue_key: str, limit: int, truncate: int | None):
    """List comments on an issue.

    ISSUE_KEY: The Jira issue key (e.g., PROJ-123)

    Examples:

      jira-comment list PROJ-123

      jira-comment list PROJ-123 --limit 5 --json
    """
    ctx.obj["client"].with_context(issue_key=issue_key)
    client = ctx.obj["client"]

    try:
        show_all = limit == 0
        if show_all:
            comments, total = _fetch_comments_paginated(client, issue_key)
        else:
            issue = client.issue(issue_key, fields="comment")
            comment_block = (issue.get("fields") or {}).get("comment") or {}
            comments = comment_block.get("comments", []) or []
            total = comment_block.get("total")

        # Limit and reverse (newest first)
        comments = list(reversed(comments))
        shown = comments if show_all else comments[:limit]

        # The truncation notice belongs on stderr, in every output mode. On
        # stdout it is part of the payload: a caller that pipes the table
        # through grep, or parses --json, drops the one line saying the history
        # is incomplete and reads 10 of 163 comments as the whole record. That
        # happened -- a ticket was reported as carrying no "ready for QA"
        # comment when it did, because the read was cut and the cut was
        # invisible. stderr survives the pipe; stdout does not.
        truncated = total is not None and not show_all and len(shown) < total
        if truncated:
            warning(f"{issue_key}: showing {len(shown)} of {total} comments — use --limit 0 for the full history")

        if ctx.obj["json"]:
            format_output(shown, as_json=True)
        elif ctx.obj["quiet"]:
            for c in shown:
                print(c.get("id", ""))
        else:
            if not shown:
                print(f"No comments on {issue_key}")
            else:
                if truncated:
                    print(f"Comments on {issue_key} ({len(shown)} of {total} shown — use --limit 0 to show all):\n")
                else:
                    print(f"Comments on {issue_key} ({len(shown)} shown):\n")
                for c in shown:
                    author = person_label(c.get("author"))
                    created = c.get("created", "")[:16].replace("T", " ") if c.get("created") else "N/A"
                    body = c.get("body", "")

                    # Handle ADF format
                    if isinstance(body, dict):
                        body = extract_adf_text(body)

                    # Truncate if requested
                    if truncate and len(body) > truncate:
                        body = body[: truncate - 3] + "..."

                    print("-" * 80)
                    print(f"[{created}] {author}:")
                    print()
                    for line in body.split("\n"):
                        print(line)
                    print()

    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to get comments for {issue_key}: {_sanitize_error(str(e))}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
