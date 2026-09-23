"""The pre-flight render check - the layer that asks instead of predicting.

Every test here uses a fake HTTP session. The point of the module is a network
call, and a test that made one would be testing jira.netresearch.de rather than
this code; the live behaviour it is modelled on is recorded in
``tests/fixtures/strikethrough_oracle.json`` and reproducible with
``scripts/verify-render-oracle.py --live``.

The failure paths get as much attention as the happy one on purpose. This check
sits in front of every comment post, so "the renderer could not be reached"
must never be indistinguishable from "the renderer says it is fine" - that
confusion is how an advisory check turns into false confidence.
"""

import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/jira-communication/scripts"))

from lib.preview import RenderVerdict, preflight_render  # noqa: E402

STRUCK_HTML = "<p>Die <tt>nr-pforum</tt><del>Extensions, jede zu</del> und abschaltbar</p>"
CLEAN_HTML = "<p>journalctl -b -p crit zeigt die Fehler</p>"
# What the live instance returns for `{{OPS-899-Divergenzanalyse.pdf}}` (see the
# oracle): OPS-899 is resolved, so Jira draws its key in <del> inside the anchor.
# That is issue-status styling, and escaping the dash does not change it.
AUTOLINK_HTML = (
    '<p>Die <tt><a href="x" class="issue-link" data-issue-key="OPS-899"><del>OPS-899</del></a>'
    "-Divergenzanalyse.pdf</tt> ok</p>"
)


class FakeResponse:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text


class FakeSession:
    """Records the request and returns a canned response."""

    def __init__(self, response=None, raises=None):
        self.headers = {}
        self.auth = None
        self._response = response
        self._raises = raises
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self._raises is not None:
            raise self._raises
        return self._response


@pytest.fixture
def server_env(monkeypatch):
    monkeypatch.setattr(
        "lib.preview.load_config",
        lambda **kwargs: {"JIRA_URL": "https://jira.example.de", "JIRA_PERSONAL_TOKEN": "t"},
    )


class TestVerdict:
    def test_ok_requires_both_available_and_clean(self):
        assert RenderVerdict(True, []).ok
        assert not RenderVerdict(True, ["x"]).ok
        assert not RenderVerdict(False, []).ok

    def test_unavailable_is_not_clean(self):
        """The distinction this whole module hangs on.

        If a failed request collapsed into "no strikethrough", every network
        blip would read as a clean bill of health - the exact shape of bug the
        repo's own rules call out ("can the caller tell failed from empty?").
        """
        verdict = RenderVerdict(False, [], "boom")
        assert verdict.struck == []
        assert not verdict.ok
        assert not verdict.available


class TestPreflightRender:
    def test_clean_markup(self, server_env):
        session = FakeSession(FakeResponse(200, CLEAN_HTML))
        verdict = preflight_render("journalctl -b -p crit", session=session)
        assert verdict.available and verdict.ok and verdict.struck == []

    def test_struck_markup_reports_the_text(self, server_env):
        session = FakeSession(FakeResponse(200, STRUCK_HTML))
        verdict = preflight_render("Die {{nr-pforum}}-Extensions, jede zu- und abschaltbar", session=session)
        assert verdict.available
        assert verdict.struck == ["Extensions, jede zu"]

    def test_resolved_issue_key_alone_is_not_struck(self, server_env):
        """Jira's "resolved" styling of an issue link is not text-effect markup.

        The oracle shows OPS-899's key wrapped in ``<del>`` inside its own
        anchor; that is how Jira draws any resolved issue, with or without a
        dash after it, and escaping cannot change it. Reporting it refused
        every comment that mentioned a resolved issue.
        """
        session = FakeSession(FakeResponse(200, AUTOLINK_HTML))
        verdict = preflight_render("Die {{OPS-899-Divergenzanalyse.pdf}} ok", session=session)
        assert verdict.available and verdict.ok and verdict.struck == []

    def test_markup_inside_del_is_stripped(self, server_env):
        session = FakeSession(FakeResponse(200, "<p><del>a <tt>b</tt> c</del></p>"))
        assert preflight_render("x", session=session).struck == ["a b c"]

    def test_issue_key_is_passed_through(self, server_env):
        session = FakeSession(FakeResponse(200, CLEAN_HTML))
        preflight_render("x", issue_key="OPS-899", session=session)
        assert session.calls[0][1]["json"]["issueKey"] == "OPS-899"

    def test_renderer_type_is_the_wiki_renderer(self, server_env):
        session = FakeSession(FakeResponse(200, CLEAN_HTML))
        preflight_render("x", session=session)
        assert session.calls[0][1]["json"]["rendererType"] == "atlassian-wiki-renderer"


