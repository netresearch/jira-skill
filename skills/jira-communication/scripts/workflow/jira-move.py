#!/usr/bin/env -S uv run --script
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "atlassian-python-api>=3.41.0,<4",
#     "click>=8.1.0,<9",
#     "requests>=2.31.0,<3",
# ]
# ///
"""Jira issue move - move issues between projects or change issue type."""

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
from lib.client import JIRA_TIMEOUT, AuthenticationError, LazyJiraClient, SessionExpiredError, _sanitize_error
from lib.output import error, format_output, success, warning

# ═══════════════════════════════════════════════════════════════════════════════
# Workflow guard
#
# Jira's REST edit endpoint accepts an issue-type change whose target type the
# project's workflow scheme maps to a different workflow, and does not migrate
# the issue's workflow entry the way the UI's Move does. The issue then keeps
# its old workflow while the scheme names another one; when that one lacks the
# current status, Jira's own Move refuses the issue afterwards ("incorrectly
# associated with the status") and add-ons that look up the step for the status
# fail on every view.
#
# The check before the change uses the scheme's view of the types. The check
# after it reads the issue's transitions, which come from the workflow the issue
# actually runs: on HMKG-2540 (2026-11-06) the issue, already a Technical task,
# was still moved through UAT Stage, Deploy to Prod and Closed, all statuses of
# the management workflow only.
# ═══════════════════════════════════════════════════════════════════════════════


def _statuses_by_type(client, project_key: str) -> dict[str, set[str]]:
    """Status names per issue type of the project (public endpoint)."""
    url = f"{client.url}/rest/api/2/project/{project_key}/statuses"
    response = client._session.get(url, timeout=JIRA_TIMEOUT)
    response.raise_for_status()
    return {t["name"]: {s["name"] for s in t.get("statuses", [])} for t in response.json()}


def _workflow_by_type(client, project_key: str) -> dict[str, str] | None:
    """Workflow name per issue type, or None when the caller cannot read the scheme.

    The project-configuration endpoint is internal to Jira Server/DC and needs
    project-admin rights; any failure means "unknown", never "same workflow".
    """
    url = f"{client.url}/rest/projectconfig/1/workflowscheme/{project_key}"
    try:
        response = client._session.get(url, timeout=JIRA_TIMEOUT)
        if response.status_code != 200:
            return None
        data = response.json()
        names = {t["id"]: t["name"] for t in data.get("issueTypes", [])}
        result: dict[str, str] = {}
        for mapping in data.get("mappings", []):
            for type_id in mapping.get("issueTypes", []):
                if type_id in names:
                    result[names[type_id]] = mapping["name"]
        return result or None
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return None


def _workflow_mismatch(
    client, project_key: str, statuses: dict[str, set[str]], current_type: str, target_type: str, status: str
) -> str | None:
    """Why a REST type change would leave the issue inconsistent, or None when it would not."""
    target_statuses = statuses.get(target_type)
    if target_statuses is None:
        return None  # unknown type: Jira's own 400 explains it
    if status not in target_statuses:
        return f"status '{status}' does not exist in the workflow of '{target_type}'"
    workflows = _workflow_by_type(client, project_key) or {}
    current_wf, target_wf = workflows.get(current_type), workflows.get(target_type)
    if current_wf and target_wf:
        if current_wf != target_wf:
            return f"'{current_type}' uses workflow '{current_wf}', '{target_type}' uses '{target_wf}'"
        return None
    # Scheme unreadable, or a type missing from it: two workflows with different
    # status sets are different workflows. Equal sets pass, which can still be
    # two workflows; only the scheme view tells them apart.
    if statuses.get(current_type, set()) != target_statuses:
        return f"'{current_type}' and '{target_type}' have different statuses, so they use different workflows"
    return None


def _offered_statuses(client, issue_key: str, status: str) -> set[str] | None:
    """The current status plus every transition target the issue offers now.

    All of them belong to the workflow the issue actually runs. A status outside
    a type's statuses means the issue does not run that type's workflow. None
    when the transitions cannot be read.
    """
    url = f"{client.url}/rest/api/2/issue/{issue_key}/transitions"
    try:
        response = client._session.get(url, timeout=JIRA_TIMEOUT)
        if response.status_code != 200:
            return None
        targets = {((t.get("to") or {}).get("name")) for t in response.json().get("transitions", [])}
    except (requests.RequestException, ValueError, AttributeError, TypeError):
        return None
    return {s for s in targets | {status} if s}


def _sorted_names(names: set[str]) -> str:
    return ", ".join(repr(s) for s in sorted(names))


# ═══════════════════════════════════════════════════════════════════════════════
# CLI Definition
# ═══════════════════════════════════════════════════════════════════════════════


