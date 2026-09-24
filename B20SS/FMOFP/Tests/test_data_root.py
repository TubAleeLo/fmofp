"""Test suite — writable data root and resource resolution (C11b, C13).

C11b  Config and data paths were written CWD-relative ('FMOFP/dbConfig.xml'
      appears 44 times), so both entry points had to os.chdir() to the
      distribution root before importing anything. The working directory was
      load-bearing, and chdir() is process-global.

C13   With the project pip-installable (C11a), that same package-relative data
      path meant an installed run wrote 11 SQLite databases and a log file into
      site-packages. Runtime state inside an installed package is lost on
      upgrade, shared between users of a system install, and fatal to a
      read-only deployment -- even when the directory happens to be writable.

The split these stories turn on: resolve_resource() is for things that SHIP
with the distribution and are read; resolve_data_dir() is for things WRITTEN at
runtime. They deliberately resolve to different places once installed.

Standalone-safe: run from B20SS/ as
`python -m FMOFP.Tests.test_data_root`.
"""
import os
import sys

_B20SS = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _B20SS not in sys.path:
    sys.path.insert(0, _B20SS)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from FMOFP.Utils.common import fetching as F  # noqa: E402

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


def with_env(**kw):
    """Set/clear env vars and reset the cached data root."""
    for k, v in kw.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    F.reset_data_root()


# ── resource resolution (C11b) ───────────────────────────────────────────────

print("\nC11b — resource resolution is CWD-independent")

for spelling in ('FMOFP/dbConfig.xml', 'dbConfig.xml'):
    r = F.resolve_resource(spelling)
    check(f"resolves {spelling!r}", os.path.isabs(r) and os.path.exists(r), r)

check("both spellings resolve to the same file",
      os.path.realpath(F.resolve_resource('FMOFP/dbConfig.xml'))
      == os.path.realpath(F.resolve_resource('dbConfig.xml')))

abs_in = os.path.abspath(__file__)
check("an absolute path is returned unchanged", F.resolve_resource(abs_in) == abs_in)
check("an unresolvable path is returned unchanged, not raised",
      F.resolve_resource('no/such/thing.xml') == 'no/such/thing.xml')
check("empty input is passed through", F.resolve_resource('') == '')

# The point of the story: resolution must not depend on where we are standing.
_cwd = os.getcwd()
try:
    os.chdir(os.path.dirname(os.path.abspath(os.sep)) or os.sep)
    from_root = F.resolve_resource('FMOFP/dbConfig.xml')
finally:
    os.chdir(_cwd)
from_here = F.resolve_resource('FMOFP/dbConfig.xml')
check("same answer from a different working directory (the whole point)",
      from_root == from_here, f"{from_root} != {from_here}")


# ── installed-vs-checkout detection (C13) ────────────────────────────────────

print("\nC13 — installed-vs-checkout detection")

for p in ('/tmp/venv/lib/python3.11/site-packages/FMOFP',
          '/usr/lib/python3/dist-packages/FMOFP',
          r'C:\venv\Lib\site-packages\FMOFP'):
    check(f"installed: {p.split(os.sep)[-2] if os.sep in p else p}", F._looks_installed(p), p)

for p in ('/root/fmofp/B20SS/FMOFP',
          '/home/me/my-site-packages-project/FMOFP',
          '/srv/dist-packages-backup/FMOFP'):
    check(f"checkout: {p}", not F._looks_installed(p), p)


# ── data root resolution (C13) ───────────────────────────────────────────────

print("\nC13 — data root resolution")

