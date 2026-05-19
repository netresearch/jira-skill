"""Tests for ``lib.input.read_stdin_utf8`` — the UTF-8-correct stdin reader."""

import sys
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest

# Add scripts to path for lib imports (mirrors tests/test_output.py).
_test_dir = Path(__file__).parent
_scripts_path = _test_dir.parent / "skills" / "jira-communication" / "scripts"
sys.path.insert(0, str(_scripts_path))

from lib.input import read_stdin_utf8


def _fake_stdin(buffer_bytes: bytes, *, text_read_raises: bool = False):
    """Build a minimal stand-in for ``sys.stdin`` whose ``.buffer`` exposes
    ``buffer_bytes``. If ``text_read_raises`` is set, calling ``.read()`` on
    the text wrapper will fail loudly — useful for proving the helper only
    touches ``.buffer``.
    """

    class _FakeStdin:
        buffer = BytesIO(buffer_bytes)
        encoding = "cp1252"  # simulate a Windows-misconfigured text wrapper

        def read(self, *_args, **_kwargs):
            if text_read_raises:
                raise AssertionError("read_stdin_utf8 must not call sys.stdin.read() — only sys.stdin.buffer.read()")
            return self.buffer.read().decode(self.encoding)

    return _FakeStdin()


class TestReadStdinUtf8:
    """``read_stdin_utf8`` must decode UTF-8 regardless of the host locale."""

    def test_returns_empty_string_for_empty_stdin(self):
        with patch.object(sys, "stdin", _fake_stdin(b"")):
            assert read_stdin_utf8() == ""

    def test_decodes_ascii_round_trip(self):
        with patch.object(sys, "stdin", _fake_stdin(b"hello world")):
            assert read_stdin_utf8() == "hello world"

    def test_decodes_german_umlauts(self):
        payload = "Schöne Grüße aus Leipzig"
        with patch.object(sys, "stdin", _fake_stdin(payload.encode("utf-8"))):
            assert read_stdin_utf8() == payload

    def test_decodes_section_sign_and_em_dash(self):
        """§ and — are the two characters that triggered today's incident."""
        payload = "Spec § 4.1 — der Idempotency-Key ist required"
        with patch.object(sys, "stdin", _fake_stdin(payload.encode("utf-8"))):
            assert read_stdin_utf8() == payload

    def test_decodes_emoji_and_arrows(self):
        payload = "✓ done — replay → 200, conflict → 409"
        with patch.object(sys, "stdin", _fake_stdin(payload.encode("utf-8"))):
            assert read_stdin_utf8() == payload

    def test_max_bytes_caps_read(self):
        with patch.object(sys, "stdin", _fake_stdin(b"abcdef")):
            assert read_stdin_utf8(max_bytes=3) == "abc"

    def test_max_bytes_none_reads_everything(self):
        with patch.object(sys, "stdin", _fake_stdin(b"abcdef")):
            assert read_stdin_utf8(max_bytes=None) == "abcdef"

    def test_invalid_utf8_raises_unicode_decode_error(self):
        # Lone 0xff is invalid as a UTF-8 start byte.
        with patch.object(sys, "stdin", _fake_stdin(b"\xff\xfe\xfd")):
            with pytest.raises(UnicodeDecodeError):
                read_stdin_utf8()

    def test_does_not_touch_text_mode_stdin_read(self):
        """Regression guard for the original Windows-cp1252 bug.

        If a future refactor brings back ``sys.stdin.read()``, the text
        wrapper's read() raises an AssertionError so the test fails loudly.
        """
        payload = "Größe"  # ü encodes as C3 BC — would mojibake under cp1252
        with patch.object(sys, "stdin", _fake_stdin(payload.encode("utf-8"), text_read_raises=True)):
            assert read_stdin_utf8() == payload
