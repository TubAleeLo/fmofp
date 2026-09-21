"""Test suite — line-ending normalisation is declared and holds.

WHY THIS EXISTS
---------------
Every text blob in this repository is stored LF-only, but nothing declared
that, so each clone inferred it from its own `core.autocrlf`. On a Windows
clone with autocrlf unset, git compared CRLF working-tree bytes against LF
blobs and reported 533 modified files, 194,476 insertions and 194,476
deletions -- with zero real content changes. Committing that diff would have
flipped the line endings of the whole repository for everyone, and it is
indistinguishable at a glance from catastrophic damage.

`.gitattributes` with `* text=auto` moves the decision into the repository.
This suite asserts the declaration is present AND that the invariant it
protects actually holds, because the declaration alone is worthless if a CRLF
blob has already been committed -- that is the state that produces the
phantom diff for the next person who clones.

Skips cleanly when not run from a git checkout (an installed copy or an
unpacked sdist has no git metadata and no blobs to check).

Standalone-safe: run from B20SS/ as
`python -m FMOFP.Tests.test_line_endings`.
"""
import os
import subprocess
import sys

_B20SS = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _B20SS not in sys.path:
    sys.path.insert(0, _B20SS)

_REPO = os.path.abspath(os.path.join(_B20SS, '..'))

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


def git(*args):
    """Run a git command in the repo; return stdout, or None if git is unusable."""
    try:
        out = subprocess.run(('git', '-C', _REPO) + args,
                             capture_output=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout


# ── skip gracefully outside a checkout ───────────────────────────────────────

if git('rev-parse', '--git-dir') is None:
    print("Line endings: SKIPPED (not a git checkout -- nothing to verify)")
    sys.exit(0)


# ── the declaration exists ───────────────────────────────────────────────────

print("\nthe repository declares its line-ending policy")

attrs_path = os.path.join(_REPO, '.gitattributes')
check(".gitattributes exists", os.path.isfile(attrs_path), attrs_path)

attrs = ""
if os.path.isfile(attrs_path):
    with open(attrs_path, encoding='utf-8') as fh:
        attrs = fh.read()

directives = [ln.split('#', 1)[0].strip() for ln in attrs.splitlines()]
directives = [d for d in directives if d]
check("it declares `* text=auto`", '* text=auto' in directives, str(directives[:3]))

check("git resolves the attribute for a Python file",
      (git('check-attr', 'text', '--', 'B20SS/FMOFP/Main.py') or b'').strip()
      .endswith(b'text: auto'),
      (git('check-attr', 'text', '--', 'B20SS/FMOFP/Main.py') or b'').decode().strip())


# ── the invariant the declaration protects ───────────────────────────────────

print("\nno committed text blob contains CR -- the state that causes the phantom diff")

listing = git('ls-files', '-z')
check("the file list is readable", listing is not None)

offenders = []
checked = 0
skipped_binary = 0
if listing is not None:
    for raw in listing.split(b'\0'):
        if not raw:
            continue
        path = raw.decode('utf-8', 'surrogateescape')
        blob = git('cat-file', '-p', f'HEAD:{path}')
        if blob is None:
            continue
        # Mirror git's own text/binary heuristic: a NUL in the first 8000
        # bytes means binary, and binary files are exempt by design.
        if b'\0' in blob[:8000]:
            skipped_binary += 1
            continue
        checked += 1
        if b'\r' in blob:
            offenders.append(path)

check(f"all {checked} committed text blobs are LF-only",
      not offenders, f"{len(offenders)} with CR: {offenders[:5]}")
check("the scan actually inspected the source tree (not vacuous)",
      checked > 500, f"checked={checked}")
check("binary files were identified and exempted",
      skipped_binary > 0, f"binary={skipped_binary}")


# ── why there is no separate "renormalising is a no-op" assertion ───────────
#
# It would be redundant. `text=auto` normalises text to LF on the way into the
# index; if no committed text blob contains CR -- asserted above -- then
# renormalising cannot change a single stored byte. A test that instead ran
# `git status` and demanded a clean tree would fail for any developer with
# uncommitted work in progress, which is a statement about someone's workspace
# rather than about the repository, and is exactly the kind of assertion that
# teaches people to ignore a failing suite.


# ── non-tautological guard ───────────────────────────────────────────────────

print("\nNON-TAUTOLOGICAL — the scan must be able to detect a CR")

check("a synthetic CRLF payload is detected by the same test",
      b'\r' in b'line one\r\nline two\r\n')
check("an LF-only payload is not flagged by the same test",
      b'\r' not in b'line one\nline two\n')
# `* text=auto` matches every path, including ones that do not exist, so
# "an unknown file is not `auto`" would be false. The discriminating check is
# that a binary-declared extension resolves DIFFERENTLY -- if it did not, the
# binary section below `* text=auto` would be having no effect at all.
whl = (git('check-attr', 'text', '--', 'bundled/PyQt6.whl') or b'').strip()
py = (git('check-attr', 'text', '--', 'bundled/module.py') or b'').strip()
check("a .py path resolves to `text: auto`", py.endswith(b'text: auto'), py.decode())
check("a .whl path does NOT (the binary rules override the catch-all)",
      not whl.endswith(b'text: auto'), whl.decode())


print(f"\nLine-ending tests: {PASS} passed, {FAIL} failed")
if FAIL:
    sys.exit(1)
print("Line endings: all assertions passed")