class TestResolvedIssueStyling:
    """Shapes measured on a Server/DC renderer, attributes shortened.

    PROJ-1 is resolved (its key comes back as ``<del>KEY</del>`` inside the
    anchor), PROJ-2 is open. A genuine span always sits outside the anchor.
    """

    RESOLVED = '<a href="x" title="t" class="issue-link" data-issue-key="PROJ-1"><del>PROJ-1</del></a>'
    OPEN = '<a href="x" title="t" class="issue-link" data-issue-key="PROJ-2">PROJ-2</a>'

    def _struck(self, rendered):
        return preflight_render("x", session=FakeSession(FakeResponse(200, rendered))).struck

    def test_resolved_key_in_prose_is_clean(self, server_env):
        assert self._struck(f"<p>see {self.RESOLVED} here</p>") == []

    def test_open_key_is_clean(self, server_env):
        assert self._struck(f"<p>see {self.OPEN} here</p>") == []

    def test_several_resolved_keys_are_clean(self, server_env):
        assert self._struck(f"<p>see {self.RESOLVED}, {self.RESOLVED} and {self.OPEN} here</p>") == []

    def test_span_wrapping_a_resolved_key_is_reported(self, server_env):
        # `-PROJ-1-`
        assert self._struck(f"<p><del>{self.RESOLVED}</del></p>") == ["PROJ-1"]

    def test_span_containing_a_resolved_key_is_reported_whole(self, server_env):
        # `a -struck PROJ-1 text- b`
        assert self._struck(f"<p>a <del>struck {self.RESOLVED} text</del> b</p>") == ["struck PROJ-1 text"]

    def test_span_right_after_a_resolved_key_is_reported(self, server_env):
        # `PROJ-1-x und zu- und`: the autolink boundary case, still caught
        assert self._struck(f"<p>{self.RESOLVED}<del>x und zu</del> und</p>") == ["x und zu"]

    def test_attribute_order_does_not_matter(self, server_env):
        swapped = '<a data-issue-key="PROJ-1" href="x" class="issue-link"><del>PROJ-1</del></a>'
        assert self._struck(f"<p>see {swapped} here</p>") == []

    def test_del_whose_text_is_not_the_anchor_key_is_reported(self, server_env):
        mismatched = '<a href="x" class="issue-link" data-issue-key="PROJ-1"><del>other</del></a>'
        assert self._struck(f"<p>see {mismatched} here</p>") == ["other"]

    def test_gt_inside_a_quoted_title_does_not_cut_the_anchor(self, server_env):
        # The title carries the issue summary; a literal `>` in it must not end
        # the tag, or the resolved <del> survives and truncates the outer span.
        link = '<a href="x" title="timeout > 30s" class="issue-link" data-issue-key="PROJ-1"><del>PROJ-1</del></a>'
        assert self._struck(f"<p><del>X {link} Y</del></p>") == ["X PROJ-1 Y"]

    def test_several_classes_and_single_quotes_are_recognised(self, server_env):
        link = "<a href='x' class='jira issue-link' data-issue-key='PROJ-1'><del>PROJ-1</del></a>"
        assert self._struck(f"<p>see {link} here</p>") == []

    @pytest.mark.parametrize("klass", ["my-issue-link", "issue-link-x", "not-issue-link-at-all"])
    def test_issue_link_must_be_a_whole_class_token(self, server_env, klass):
        link = f'<a href="x" class="{klass}" data-issue-key="PROJ-1"><del>PROJ-1</del></a>'
        assert self._struck(f"<p>see {link} here</p>") == ["PROJ-1"]

    def test_del_inside_a_non_issue_link_is_reported(self, server_env):
        external = '<a href="x" class="external-link" data-issue-key="PROJ-1"><del>PROJ-1</del></a>'
        assert self._struck(f"<p>see {external} here</p>") == ["PROJ-1"]


