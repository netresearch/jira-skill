#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests>=2.31,<3",
#     "atlassian-python-api>=3.41.0,<4",
# ]
# ///
"""Re-record the strikethrough oracle against a live Jira wiki renderer.

``tests/fixtures/strikethrough_oracle.json`` is what makes the grammar in
``lib/markup.py`` a measurement instead of a belief. This script is how that
measurement is repeated - against a Jira upgrade, another deployment, or a
claim in a review that "Jira does X".

    # compare the fixture against the live renderer, change nothing
    uv run scripts/verify-render-oracle.py --live

    # same, but write back what the renderer actually said
    uv run scripts/verify-render-oracle.py --live --record

Credentials come from ``lib/config`` (``~/.env.jira`` or ``--env-file``), the
same place every other script in this repo reads them.
"""

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "skills/jira-communication/scripts"))

import requests  # noqa: E402
from lib.config import load_env  # noqa: E402

FIXTURE = _REPO / "tests/fixtures/strikethrough_oracle.json"

# The preview endpoint behind Jira's own "wiki markup" preview button. Present
# on Server/DC; the Cloud pathway is untested here on purpose (see the
# atlassian-python-api note in the root AGENTS.md).
RENDER_PATH = "/rest/api/1.0/render"


def render(session: requests.Session, base_url: str, markup: str) -> str:
    response = session.post(
        f"{base_url.rstrip('/')}{RENDER_PATH}",
        json={"rendererType": "atlassian-wiki-renderer", "unrenderedMarkup": markup, "issueKey": None},
        timeout=30,
    )
    response.raise_for_status()
    return response.text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--live",
        action="store_true",
        required=True,
        help="Actually call Jira. Required, so the network call is never a side effect of a typo.",
    )
    parser.add_argument("--record", action="store_true", help="Write the live output back into the fixture")
    parser.add_argument("--env-file", help="Environment file with JIRA_URL / JIRA_PERSONAL_TOKEN")
    args = parser.parse_args()

    config = load_env(args.env_file)
    base_url = config.get("JIRA_URL")
    if not base_url:
        print("error: JIRA_URL is not set - see lib/config.py", file=sys.stderr)
        return 2

    session = requests.Session()
    if config.get("JIRA_PERSONAL_TOKEN"):
        session.headers["Authorization"] = f"Bearer {config['JIRA_PERSONAL_TOKEN']}"
    elif config.get("JIRA_USERNAME") and config.get("JIRA_API_TOKEN"):
        session.auth = (config["JIRA_USERNAME"], config["JIRA_API_TOKEN"])
    else:
        print("error: no Jira credentials found - see lib/config.py", file=sys.stderr)
        return 2

    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    drift = []
    for case in fixture["cases"]:
        live = render(session, base_url, case["markup"])
        if live != case["rendered"]:
            drift.append(case["markup"])
            print(f"DRIFT  {case['markup']!r}\n  fixture: {case['rendered'].strip()!r}\n  live   : {live.strip()!r}")
        case["rendered"] = live

    print(f"\n{len(fixture['cases'])} cases checked against {base_url}, {len(drift)} drifted")

    if args.record:
        fixture["recorded_against"] = f"{base_url} (as reported by --record)"
        FIXTURE.write_text(json.dumps(fixture, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"recorded into {FIXTURE.relative_to(_REPO)}")
        return 0

    # Drift is the finding, not an error: a different Jira version legitimately
    # renders differently. It must be looked at, so it must not exit 0.
    return 1 if drift else 0


if __name__ == "__main__":
    sys.exit(main())