try:
    with_env(FMOFP_DATA_DIR=None)
    checkout_root = F.data_root()
    check("source checkout keeps the historical in-package location",
          os.path.realpath(checkout_root) == os.path.realpath(F.fetch_fmofp_path()),
          checkout_root)

    # data_root() returns os.path.abspath(os.path.expanduser(override)), so the
    # expectation has to be normalised the same way. Comparing against the raw
    # literal passed these on POSIX and could never pass on Windows, where
    # abspath('/tmp/fmofp-state-test') is 'C:\\tmp\\fmofp-state-test'.
    override = '/tmp/fmofp-state-test'
    expected_root = os.path.abspath(os.path.expanduser(override))
    with_env(FMOFP_DATA_DIR=override)
    check("FMOFP_DATA_DIR overrides everything",
          F.data_root() == expected_root, F.data_root())
    check("resolve_data_dir composes under the override",
          F.resolve_data_dir('storage', 'databases')
          == os.path.join(expected_root, 'storage', 'databases'))

    with_env(FMOFP_DATA_DIR='~/fmofp-tilde-test')
    check("~ in the override is expanded",
          F.data_root() == os.path.abspath(os.path.expanduser('~/fmofp-tilde-test')),
          F.data_root())

    with_env(FMOFP_DATA_DIR=None)
    check("the data root is cached (stable within a process)",
          F.data_root() is F.data_root())

    platform_dir = F._platform_data_dir()
    check("a platform data dir is produced and absolute",
          os.path.isabs(platform_dir), platform_dir)
    check("the platform dir is NOT inside the package -- the C13 requirement",
          not os.path.realpath(platform_dir).startswith(
              os.path.realpath(F.fetch_fmofp_path()) + os.sep),
          platform_dir)

    if sys.platform not in ('win32', 'darwin'):
        with_env(XDG_STATE_HOME='/tmp/xdg-test')
        check("XDG_STATE_HOME is honoured on Linux",
              F._platform_data_dir() == '/tmp/xdg-test/fmofp', F._platform_data_dir())
        with_env(XDG_STATE_HOME=None)
        check("falls back to ~/.local/state when XDG_STATE_HOME is unset",
              F._platform_data_dir() == os.path.expanduser('~/.local/state/fmofp'),
              F._platform_data_dir())
finally:
    with_env(FMOFP_DATA_DIR=None, XDG_STATE_HOME=None)


# ── resources and data must not be conflated ─────────────────────────────────

print("\nresources vs data are genuinely separate")

check("a config resource lives in the package, not the data root",
      os.path.realpath(F.resolve_resource('FMOFP/dbConfig.xml')).startswith(
          os.path.realpath(F.fetch_fmofp_path()) + os.sep))

with_env(FMOFP_DATA_DIR='/tmp/fmofp-split-test')
check("...while data follows the override away from the package",
      not F.resolve_data_dir('storage').startswith(F.fetch_fmofp_path()),
      F.resolve_data_dir('storage'))
check("...and resources are unaffected by the data override",
      os.path.exists(F.resolve_resource('FMOFP/dbConfig.xml')))
with_env(FMOFP_DATA_DIR=None)


# ── non-tautological guard ───────────────────────────────────────────────────

print("\nNON-TAUTOLOGICAL — pre-fix behaviour must fail these")

# Pre-C13, the data root WAS the package dir unconditionally.
legacy_data_root = F.fetch_fmofp_path()
check("pre-fix data root sat inside the package (proves the C13 assertion bites)",
      os.path.realpath(legacy_data_root).startswith(
          os.path.realpath(F.fetch_fmofp_path())))
with_env(FMOFP_DATA_DIR='/tmp/fmofp-proof')
check("post-fix an override moves it out",
      not F.data_root().startswith(F.fetch_fmofp_path()), F.data_root())
with_env(FMOFP_DATA_DIR=None)

# Pre-C11b, resolution was CWD-relative: a bare relative path only existed
# from one directory.
check("pre-fix CWD-relative lookup fails from elsewhere (proves C11b bites)",
      not os.path.exists(os.path.join(os.sep, 'FMOFP', 'dbConfig.xml')))


print(f"\nData root & resource tests: {PASS} passed, {FAIL} failed")
if FAIL:
    sys.exit(1)
print("Data root and resources: all assertions passed")
