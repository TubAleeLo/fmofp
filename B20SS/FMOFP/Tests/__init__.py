"""Test package bootstrap.

Exists for one reason: force UTF-8 on stdout and stderr for every suite.

The suites print box-drawing separators and check/cross marks (7,452 non-ASCII
characters across 30 files, 7,222 of them U+2500 alone). When a suite's stdout
is a PIPE -- which it always is under run_all_tests.py, and often is when a
developer redirects output -- Python picks the locale encoding for it, and on
Windows that is cp1252. The first such print() then raises UnicodeEncodeError
before the suite has asserted anything, and the handler raises again trying to
print the failure marker. Nine of the 28 suites died that way.

run_all_tests.py sets PYTHONIOENCODING for the children it launches, which
fixes runs through the runner. This covers every other invocation -- notably
`python -m FMOFP.Tests.<suite>` run directly -- because importing any
FMOFP.Tests submodule imports this first.

reconfigure() overrides PYTHONIOENCODING, so it is authoritative wherever it
can run at all; a closed or exotic stream simply keeps its current encoding.
"""

import sys


def force_utf8_stdio():
    """Best effort: make stdout/stderr encode the glyphs the suites print."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass


force_utf8_stdio()
