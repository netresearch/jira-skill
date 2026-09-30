<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
<!-- SPDX-FileCopyrightText: Netresearch DTT GmbH -->

# Security assurance case — jira-skill

This document states what a user can expect from this repository in terms of security, and argues why that expectation holds. Every claim names the file that implements it; paths starting with `lib/`, `core/`, `workflow/` or `utility/` are under `skills/jira-communication/scripts/`. Reporting a vulnerability: see the [security policy](https://github.com/netresearch/.github/blob/main/SECURITY.md).

## What the repository ships

| Part | Files | Runs where |
| --- | --- | --- |
| Skill instructions for an AI agent | `skills/*/SKILL.md`, `skills/*/references/*.md` | Read by the agent as instructions; not executed. |
| Jira CLI scripts | `core/*.py`, `workflow/*.py`, `utility/*.py`, shared code in `lib/*.py` | On the user's machine through `uv run`, with the user's Jira credentials, against the Jira instance the user configured. |
| Prompt hook | `hooks/hooks.json`, `scripts/detect_jira_issues.py` | On the user's machine as a Claude Code `UserPromptSubmit` hook on every prompt, when the skill is installed as a plugin. |
| Wiki markup validator | `skills/jira-syntax/scripts/validate-jira-syntax.sh` | On the user's machine; reads text from a file or stdin and prints findings. It makes no network request. |
| Templates | `skills/jira-syntax/templates/*.md` | Text the user or the agent copies into Jira tickets. |
| Maintainer tools | `scripts/generate-strikethrough-corpus.py`, `scripts/verify-render-oracle.py`, `scripts/verify-harness.sh`, `evals/run-evals.sh`, `Build/` | On maintainers' machines and in this repository's CI. |

The repository ships no server component and no container image. It keeps no data of its own beyond the credential files the setup script writes and the attachments a user downloads. The only secrets it handles are the user's Jira credentials, described in the next section.

## Credentials: where they are read and where they go

- **Sources.** `lib/config.py` resolves one configuration per call, in this order (`load_config`): a file given with `--env-file`; otherwise, if `~/.jira/profiles.json` exists, one profile from it (`resolve_profile`: the `--profile` name, the host of a Jira URL, the project prefix of an issue key, a `.jira-profile` file in the current directory that names a profile, or the file's `default`); otherwise `~/.env.jira`. An env file is parsed as `KEY=VALUE` lines (`load_env`); it is read as text and never executed. Environment variables fill values the file does not set.
- **Kinds.** Server/Data Center uses a personal access token (`JIRA_PERSONAL_TOKEN`, profile field `token`); Cloud uses an account name and API token (`JIRA_USERNAME`, `JIRA_API_TOKEN`). `validate_config` refuses to build a client without one of the two.
- **Storage.** `core/jira-setup.py` writes both files with `os.open(…, 0o600)` followed by `os.chmod(…, 0o600)` (`write_env_file`, `write_profile`), and prompts for tokens with `hide_input=True`. The files hold the tokens in clear text, like `~/.netrc`; the docstring of `write_env_file` records this as a design choice. Tests: `tests/test_jira_setup.py`.
- **Destinations.** The scripts build their request URLs from the configured `JIRA_URL` and attach the credentials to those requests: through the `atlassian-python-api` client built in `lib/client.py` (`get_jira_client`, token as Bearer, Cloud as HTTP basic auth), through that client's session for the Tempo and move endpoints and attachment uploads (`utility/jira-worklog-query.py`, `workflow/jira-move.py`, `core/jira-attachment.py add`), to the Server/DC render endpoint `/rest/api/1.0/render` (`lib/preview.py`), for attachment downloads (`core/jira-attachment.py`, `_build_auth`), and, during setup, to the URL being configured, where `core/jira-setup.py` (`validate_credentials`) builds its own client and calls `myself()`. The reachability checks in `core/jira-setup.py` (`validate_url`: `HEAD`, or `GET` when the server answers 405) and `core/jira-validate.py` (`HEAD`) send no credentials. The prompt hook reads `~/.jira/profiles.json` only to print a profile name; it prints no URL or token and makes no request (`scripts/detect_jira_issues.py`, `resolve_profile_suggestion`).
- **Error output.** The scripts put credentials only into the `Authorization` header (Bearer token or HTTP basic auth), never into a URL or a request body, so the request URLs that error messages quote carry no credential. In addition, the connection error of `get_jira_client`, the error paths of `core/jira-setup.py`, the download and upload errors of `core/jira-attachment.py`, and part of the error paths of other scripts pass through `_sanitize_error` (`lib/errors.py`), which replaces the value after `Authorization:`, `Bearer`, `Basic` and `token=`/`password=`-style keys with `***`. Tests: `tests/test_client.py` (`test_redacts_*`), `tests/test_jira_setup.py` (`test_token_in_exception_is_redacted`).

## Security requirements

1. Jira credentials are read only from the user's own configuration (`--env-file`, `~/.jira/profiles.json`, `~/.env.jira`, `JIRA_*` environment variables).
2. Credential files written by the setup script are readable by their owner only.
3. Credentials travel only in the `Authorization` header, never in a URL, request body or log line the scripts write.
4. The destructive commands (delete, remove, issue update and move) can be previewed with `--dry-run` before they change Jira data.
5. Data returned by Jira is treated as data: it is printed or saved, never executed.
6. Nothing committed to this repository contains a secret.

## Actors and trust boundaries

- **User and agent.** The agent reads the skill and runs the scripts. What it runs, and against which ticket, is decided by the agent and the user. `allowed-tools` in `skills/jira-communication/SKILL.md` only pre-approves running the scripts and `Read`/`Write`; it does not take any tool away from the agent.
- **Configuration.** `~/.env.jira`, `~/.jira/profiles.json`, `--env-file` and the `JIRA_*` environment variables are trusted: whoever controls them chooses the Jira URL the credentials go to. A `.jira-profile` file in the current directory can only select one of the user's existing profiles by name (`resolve_profile`, step 4); it cannot add a URL or a credential.
- **Jira instance.** The configured Jira server is trusted with the credentials. Its responses cross back into the scripts as data: issue fields, comments and attachment names are parsed and printed, and attachment file names are reduced to their last path component before they are used (`core/jira-attachment.py`, `download_all`).
- **Hook payload.** Claude Code passes the prompt to `scripts/detect_jira_issues.py` as JSON on stdin. The hook only extracts strings matching `[A-Z][A-Z0-9_]+-\d+` and Jira host names by regular expression and prints a reminder with the matched keys; it runs under a 3-second timeout (`hooks/hooks.json`).
- **Contributors and CI.** Changes reach `main` through pull requests checked by `.github/workflows/`. Workflows start from `permissions: {}` or `contents: read` and grant each job the scopes its reusable workflow needs. The two `pull_request_target` workflows (`auto-merge-deps.yml`, `labeler.yml`) call reusables that merge or label and do not check out pull request code; `auto-merge-deps.yml` passes two named secrets instead of `secrets: inherit`.

## Threats and countermeasures

| Threat | Countermeasure | Evidence |
| --- | --- | --- |
| Jira Cloud answers an attachment download with a redirect to its storage host | Exactly one redirect is followed, without credentials; a further redirect is an error, so a redirect body is never saved as the file | `core/jira-attachment.py` (`_stream_to_path`); `tests/test_attachment_security.py` |
| A download writes outside the intended directory (CWE-22) | Output paths and the `--dir` of `download-all` are resolved and must stay inside the current directory; Jira-supplied file names lose their path components; duplicate names are disambiguated instead of overwritten | `core/jira-attachment.py` (`validate_output_path`, `download_all`); `tests/test_attachment_security.py` |
| A login or session-expiry page is taken for real data | Every response through the patched client session is checked: a CAPTCHA challenge, HTTP 401/403, and a `200` HTML page without an attachment disposition each raise a typed error | `lib/client.py` (`_handle_response`, `_patch_session_for_response_validation`); `tests/test_attachment_security.py`, `tests/test_client.py` |
| A CAPTCHA response sends the user to a foreign login page | The login URL from the `X-Authentication-Denied-Reason` header is used only if its host equals the configured Jira host | `lib/client.py` (`_check_captcha_challenge`); `tests/test_client.py` |
| A host name such as `atlassian.net.example.com` is taken for Jira Cloud | Cloud is detected only for `atlassian.net` or a name ending in `.atlassian.net` | `lib/config.py` (`is_cloud_url`); `tests/test_config.py` |
| Credentials leak through an error message (CWE-532) | Credentials are never part of a URL; `_sanitize_error` additionally redacts authorization headers and token-style parameters in the error paths that call it | `lib/client.py` (`get_jira_client`), `core/jira-attachment.py` (`_build_auth`), `lib/preview.py`, `lib/errors.py`; `tests/test_client.py`, `tests/test_jira_setup.py` |
| Credential files are readable by other local users (CWE-732) | Created with mode `0600` from the first write, then `chmod 0600` | `core/jira-setup.py`; `tests/test_jira_setup.py` |
| A user value breaks out of a JQL string literal | Values placed inside quoted JQL strings are escaped (`\` and `"`) | `lib/jql.py` (`jql_escape`), used by `utility/jira-qa-gather.py` and `utility/jira-worklog-query.py` |
| A request hangs indefinitely | Calls through the Jira client use a 30-second timeout (`JIRA_TIMEOUT`), and the direct session calls pass their own (`workflow/jira-move.py`, `utility/jira-worklog-query.py`); downloads and uploads use `(10, 300)` seconds; rate-limit and gateway errors (429, 502, 503, 504) are retried three times with backoff, for the methods urllib3 retries by default (not `POST`) | `lib/client.py`, `core/jira-attachment.py`; `tests/test_client.py`, `tests/test_move.py` |
| An unintended destructive change in Jira | Every delete and remove command, `core/jira-issue.py update` and `workflow/jira-move.py` accept `--dry-run`; the read-only scripts (`core/jira-search.py`, `workflow/jira-board.py`, `workflow/jira-sprint.py`, `utility/jira-fields.py`, `utility/jira-user.py`, `utility/jira-qa-gather.py`) have no write command | the scripts named; `skills/jira-communication/AGENTS.md` |
| Piped text is mis-decoded and stored garbled | stdin is decoded as UTF-8 regardless of the host code page, with a character cap where callers set one | `lib/input.py` (`read_stdin_utf8`); `tests/test_input.py` |
| A secret is committed | Betterleaks scans every push to `main` and every pull request to `main` | `.github/workflows/security.yml` |
| A vulnerable dependency is used | Python dependencies are declared per script with upper bounds (PEP 723 blocks, for example `atlassian-python-api>=3.41.0,<4`) and audited weekly with pip-audit; dependency review and Composer Audit run on pull requests | script headers; `.github/workflows/dependency-audit.yml`, `.github/workflows/security.yml` |
| Insecure code or workflow patterns | CodeQL (`actions`, `python`), bandit at severity medium, Opengrep, zizmor, ruff and ShellCheck (style severity in `validate.yml`) run on pull requests | `.github/workflows/codeql.yml`, `ci.yml`, `security.yml`, `validate.yml`, `lint.yml` |
| A script regresses unnoticed | The pytest suite in `tests/` runs on Python 3.10 to 3.14 for every pull request to `main` and every push to `main`, with the Jira client mocked | `.github/workflows/ci.yml`, `tests/conftest.py` |
| A release archive is tampered with | The release workflow publishes `SHA256SUMS.txt` with a Sigstore signature and build-provenance attestations; the documented release process cuts releases from signed annotated tags | `.github/workflows/release.yml`; `AGENTS.md` (Release workflow) |

Which of these checks must pass before a pull request can merge is set in the branch protection of `main`, not in this repository.

## Secure design principles applied

- **Least privilege:** scripts use the permissions of the token the user configured and nothing else; workflows start from explicit `permissions`.
- **Fail-safe defaults:** a missing credential stops the client from being built (`validate_config`); an unknown `--profile` name or an ambiguous project prefix is an error, not a guess (`resolve_profile`); unexpected redirects and HTML login pages are errors (`_stream_to_path`, `_handle_response`).
- **Complete mediation:** response validation is installed on the client session once, so every request made through the client passes the same checks (`_patch_session_for_response_validation`).
- **Economy of mechanism:** three runtime dependencies (`atlassian-python-api`, `click`, `requests`), resolved by `uv` from each script's PEP 723 block; the hook uses the Python standard library only.

## What a user cannot expect

- The configuration is trusted. A `JIRA_URL` starting with `http://` passes `validate_config`, and the credentials then travel unencrypted. Whoever can edit the configuration files or the `JIRA_*` environment variables can redirect the credentials.
- `download-all` downloads the `content` URL that the Jira server lists for each attachment; the server is trusted to list its own URLs.
- `--debug` re-raises the original exception without `_sanitize_error`, and several scripts (for example `core/jira-search.py`, `core/jira-worklog.py`, `workflow/jira-transition.py`) print exception text unfiltered. `_sanitize_error` matches known key names; a credential in an unexpected format is not recognised.
- Content returned from Jira (descriptions, comments, attachment names) is printed to the agent unchanged. Ticket text can contain instructions aimed at the agent; the scripts do not detect or remove them.
- `--dry-run` is opt-in. Commands such as `core/jira-issue.py delete` act without an interactive confirmation, and commands that add content (`workflow/jira-comment.py add`, `core/jira-worklog.py add`, `utility/jira-watchers.py add`) have no `--dry-run`.
- The skill gives guidance; the agent runs the scripts with the user's token, and a token with the necessary rights can do anything the scripts offer. Review what an agent proposes to write.
- Security fixes follow the supported-versions rules of the organisation's security policy; older releases may not receive them.