class TestDegradesInsteadOfBlocking:
    """Every failure path must be reported as unavailable, never as clean."""

    def test_missing_url(self, monkeypatch):
        monkeypatch.setattr("lib.preview.load_config", lambda **kwargs: {})
        verdict = preflight_render("x", session=FakeSession(FakeResponse(200, STRUCK_HTML)))
        assert not verdict.available and "JIRA_URL" in verdict.reason

    def test_cloud_instance_is_skipped(self, monkeypatch):
        monkeypatch.setattr(
            "lib.preview.load_config",
            lambda **kwargs: {"JIRA_URL": "https://acme.atlassian.net", "JIRA_PERSONAL_TOKEN": "t"},
        )
        verdict = preflight_render("x", session=FakeSession(FakeResponse(200, STRUCK_HTML)))
        assert not verdict.available and "Server/DC" in verdict.reason

    def test_no_credentials(self, monkeypatch):
        monkeypatch.setattr("lib.preview.load_config", lambda **kwargs: {"JIRA_URL": "https://jira.example.de"})
        # No session passed, so the credential branch is the one under test.
        verdict = preflight_render("x")
        assert not verdict.available and "credentials" in verdict.reason

    @pytest.mark.parametrize("status", [401, 403, 404, 429, 500, 503])
    def test_non_200_is_unavailable(self, server_env, status):
        verdict = preflight_render("x", session=FakeSession(FakeResponse(status, STRUCK_HTML)))
        assert not verdict.available
        assert str(status) in verdict.reason
        assert verdict.struck == []

    @pytest.mark.parametrize(
        "exc",
        [requests.ConnectionError("down"), requests.Timeout("slow"), requests.TooManyRedirects("loop")],
    )
    def test_network_failure_is_unavailable(self, server_env, exc):
        verdict = preflight_render("x", session=FakeSession(raises=exc))
        assert not verdict.available and "render request failed" in verdict.reason


class TestOnlyTrustsActualRenderOutput:
    """A 200 is not proof the body came from the renderer.

    An SSO or maintenance page intercepting the request answers 200 with HTML
    that has no <del> in it. Reported as available+clean, that is a clean
    verdict on an unrendered comment - the worst outcome this module can
    produce, and the one its docstring promises it will not.
    """

    SSO_PAGE = "<html><head><title>Log in</title></head><body><form>SSO</form></body></html>"

    def test_interception_page_is_unavailable_not_clean(self, server_env):
        session = FakeSession(FakeResponse(200, self.SSO_PAGE))
        verdict = preflight_render("Die {{a}}-Extensions, jede zu- und abschaltbar", session=session)
        assert not verdict.available
        assert "render output" in verdict.reason

    def test_empty_body_is_unavailable(self, server_env):
        verdict = preflight_render("Extensions abschaltbar", session=FakeSession(FakeResponse(200, "")))
        assert not verdict.available

    def test_body_missing_the_input_text_is_unavailable(self, server_env):
        # A fragment, but not this input's fragment.
        session = FakeSession(FakeResponse(200, "<p>something else entirely</p>"))
        assert not preflight_render("Extensions abschaltbar", session=session).available

    def test_genuine_fragment_is_accepted(self, server_env):
        session = FakeSession(FakeResponse(200, STRUCK_HTML))
        verdict = preflight_render("Die {{nr-pforum}}-Extensions, jede zu- und abschaltbar", session=session)
        assert verdict.available and verdict.struck == ["Extensions, jede zu"]

    def test_input_with_no_long_word_still_renders(self, server_env):
        # Nothing to look for, so the fragment check alone decides.
        session = FakeSession(FakeResponse(200, "<p>a <del>x</del> b</p>"))
        assert preflight_render("a -x- b", session=session).available


