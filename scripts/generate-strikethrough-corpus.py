#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests>=2.31,<3",
#     "atlassian-python-api>=3.41.0,<4",
# ]
# ///
"""Generate the strikethrough corpus and record how a live Jira renders it.

``tests/fixtures/strikethrough_corpus.json`` is what stops this rule being
re-derived wrongly a third time. Two hand-written versions of the dash grammar
shipped before it existed: the first claimed ``journalctl -b -p crit`` was a
matched pair, the second passed 168 hand-picked cases while still asserting
that a span body cannot contain a dash. Neither survived contact with a
systematic corpus, and neither could have been caught by cases a human chose,
because a human chooses the cases they already thought of.

So this enumerates instead: every ordered pair and triple over an alphabet of
dash-relevant tokens, a random sample of longer ones, and a set of
prose-shaped sentences, then asks the renderer what each one does.

    uv run scripts/generate-strikethrough-corpus.py --live
    uv run scripts/generate-strikethrough-corpus.py --live --record

Without ``--record`` it only reports how the current model in ``lib/markup.py``
scores against the freshly rendered cases. Credentials come from ``lib/config``
(``~/.env.jira`` or ``--env-file``), like every other script here.
"""

import argparse
import hashlib
import itertools
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "skills/jira-communication/scripts"))

import requests  # noqa: E402
from lib.config import load_env  # noqa: E402
from lib.markup import find_strikethrough_spans  # noqa: E402

FIXTURE = _REPO / "tests/fixtures/strikethrough_corpus.json"
RENDER_PATH = "/rest/api/1.0/render"

# Every token that can influence the grammar: word characters of both ASCII and
# non-ASCII kinds, the punctuation that forms a boundary, dash runs, an escape,
# and one of each protected region (link, bare URL, image) carrying a literal
# `/-/` - the shape a GitLab merge-request URL has.
#
# Two of the tokens put U+00A0 INSIDE a region. A review found that the bare
# `\u00a0` token could never produce that shape - pairs and triples cannot fit
# region + NBSP + live-dash tail - so the corpus certified a real divergence as
# clean: the awk mirror let a region swallow the dashes after an NBSP. A class
# the alphabet cannot express is a class the corpus cannot defend.
#
# `§` and U+00A0 are here because a review found both classes unrepresented:
# the awk mirror lost the opener boundary on non-ASCII SYMBOLS under LC_ALL=C,
# and Python read U+00A0 as whitespace and dropped a closer Jira accepts. NBSP
# arrives routinely in text pasted out of Word. `\[` covers the escaped-bracket
# case, where the region does NOT resolve and its dashes stay live.
TOKENS = [
    "a",
    "ab",
    "-",
    "--",
    "\\-",
    " ",
    "}}",
    ".",
    "_",
    "/",
    "ä",
    "§",
    "\u00a0",
    "\\[",
    "{{m}}",
    "[t|https://x.de/a/-/b]",
    "https://x.de/a/-/b",
    "https://x.de/a\u00a0/-/b",
    "!i.png!",
    "!-x\u00a0y!",
    "*b*",
    "1",
]

# Fixed salt: the corpus must be reproducible, or "re-record and diff" is
# meaningless.
SEED = 226
LONG_SAMPLES = 400


def build_cases() -> list[str]:
    cases: list[str] = []
    for length in (2, 3):
        for combo in itertools.product(TOKENS, repeat=length):
            cases.append("x " + "".join(combo) + " y")

    # Longer sequences, sampled deterministically from a hash rather than a PRNG.
    # The corpus has to be byte-identical on every machine and interpreter or
    # "re-record and diff the fixture" means nothing, and a hash gives that
    # guarantee outright instead of relying on an implementation detail of
    # random.Random staying put across versions.
    for index in range(LONG_SAMPLES):
        digest = hashlib.sha256(f"{SEED}:{index}".encode()).digest()
        size = 4 + digest[0] % 3
        picks = [TOKENS[digest[1 + n] % len(TOKENS)] for n in range(size)]
        cases.append("x " + "".join(picks) + " y")

    # Prose-shaped: an opener candidate after each kind of boundary, combined
    # with each kind of tail. `zu- und` is the German elliptical compound from
    # issue #226 - the closer that makes an otherwise harmless line break.
    for lead in ["{{m}}", "*b*", "ab", "[t|https://x.de/a/-/b]", "https://x.de/a/-/b", "!i.png!", "/", "."]:
        for mid in ["-x", "--x", "\\-x", "-1", "- x"]:
            for tail in ["zu- und", "word-", "-v mehr", "nichts", "zu\\- und"]:
                cases.append(f"Der {lead}{mid} Wert ist {tail} da.")

    return list(dict.fromkeys(cases))


def make_session(env_file: str | None) -> tuple[requests.Session, str]:
    config = load_env(env_file)
    base_url = config.get("JIRA_URL")
    if not base_url:
        raise SystemExit("error: JIRA_URL is not set - see lib/config.py")
    session = requests.Session()
    if config.get("JIRA_PERSONAL_TOKEN"):
        session.headers["Authorization"] = f"Bearer {config['JIRA_PERSONAL_TOKEN']}"
    elif config.get("JIRA_USERNAME") and config.get("JIRA_API_TOKEN"):
        session.auth = (config["JIRA_USERNAME"], config["JIRA_API_TOKEN"])
    else:
        raise SystemExit("error: no Jira credentials found - see lib/config.py")
    return session, base_url.rstrip("/")


