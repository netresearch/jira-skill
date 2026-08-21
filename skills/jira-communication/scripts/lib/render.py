"""Terminal rendering of issue descriptions and comments.

Shared by ``jira-issue.py`` (work / qa / qa-fail) and ``jira-qa-gather.py`` so
both print the same shape: the description indented under a ``Description:``
header, each comment under a ``--- [created] author ---`` separator. Lives
outside ``output.py`` because it needs ``users.person_label`` and ``users``
already imports ``output`` (no circular imports between lib modules).
"""

from .output import comment_to_text, extract_adf_text
from .users import person_label


def truncate_text(text: str, n: int | None) -> str:
    """Cut ``text`` to at most ``n`` chars at a word boundary; ``n`` falsy = no-op."""
    if not n or len(text) <= n:
        return text
    return text[:n].rsplit(" ", 1)[0] + " …[truncated]"


def print_comment(comment: dict, *, truncate: int | None = None) -> None:
    """Print one comment: ``--- [YYYY-MM-DD HH:MM] Author (name) ---`` then the body."""
    author = person_label(comment.get("author"))
    created = comment.get("created", "")[:16].replace("T", " ")
    body = comment_to_text(comment.get("body"))
    if truncate:
        body = truncate_text(body, truncate)
    print(f"\n--- [{created}] {author} ---")
    for line in body.split("\n"):
        print(line)


def print_description(issue: dict, *, truncate: int | None = None) -> None:
    """Print the issue description (Server string or Cloud ADF) under a header; no-op when empty."""
    description = issue.get("fields", {}).get("description")
    if not description:
        return
    if isinstance(description, dict):
        description = extract_adf_text(description)
    text = str(description)
    if truncate:
        text = truncate_text(text, truncate)
    print("\nDescription:")
    for line in text.split("\n"):
        print(f"  {line}")
