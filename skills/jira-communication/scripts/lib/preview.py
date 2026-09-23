"""Ask the Jira instance how it will render a piece of wiki markup.

The lexical model in ``lib.markup`` predicts what Jira does to dashes, and it
is measured rather than guessed - but it is a model, and one class of defect is
out of its reach by construction: Jira substitutes autolinked issue keys before
text effects run. ``OPS-899-x ... zu-`` is struck through on an instance where
OPS-899 exists and renders literally on one where it does not. Same string, two
renderings, decided by state that lives in the Jira database. No source-level
model can decide it, and a better regex will not change that - which is why the
same class of bug kept coming back.

One ``<del>`` in the answer is not a text effect at all: Jira draws a link to a
RESOLVED issue with the key struck through inside its anchor, as status
styling. That shape is unwrapped before the spans are collected, so mentioning
a resolved issue is not a finding while a real span next to or around the link
still is.

This module asks instead of predicting. ``POST /rest/api/1.0/render`` is the
endpoint behind Jira's own "preview" button on Server/DC, so the answer is the
renderer's, not ours.

It is advisory by design: a renderer that is unreachable, slow, or absent (the
endpoint is Server/DC-only) must never stop somebody posting a comment. Every
failure path returns "unknown" and says why, and the caller degrades to the
lexical check.
"""

import html
import re
from dataclasses import dataclass
from typing import Any

import requests

from lib.config import is_cloud_url, load_config

RENDER_PATH = "/rest/api/1.0/render"
DEFAULT_TIMEOUT = 10

_DEL_RE = re.compile(r"<del>(.*?)</del>", re.S)
# A tag, with quoted attribute values taken whole: an issue link's title is the
# issue summary, and a literal `>` in it must not end the tag.
_ATTRS = r"""(?:[^>"']|"[^"]*"|'[^']*')*"""
_TAG_RE = re.compile(rf"<{_ATTRS}>")
# Jira draws a link to a RESOLVED issue with its key in <del>, inside the
# anchor: `<a class="issue-link" data-issue-key="K"><del>K</del></a>`. That is
# issue-status styling, not text-effect markup; escaping cannot change it, and
# reporting it refused every comment that mentioned a resolved issue. A genuine
# span is always outside the anchor (around it or next to it), so only the
# exact shape is unwrapped: an issue-link anchor whose whole content is
# `<del>` + its own data-issue-key + `</del>`.
_RESOLVED_ISSUE_LINK_RE = re.compile(rf"(<a\b{_ATTRS}>)<del>([^<]*)</del></a>")
_CLASS_ISSUE_LINK_RE = re.compile(r"""\bclass=["'](?:[^"']*\s)?issue-link(?:\s[^"']*)?["']""")
_DATA_ISSUE_KEY_RE = re.compile(r"""\bdata-issue-key=["']([^"']+)["']""")

# Jira macro syntax, stripped before looking for echoed prose: {code}, {color:red},
# {{monospace}}, [text|url], !image.png!.
_MACRO_RE = re.compile(r"\{\{.*?\}\}|\{[^}\n]*\}|\[[^\]\n]*\]|![^\s!]+!")


def _unwrap_resolved_issue_links(body: str) -> str:
    """Drop the resolved-issue ``<del>`` so only text-effect spans remain."""

    def unwrap(match: re.Match) -> str:
        anchor, text = match.group(1), match.group(2)
        key = _DATA_ISSUE_KEY_RE.search(anchor)
        if _CLASS_ISSUE_LINK_RE.search(anchor) and key and key.group(1) == text:
            return f"{anchor}{text}</a>"
        return match.group(0)

    return _RESOLVED_ISSUE_LINK_RE.sub(unwrap, body)


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


def _looks_like_render_output(body: str, source: str) -> bool:
    """Cheap sanity check that ``body`` is the renderer's answer to ``source``.

    Two signals, both one-directional. The renderer returns a fragment, so a
    full HTML document is somebody else answering - a login page, a proxy, a
    maintenance notice. And the renderer echoes the text it was given, so a
    reasonably long word from the input should survive into the output.

    Deliberately lenient: a false "unavailable" costs one warning, while a
    false "available" is a clean verdict on an unrendered comment.
    """
    lowered = body.lower()
    if "<html" in lowered or "<!doctype" in lowered:
        return False
    # Words are taken from the PROSE, with macro syntax removed first. A macro
    # name is not echoed - the renderer consumes it - so `{color:red}ok{color}`
    # or `!screenshot.png!` would otherwise be rejected as "not render output",
    # and an image-only comment is an ordinary Jira comment.
    prose = _MACRO_RE.sub(" ", source)
    words = re.findall(r"[A-Za-z\u00c0-\u024f]{4,}", prose)
    if not words:
        return True  # nothing to look for; the document check above stands alone
    # ANY surviving word, not all of them and not the longest: the renderer
    # entity-escapes non-ASCII (`Übersicht` comes back as `&Uuml;bersicht`), so
    # requiring a specific word would fail on ordinary German prose.
    plain = html.unescape(_plain(body)).lower()
    return any(word.lower() in plain for word in words)


def _resolve_config(issue_key: str | None, env_file: str | None, profile: str | None) -> tuple[dict, str]:
    """Config for the SAME instance the write will go to, or the reason there is none.

    This calls ``load_config`` - the loader ``LazyJiraClient`` itself uses -
    rather than reimplementing part of it. An earlier version only consulted
    profiles when ``--profile`` was given explicitly, which missed the common
    case entirely: ``jira-comment.py add OPS-899 "..."`` resolves a profile BY
    ISSUE KEY in the client and fell back to ``~/.env.jira`` here. A preview
    rendered against a different Jira is worse than no preview - the key does
    not resolve there, the autolink substitution never fires, and the verdict
    comes back clean on exactly the case this module exists to catch.
    """
    try:
        return load_config(profile=profile, env_file=env_file, issue_key=issue_key), ""
    except (ValueError, KeyError, OSError, FileNotFoundError) as exc:
        # Carry the reason: "profiles.json is unreadable" and "JIRA_URL is not
        # set" are different problems and the message is what gets acted on.
        return {}, f"could not resolve the Jira config: {type(exc).__name__}: {exc}"


def preflight_render(
    text: str,
    *,
    issue_key: str | None = None,
    env_file: str | None = None,
    profile: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    session: Any = None,
) -> RenderVerdict:
    """Render ``text`` on the configured instance and report struck-through spans.

    Returns the plain text of every ``<del>`` the renderer produced. An empty
    list with ``available=True`` means the instance itself says the markup is
    clean - the strongest statement available short of posting it.
    """
    config, problem = _resolve_config(issue_key, env_file, profile)
    if problem:
        return RenderVerdict(False, [], problem)
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

    if not _looks_like_render_output(response.text, text):
        # An SSO or maintenance page intercepting the request answers 200 with
        # HTML that contains no <del>, which would otherwise be reported as
        # "the instance says this is clean" - the one reading this module must
        # never produce.
        return RenderVerdict(False, [], "response does not look like render output")

    body = _unwrap_resolved_issue_links(response.text)
    return RenderVerdict(True, [_plain(m) for m in _DEL_RE.findall(body)])