@click.group()
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option("--quiet", "-q", is_flag=True, help="Minimal output (just new issue key)")
@click.option("--env-file", type=click.Path(), help="Environment file path")
@click.option("--profile", "-P", help="Jira profile name from ~/.jira/profiles.json")
@click.option("--debug", is_flag=True, help="Show debug information on errors")
@click.pass_context
def cli(ctx, output_json: bool, quiet: bool, env_file: str | None, profile: str | None, debug: bool):
    """Jira issue move.

    Change issue type within the same project.

    Cross-project moves are intentionally refused by this command because
    they are not safely supported via the standard issue edit endpoint
    (some Jira versions ignore project changes without error).
    """
    ctx.ensure_object(dict)
    ctx.obj["json"] = output_json
    ctx.obj["quiet"] = quiet
    ctx.obj["debug"] = debug
    ctx.obj["client"] = LazyJiraClient(env_file=env_file, profile=profile)


@cli.command("issue")
@click.argument("issue_key")
@click.argument("target_project")
@click.option("--issue-type", "-t", help="Issue type in target project (default: keep current)")
@click.option("--dry-run", is_flag=True, help="Show what would happen without making changes")
@click.pass_context
def move_issue(ctx, issue_key: str, target_project: str, issue_type: str | None, dry_run: bool):
    """Change an issue's type within the same project.

    ISSUE_KEY: The Jira issue key to move (e.g., NRS-4301)

    TARGET_PROJECT: Target project key (e.g., SRVUC). Use the same project key
    to change issue type. Cross-project moves are refused.

    Examples:

      jira-move issue NRS-4301 PROJ --issue-type Task  (change type, same project)

      jira-move issue NRS-4301 NRS --issue-type Task --dry-run
    """
    ctx.obj["client"].with_context(issue_key=issue_key)
    client = ctx.obj["client"]

    try:
        # Fetch current issue details
        issue = client.issue(issue_key, fields="summary,issuetype,status,project")
        fields = issue["fields"]
        current_project = fields["project"]["key"]
        current_type = fields["issuetype"]["name"]
        summary = fields["summary"]
        status = fields["status"]["name"]

        same_project = current_project.upper() == target_project.upper()

        if same_project and not issue_type:
            error(f"{issue_key} is already in project {target_project} (use --issue-type to change type)")
            sys.exit(1)

        target_type = issue_type or current_type

        if same_project and target_type == current_type:
            error(f"{issue_key} is already type {current_type} in project {target_project}")
            sys.exit(1)

        # IMPORTANT: Cross-project moves are NOT safely supported via the standard
        # issue edit endpoint. Refuse even for --dry-run so we never preview an
        # operation this command will not execute.
        if not same_project:
            error(
                "Cross-project move is not supported safely by this command yet. "
                "Refusing to proceed to avoid partial moves. "
                "Use the Jira UI Move action (or implement bulk move API support)."
            )
            sys.exit(1)

        # Refuse a change the REST edit cannot carry out correctly (see "Workflow guard").
        statuses = _statuses_by_type(client, current_project)
        # Jira matches type names case-insensitively in places; the checks below
        # look them up by the project's own spelling.
        target_type = next((n for n in statuses if n.casefold() == target_type.casefold()), target_type)
        if target_type == current_type:
            error(f"{issue_key} is already type {current_type} in project {target_project}")
            sys.exit(1)
        # An issue that already runs another workflow than its type's (an earlier
        # REST change) shows it in its transitions. Setting the type of that
        # workflow is the repair; any other change is refused.
        offered = _offered_statuses(client, issue_key, status)
        current_statuses, target_statuses = statuses.get(current_type), statuses.get(target_type)
        stray = offered - current_statuses if offered is not None and current_statuses is not None else set()
        repair = bool(stray) and target_statuses is not None and offered <= target_statuses
        if stray and not repair:
            error(
                f"Refusing to change {issue_key}: it already runs another workflow than the one of "
                f"{current_type} (it offers {_sorted_names(stray)}, which that workflow does not have).",
                suggestion=(
                    "Change it to the type whose workflow it runs, or walk its transitions to a status "
                    "both workflows have and then use the Jira UI's 'Move' action, which migrates the "
                    "workflow. Jira's Move refuses such an issue while it sits in a status the scheme's "
                    "workflow lacks."
                ),
            )
            sys.exit(1)
        if repair:
            warning(
                f"{issue_key} runs another workflow than the one of {current_type} (it offers "
                f"{_sorted_names(stray)}); {target_type} has all its statuses, so the change repairs it."
            )
        mismatch = (
            None if repair else _workflow_mismatch(client, current_project, statuses, current_type, target_type, status)
        )
        if mismatch:
            error(
                f"Refusing to change {issue_key} from {current_type} to {target_type}: {mismatch}.",
                suggestion=(
                    "Jira's REST edit changes the type without migrating the issue's workflow, which "
                    "leaves the issue on the old workflow. Use the Jira UI's 'Move' action, which maps "
                    "the status to the new workflow."
                ),
            )
            sys.exit(1)

        # Dry run (same project only — cross-project moves are refused above)
        if dry_run:
            warning("DRY RUN - No changes will be made")
            print(f"\nWould change type of {issue_key}:")
            print(f"  Summary:  {summary}")
            print(f"  From:     {current_type}")
            print(f"  To:       {target_type}")
            print(f"  Status:   {status}")
            return

        # Use the REST API directly — atlassian-python-api doesn't have a move method.
        #
        # IMPORTANT: Cross-project moves are NOT safely supported via the standard
        # issue edit endpoint. Some Jira Server/DC versions silently ignore
        # `project` updates, which looks like success but leaves the issue in the
        # old project with a changed issue type (data corruption).
        # PUT /rest/api/2/issue/{issueKey} with issuetype change (same project)
        update_fields = {"fields": {"issuetype": {"name": target_type}}}

        url = f"{client.url}/rest/api/2/issue/{issue_key}"
        # atlassian-python-api has no public method for issue move/edit.
        # Using _session directly is intentional; version range (>=3.41.0,<4) in
        # PEP 723 header guards against breaking changes across major versions.
        response = client._session.put(url, json=update_fields, timeout=JIRA_TIMEOUT)

        if response.status_code == 204:
            # Verify the update actually applied (defense against silent failures)
            refreshed = client.issue(issue_key, fields="issuetype,project,status")
            refreshed_fields = refreshed.get("fields") or {}
            refreshed_type = (refreshed_fields.get("issuetype") or {}).get("name")
            refreshed_project = (refreshed_fields.get("project") or {}).get("key")
            if refreshed_project and refreshed_project.upper() != current_project.upper():
                error(
                    f"Move verification failed: issue ended up in unexpected project "
                    f"{refreshed_project} (expected {current_project})"
                )
                sys.exit(1)
            if refreshed_type and refreshed_type != target_type:
                error(
                    f"Type change {current_type} → {target_type} was rejected by Jira's REST "
                    f"edit endpoint: {issue_key} is still type {refreshed_type}.",
                    suggestion=(
                        "Jira's edit endpoint silently refuses some issue-type conversions — "
                        "notably between Sub-Task types (e.g. Sub: Task → Sub: Bug) and between "
                        "Sub-Task and standard types. No payload variation makes it work via "
                        "REST. Use the Jira UI's 'Move' action on the issue instead."
                    ),
                )
                sys.exit(1)
            # After the change: the issue must run the new type's workflow. Its
            # transitions come from the workflow it actually runs; a target the
            # new type's workflow lacks means the old workflow stayed. Then put
            # the old type back and fail.
            refreshed_status = (refreshed_fields.get("status") or {}).get("name") or status
            new_statuses = statuses.get(target_type)
            after = _offered_statuses(client, issue_key, refreshed_status)
            foreign = after - new_statuses if after is not None and new_statuses is not None else None
            if foreign is None:
                warning(
                    f"Could not verify that {issue_key} runs the workflow of {target_type} "
                    "(transitions or statuses unreadable)."
                )
            elif foreign:
                try:
                    rollback = client._session.put(
                        url, json={"fields": {"issuetype": {"name": current_type}}}, timeout=JIRA_TIMEOUT
                    )
                    restored = (client.issue(issue_key, fields="issuetype").get("fields") or {}).get("issuetype") or {}
                    restored_ok = rollback.status_code == 204 and restored.get("name") == current_type
                    failure = f"HTTP {rollback.status_code}, type now {restored.get('name')}"
                except Exception as exc:  # the change stands; report it, not a generic "failed to move"
                    restored_ok = False
                    failure = _sanitize_error(str(exc))
                error(
                    f"{issue_key} does not run the workflow of {target_type}: it offers "
                    f"{_sorted_names(foreign)}, which that workflow does not have. "
                    + (
                        f"The type was set back to {current_type}."
                        if restored_ok
                        else f"Setting the type back to {current_type} FAILED ({failure}); "
                        f"{issue_key} may still be {target_type} on the old workflow, fix it in the Jira UI."
                    ),
                    suggestion="Use the Jira UI's 'Move' action, which maps the status to the new workflow.",
                )
                sys.exit(1)
            # Type change within same project — key stays the same
            if ctx.obj["quiet"]:
                print(issue_key)
            elif ctx.obj["json"]:
                format_output(
                    {
                        "key": issue_key,
                        "old_type": current_type,
                        "new_type": target_type,
                        "project": current_project,
                        "summary": summary,
                    },
                    as_json=True,
                )
            else:
                success(f"Changed {issue_key} type: {current_type} → {target_type}")
                print(f"  Summary:    {summary}")
        elif response.status_code == 400:
            # Common: issue type not available in target project
            detail = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            errors = detail.get("errors", {})
            error_msgs = detail.get("errorMessages", [])
            msg = "; ".join(error_msgs) if error_msgs else "; ".join(f"{k}: {v}" for k, v in errors.items())
            error(f"Cannot move {issue_key} to {target_project}: {msg}")
            if "issuetype" in str(errors).lower() or "issue type" in msg.lower():
                print("\nHint: Use --issue-type to specify a valid type in the target project")
            sys.exit(1)
        else:
            response.raise_for_status()

    except SessionExpiredError as e:
        if ctx.obj["debug"]:
            raise
        error(str(e))
        sys.exit(1)
    except AuthenticationError as e:
        if ctx.obj["debug"]:
            raise
        error(str(e))
        sys.exit(1)
    except requests.HTTPError as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to move {issue_key}: {_sanitize_error(str(e))}")
        sys.exit(1)
    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to move {issue_key}: {_sanitize_error(str(e))}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
