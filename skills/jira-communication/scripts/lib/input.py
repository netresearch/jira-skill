"""Stdin helpers for Jira CLI scripts that accept piped input.

This module is the input-side companion to :mod:`lib.output`, which
reconfigures ``stdout`` / ``stderr`` to UTF-8 on Windows at import time
(see PR #61). On the input side we cannot rely on auto-reconfiguration —
``sys.stdin``'s text-mode decoder is set up at interpreter startup and
honoured by every ``sys.stdin.read()`` call, so the only reliable fix is
to bypass it and read raw bytes from ``sys.stdin.buffer`` ourselves.
"""

import sys

# === INLINE_START: input ===


def read_stdin_utf8(max_bytes: int | None = None) -> str:
    """Read piped stdin as raw bytes and decode them as UTF-8.

    Args:
        max_bytes: Optional cap on the number of bytes to read from stdin.
            ``None`` reads until EOF.

    Returns:
        The decoded text.

    Raises:
        UnicodeDecodeError: if the stdin bytes are not valid UTF-8 (e.g.
            binary data accidentally piped in, or a file in a non-UTF-8
            encoding such as UTF-16 / Windows-1252).

    Why this exists
    ---------------
    ``sys.stdin.read()`` is a *text-mode* read — it decodes the underlying
    bytes with whatever encoding Python picked for stdin at interpreter
    startup. On Linux / macOS that is almost always UTF-8. On Windows it
    defaults to the system codepage (cp1252, cp850, …) unless the user
    has explicitly set ``PYTHONIOENCODING=utf-8`` or ``PYTHONUTF8=1`` in
    the environment.

    When a Windows shell user pipes a UTF-8 file in
    (``cat file.txt | jira-comment add PROJ-123 -``), every UTF-8 byte
    happens to also be a valid cp1252 character. The text-mode decode
    *succeeds* with garbage characters (e.g. ``ü`` ``\\xc3\\xbc`` →
    ``Ã¼``), the script re-encodes the garbage as UTF-8 to POST to the
    Jira REST API, and Jira faithfully stores the mojibake.

    ``sys.stdin.buffer`` is the raw byte stream underneath the text-mode
    wrapper. Reading from it bypasses the system codepage entirely;
    decoding the result explicitly as UTF-8 gives back what the caller
    intended regardless of the host's locale.

    See also: PR #61 (April 2026) which fixed the sibling problem on
    ``stdout`` / ``stderr`` and motivated the duplicate-Jira-comment
    incident.
    """
    buffer = sys.stdin.buffer
    if max_bytes is None:
        data = buffer.read()
    else:
        data = buffer.read(max_bytes)
    return data.decode("utf-8")


# === INLINE_END: input ===