class TestTargetsTheSameInstanceAsTheWrite:
    """The preview must resolve the instance the comment will be posted to.

    Rendering against a different Jira is worse than not rendering: the issue
    key does not resolve there, so the autolink substitution never fires and
    the verdict comes back clean on precisely the case this module exists for.
    """

    def test_all_three_arguments_reach_the_loader(self, monkeypatch):
        """The client resolves a profile BY ISSUE KEY even with no --profile.

        An earlier version only consulted profiles when --profile was given, so
        `jira-comment.py add OPS-899 "..."` wrote to the key-resolved instance
        and previewed against ~/.env.jira. All three go to load_config now -
        the loader LazyJiraClient itself uses.
        """
        seen = {}

        def fake_load_config(profile=None, env_file=None, issue_key=None, **kwargs):
            seen.update(profile=profile, env_file=env_file, issue_key=issue_key)
            return {"JIRA_URL": "https://other.example.de", "JIRA_PERSONAL_TOKEN": "t"}

        monkeypatch.setattr("lib.preview.load_config", fake_load_config)
        session = FakeSession(FakeResponse(200, CLEAN_HTML))
        preflight_render(
            "Extensions abschaltbar",
            issue_key="OPS-899",
            profile="other",
            env_file="/tmp/other.env",
            session=session,
        )
        assert seen == {"profile": "other", "env_file": "/tmp/other.env", "issue_key": "OPS-899"}
        # Full URL, not a prefix: a prefix check says nothing about what follows
        # it, and CodeQL reads `startswith` on a URL as a sanitization attempt.
        assert session.calls[0][0] == "https://other.example.de/rest/api/1.0/render"

    def test_issue_key_alone_still_reaches_the_loader(self, monkeypatch):
        seen = {}

        def fake_load_config(**kwargs):
            seen.update(kwargs)
            return {"JIRA_URL": "https://jira.example.de", "JIRA_PERSONAL_TOKEN": "t"}

        monkeypatch.setattr("lib.preview.load_config", fake_load_config)
        preflight_render(
            "Extensions abschaltbar", issue_key="OPS-899", session=FakeSession(FakeResponse(200, CLEAN_HTML))
        )
        assert seen["issue_key"] == "OPS-899"

    def test_unusable_config_carries_the_reason(self, monkeypatch):
        """A broken profile store and an unset JIRA_URL are different problems."""
        monkeypatch.setattr(
            "lib.preview.load_config",
            lambda **kwargs: (_ for _ in ()).throw(ValueError("profile 'missing' is ambiguous")),
        )
        verdict = preflight_render("x", profile="missing", session=FakeSession(FakeResponse(200, CLEAN_HTML)))
        assert not verdict.available
        assert "ambiguous" in verdict.reason, verdict.reason


class TestCheckRenderingGate:
    """``check_rendering`` must abort on a struck preview and never on a failure.

    Tests the gate where it now lives - ``lib.markup_cli`` - rather than
    through one command that happens to call it. It guards all seven wiki-markup
    surfaces, so binding these to ``jira-comment.py`` would have tested one
    sixth of the behaviour while reading like all of it.
    """

    @staticmethod
    def _gate():
        from lib import markup_cli

        return markup_cli

    def test_struck_preview_aborts(self, monkeypatch):
        gate = self._gate()
        monkeypatch.setattr(gate, "preflight_render", lambda *a, **k: RenderVerdict(True, ["OPS-899"]))
        with pytest.raises(SystemExit) as exc:
            gate.check_rendering("x", force=False, issue_key="OPS-899", enabled=True)
        assert exc.value.code == 1

    def test_force_downgrades_to_a_warning(self, monkeypatch):
        gate = self._gate()
        monkeypatch.setattr(gate, "preflight_render", lambda *a, **k: RenderVerdict(True, ["OPS-899"]))
        gate.check_rendering("x", force=True, issue_key="OPS-899", enabled=True)

    def test_clean_preview_passes(self, monkeypatch):
        gate = self._gate()
        monkeypatch.setattr(gate, "preflight_render", lambda *a, **k: RenderVerdict(True, []))
        gate.check_rendering("x", force=False, issue_key="OPS-899", enabled=True)

    def test_unavailable_renderer_does_not_block_the_write(self, monkeypatch):
        gate = self._gate()
        monkeypatch.setattr(gate, "preflight_render", lambda *a, **k: RenderVerdict(False, [], "down"))
        gate.check_rendering("x", force=False, issue_key="OPS-899", enabled=True)

    def test_disabled_makes_no_call(self, monkeypatch):
        gate = self._gate()

        def explode(*a, **k):
            raise AssertionError("--no-preflight must not call the renderer")

        monkeypatch.setattr(gate, "preflight_render", explode)
        gate.check_rendering("x", force=False, issue_key="OPS-899", enabled=False)
