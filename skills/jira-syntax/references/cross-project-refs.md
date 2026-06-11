# Cross-Project References to GitLab Resources

When referencing GitLab merge requests, issues, tags, or commits **from a Jira description, comment, or worklog**, prefer the GitLab cross-project autolink syntax — even though Jira itself doesn't autolink GitLab paths, the cross-project form removes ambiguity for human readers and matches the convention used in GitLab itself.

## Convention

| GitLab resource | Short form (single-project context) | Cross-project form (use this in Jira) |
|---|---|---|
| Merge request | `!42` | `group/project!42` |
| Issue | `#123` | `group/project#123` |
| Tag / commit / branch | `vX.Y.Z` | `group/project@vX.Y.Z` |

The same prefix characters (`!`, `#`, `@`) are what GitLab itself recognises for cross-project autolinks in markdown, commit messages, and MR descriptions — so a reader who pastes the reference into a GitLab UI will get a working link automatically.

## In Jira wiki markup

Wrap the cross-project text inside the standard Jira link syntax `[text|url]`:

```
[jira/jira!25|https://git.netresearch.de/jira/jira/-/merge_requests/25]
[jira/jira@v9.12.3-2|https://git.netresearch.de/jira/jira/-/tags/v9.12.3-2]
[jira/jira#42|https://git.netresearch.de/jira/jira/-/issues/42]
```

## Why not just `!25`?

A bare `!25` in a Jira issue forces the reader to guess which GitLab project it lives in — and to *click* to find out. A bare `v9.12.3-2` is even worse: tag names are reused across many repos.

When an issue references multiple repos in the same group (e.g. `jira/jira` for the image build and `jira/app` for the deploy stack), the cross-project form is essential — `!3` could be either repo's MR.

## Inside `{{...}}` monospace

`!`, `#`, and `@` all work inside `{{...}}`, but **unescaped `{`, `}` and `*` inside a `{{...}}` block break Jira's parser**: a raw `{` makes the whole block render as raw text, and a `*` pair turns bold mid-token. Escape them with a backslash (verified against the Jira Server 9.12 wiki renderer).

Broken — the block falls apart on the raw `{`, and `backup-` renders bold:

```
{{compose.example.{yml,override.pga.yml}}}
{{jira-*backup-*}}
```

Correct — renders `compose.example.{yml,override.pga.yml}` and `jira-*backup-*` in monospace:

```
{{compose.example.\{yml,override.pga.yml\}}}
{{jira-\*backup-\*}}
```

Splitting into separate `{{...}}` references also works when escaping would hurt readability.

The `validate-jira-syntax.sh` script catches the brace collision.