def render(session: requests.Session, base_url: str, markup: str, attempts: int = 6) -> str:
    """POST one snippet to the renderer, backing off when Jira throttles.

    A corpus run is thousands of requests, so a 429 is the normal case rather
    than an exception - a run that dies on the first one leaves a half-recorded
    fixture, which is worse than a slow run.
    """
    for attempt in range(attempts):
        response = session.post(
            f"{base_url}{RENDER_PATH}",
            json={"rendererType": "atlassian-wiki-renderer", "unrenderedMarkup": markup, "issueKey": None},
            timeout=30,
        )
        if response.status_code == 429 or response.status_code >= 500:
            if attempt == attempts - 1:
                response.raise_for_status()
            time.sleep(float(response.headers.get("Retry-After", 2**attempt)))
            continue
        response.raise_for_status()
        return response.text
    raise RuntimeError("unreachable")


_VERBATIM_RE = re.compile(r"^\s*\{(code|noformat)(?::[^}\n]*)?\}\s*$")


def predicts_span(markup: str) -> bool:
    open_tag = None
    for line in markup.split("\n"):
        match = _VERBATIM_RE.match(line)
        if open_tag is not None:
            if match is not None and match.group(1) == open_tag:
                open_tag = None
            continue
        if match is not None:
            open_tag = match.group(1)
            continue
        if find_strikethrough_spans(line):
            return True
    return False


def write_fixture(fixture: dict, results: dict[str, bool], *, write: bool, accept_new_misses: bool) -> int:
    """Report the pinned lists the model currently produces, and optionally store them.

    Two flat lists rather than a list of objects: at this size the repeated
    {"markup": ..., "struck": ...} scaffolding is most of the file, and the
    repo's pre-commit gate rejects large files.

    A NEW under-prediction is never pinned silently. This function is what
    ``--repin`` calls after a model change - which is exactly the moment a
    regression would show up as a new miss, and pinning it makes the suite
    green again while the model is worse than it was. New misses are listed
    and refused unless ``--accept-new-misses`` says they were looked at.
    """
    under = sorted(m for m, struck in results.items() if struck and not predicts_span(m))
    over = sorted(m for m, struck in results.items() if not struck and predicts_span(m))
    was_under = set(fixture.get("known_under_predictions", []))
    new_misses = [m for m in under if m not in was_under]
    fixed = sorted(was_under - set(under))

    print(f"under-predictions: {len(under)} (was {len(was_under)})  over-predictions: {len(over)}", file=sys.stderr)
    for markup in fixed:
        print(f"  NO LONGER MISSED  {markup!r}", file=sys.stderr)
    for markup in new_misses:
        print(f"  NEW MISS          {markup!r}", file=sys.stderr)

    if new_misses and not accept_new_misses:
        print(
            f"\nrefusing to pin {len(new_misses)} new miss(es). The model got worse, or a new "
            "class appeared. Look at them, then pass --accept-new-misses to pin them.",
            file=sys.stderr,
        )
        return 1

    if not write:
        print("\nnothing written (pass --record to store this)", file=sys.stderr)
        return 1 if under else 0

    fixture["known_under_predictions"] = under
    fixture["known_over_predictions"] = over
    fixture["struck"] = sorted(m for m, struck in results.items() if struck)
    fixture["clean"] = sorted(m for m, struck in results.items() if not struck)
    fixture.pop("cases", None)
    FIXTURE.write_text(json.dumps(fixture, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"recorded into {FIXTURE.relative_to(_REPO)}", file=sys.stderr)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Actually call Jira. Required unless --repin, so the traffic is never a side effect of a typo.",
    )
    parser.add_argument(
        "--repin",
        action="store_true",
        help="Recompute the pinned lists from the verdicts already recorded, without calling Jira. "
        "Use after a model change: the renderer's answers have not changed, only ours.",
    )
    parser.add_argument("--record", action="store_true", help="Write the result into the fixture")
    parser.add_argument(
        "--accept-new-misses",
        action="store_true",
        help="Pin under-predictions that are not already pinned. Without it they are listed and refused.",
    )
    parser.add_argument("--env-file", help="Environment file with JIRA_URL / JIRA_PERSONAL_TOKEN")
    parser.add_argument("--workers", type=int, default=3, help="Parallel render requests (default 3)")
    args = parser.parse_args()

    if args.repin:
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        if "struck" not in fixture or "clean" not in fixture:
            parser.error("fixture is in the old {markup, struck} format - re-record it with --live --record")
        results = dict.fromkeys(fixture["struck"], True) | dict.fromkeys(fixture["clean"], False)
        return write_fixture(fixture, results, write=args.record, accept_new_misses=args.accept_new_misses)

    if not args.live:
        parser.error("pass --live to call Jira, or --repin to recompute from the recorded verdicts")

    session, base_url = make_session(args.env_file)
    cases = build_cases()
    print(f"{len(cases)} cases against {base_url}", file=sys.stderr)

    def one(markup: str) -> tuple[str, bool]:
        return markup, "<del>" in render(session, base_url, markup)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = dict(pool.map(one, cases))

    under = sorted(m for m, struck in results.items() if struck and not predicts_span(m))
    over = sorted(m for m, struck in results.items() if not struck and predicts_span(m))
    print(f"under-predictions (model misses a real span): {len(under)}", file=sys.stderr)
    print(f"over-predictions  (model escapes needlessly): {len(over)}", file=sys.stderr)

    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return write_fixture(fixture, results, write=args.record, accept_new_misses=args.accept_new_misses)


if __name__ == "__main__":
    sys.exit(main())
