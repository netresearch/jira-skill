"""Stdin helpers for Jira CLI scripts that accept piped input.

This module is the input-side companion to :mod:`lib.output`, which
reconfigures ``stdout`` / ``stderr`` to UTF-8 on Windows at import time
(see PR #61). On the input side we cannot rely on auto-reconfiguration —
``sys.stdin``'s text-mode decoder is set up at interpreter startup and
honoured by every ``sys.stdin.read()`` call, so the only reliable fix is
to read through our own UTF-8 decoder wrapped around ``sys.stdin.buffer``.
"""

import sys

# === INLINE_START: input ===


def read_stdin_utf8(max_chars: int | None = None) -> str:
    """Read piped stdin as text, forcing UTF-8 regardless of host locale.

    Args:
        max_chars: Optional cap on the number of *characters* to read from
            stdin. ``None`` reads until EOF. The cap counts decoded
            characters (not bytes), matching the semantics of the
            ``sys.stdin.read(n)`` this helper replaces.

    Returns:
        The decoded text, with universal newline translation applied
        (``\\r\\n`` / ``\\r`` → ``\\n``).

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

    We rebuild the text wrapper ourselves: ``io.TextIOWrapper`` around the
    raw ``sys.stdin.buffer`` with ``encoding="utf-8"`` pinned. This forces
    UTF-8 no matter the host codepage, while keeping the two text-mode
    properties callers rely on:

    * **Character-based capping.** ``read(max_chars)`` returns whole
      characters, so it never splits a multi-byte UTF-8 sequence at the
      cap boundary (which would raise a spurious ``UnicodeDecodeError`` and
      mask the real "input too large" condition). The cap also stays a
      character count, matching the ``len(text) > max_size`` checks at the
      call sites.
    * **Universal newlines.** ``\\r\\n`` is translated to ``\\n`` exactly as
      the original text-mode read did, so Windows line endings don't leak
      into Jira content.

    ``detach()`` releases ``sys.stdin.buffer`` without closing it, so the
    wrapper's garbage collection can't tear down the process's stdin.

    See also: PR #61 (April 2026) which fixed the sibling problem on
    ``stdout`` / ``stderr`` and motivated the duplicate-Jira-comment
    incident.
    """
    import io

    wrapper = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8")
    try:
        if max_chars is None:
            return wrapper.read()
        return wrapper.read(max_chars)
    finally:
        wrapper.detach()


# === INLINE_END: input ===
