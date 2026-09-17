"""Ask the Jira instance how it will render a piece of wiki markup.

The lexical model in ``lib.markup`` predicts what Jira does to dashes, and it
is measured rather than guessed - but it is a model, and one class of defect is
out of its reach by construction: Jira substitutes autolinked issue keys before
text effects run. ``OPS-899-x ... zu-`` is struck through on an instance where
OPS-899 exists and renders literally on one where it does not. Same string, two
renderings, decided by state that lives in the Jira database. No source-level
model can decide it, and a better regex will not change that - which is why the
same class of bug kept coming back.

This module asks instead of predicting. ``POST /rest/api/1.0/render`` is the
endpoint behind Jira's own "preview" button on Server/DC, so the answer is the
renderer's, not ours.

It is advisory by design: a renderer that is unreachable, slow, or absent (the
endpoint is Server/DC-only) must never stop somebody posting a comment. Every
failure path returns "unknown" and says why, and the caller degrades to the
lexical check.
"""

import re
from dataclasses import dataclass
from typing import Any

import requests

from lib.config import is_cloud_url, load_env

RENDER_PATH = "/rest/api/1.0/render"
DEFAULT_TIMEOUT = 10

_DEL_RE = re.compile(r"<del>(.*?)</del>", re.S)
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class RenderVerdict:
    """What the instance said, or why it could not be asked.

    ``available`` is False for every failure - unreachable, unauthorised, Cloud,
    endpoint missing. It is deliberately NOT collapsed into ``struck=False``:
    "the renderer says this is clean" and "nobody asked the renderer" must stay
    distinguishable, or a network blip reads as a clean bill of health.
    """

    available: bool
    struck: list[str]
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.available and not self.struck


def _plain(fragment: str) -> str:
    return _TAG_RE.sub("", fragment).strip()


def preflight_render(
    text: str,
    *,
    issue_key: str | None = None,
    env_file: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    session: Any = None,
) -> RenderVerdict:
    """Render ``text`` on the configured instance and report struck-through spans.

    Returns the plain text of every ``<del>`` the renderer produced. An empty
    list with ``available=True`` means the instance itself says the markup is
    clean - the strongest statement available short of posting it.
    """
    config = load_env(env_file)
    base_url = config.get("JIRA_URL")
    if not base_url:
        return RenderVerdict(False, [], "JIRA_URL is not configured")
    if is_cloud_url(base_url):
        # Cloud has no api/1.0 wiki renderer and uses ADF anyway. Saying so
        # beats a 404 the caller has to interpret.
        return RenderVerdict(False, [], "preview endpoint is Server/DC only")

    http = session or requests.Session()
    if session is None:
        if config.get("JIRA_PERSONAL_TOKEN"):
            http.headers["Authorization"] = f"Bearer {config['JIRA_PERSONAL_TOKEN']}"
        elif config.get("JIRA_USERNAME") and config.get("JIRA_API_TOKEN"):
            http.auth = (config["JIRA_USERNAME"], config["JIRA_API_TOKEN"])
        else:
            return RenderVerdict(False, [], "no Jira credentials found")

    try:
        response = http.post(
            f"{base_url.rstrip('/')}{RENDER_PATH}",
            json={
                "rendererType": "atlassian-wiki-renderer",
                "unrenderedMarkup": text,
                # Passing the key is the faithful context even though this
                # instance renders identically without it (measured on
                # OPS-899); a future Jira may not.
                "issueKey": issue_key,
            },
            headers={"Content-Type": "application/json"},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        return RenderVerdict(False, [], f"render request failed: {type(exc).__name__}")

    if response.status_code != 200:
        return RenderVerdict(False, [], f"render endpoint returned HTTP {response.status_code}")

    return RenderVerdict(True, [_plain(m) for m in _DEL_RE.findall(response.text)])


def rendered_body_strikethrough(rendered_body: str) -> list[str]:
    """Struck-through text in a comment's ``renderedBody``, as Jira stored it.

    The last line of defence: what the reader will actually see, read back
    after the write. ``references/comments.md`` documented doing this by hand;
    a check nobody remembers to run is not a control.
    """
    return [_plain(m) for m in _DEL_RE.findall(rendered_body or "")]
