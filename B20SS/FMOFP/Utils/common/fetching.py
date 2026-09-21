import os
import sys

def fetch():
    """Make the FMOFP package importable from a source checkout.

    Story C12: this used to insert TWO sys.path entries -- the distribution root
    AND B20SS/FMOFP itself -- so the same file could be imported both as
    `Utils.common.fetching` and as `FMOFP.Utils.common.fetching`. Python keys
    sys.modules by dotted name, so those spellings loaded one source file twice
    and produced two independent module objects, and with them two independent
    copies of every class defined there. isinstance() checks, `is` comparisons
    and every __new__-based singleton silently diverged across the boundary, and
    the codebase carried a sys.meta_path finder (Utils/dual_path_compat.py)
    purely to paper over it.

    Every import is now FMOFP-prefixed, so only the distribution root is needed
    and the ambiguity cannot arise. The shim is deleted.

    Only source checkouts need this at all; an installed package is already on
    sys.path via site-packages.
    """
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

def fetch_project_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))

def fetch_fmofp_path():
    return os.path.join(fetch_project_root(), 'FMOFP')


def resolve_resource(path):
    """Resolve a config/data path without depending on the process CWD (story C11b).

    Most config paths in this codebase are written as CWD-relative literals --
    `'FMOFP/dbConfig.xml'` appears 44 times on its own -- which only worked
    because both entry points used to call os.chdir() to the distribution root
    before importing anything (removed in the same story). That made the application unable to run without first
    relocating the whole process, and it broke outright once the package could
    be pip-installed: an installed run chdir'd into site-packages and wrote its
    databases there.

    Accepts every spelling already in use and returns an absolute path:

        'FMOFP/dbConfig.xml'   distribution-root relative (the historical form)
        'dbConfig.xml'         package relative
        '/abs/path.xml'        returned unchanged

    A path that matches nothing is returned unchanged rather than raising, so a
    caller passing something genuinely CWD-relative keeps the old behaviour and
    fails where it used to fail, with its own error message, instead of here.
    """
    if not path:
        return path
    if os.path.isabs(path):
        return path

    for candidate in (os.path.join(fetch_project_root(), path),
                      os.path.join(fetch_fmofp_path(), path)):
        if os.path.exists(candidate):
            return candidate
    return path


_data_root_cache = None


def _looks_installed(package_dir):
    """True when the package lives in an installed location rather than a checkout."""
    parts = package_dir.replace('\\', '/').lower().split('/')
    return 'site-packages' in parts or 'dist-packages' in parts


def _platform_data_dir():
    """The conventional per-user writable data location for this OS."""
    if sys.platform == 'win32':
        base = os.environ.get('LOCALAPPDATA') or os.path.expanduser(r'~\AppData\Local')
        return os.path.join(base, 'FMOFP')
    if sys.platform == 'darwin':
        return os.path.expanduser('~/Library/Application Support/FMOFP')
    base = os.environ.get('XDG_STATE_HOME') or os.path.expanduser('~/.local/state')
    return os.path.join(base, 'fmofp')


def data_root():
    """Root directory for everything this program WRITES (story C13).

    Databases, logs, lock files and operation-tracking files all live under
    here. Configuration and other read-only resources do not -- those ship with
    the distribution and are resolved by resolve_resource().

    Resolution order, highest first:

      1. FMOFP_DATA_DIR, if set. An explicit answer always wins, which is what
         makes the program deployable into a container or a service account's
         state directory without patching it.

      2. The platform's per-user data location, when the package is INSTALLED
         (its path is under site-packages/dist-packages):
             Windows  %LOCALAPPDATA%\FMOFP
             macOS    ~/Library/Application Support/FMOFP
             Linux    $XDG_STATE_HOME/fmofp, else ~/.local/state/fmofp
         This is the case story C11a made visible: an installed run previously
         created 11 SQLite databases and a log file inside site-packages,
         because the data path was the package path. Writing runtime state into
         an installed package is wrong even when the directory happens to be
         writable -- it is lost on upgrade, shared between users of a system
         install, and breaks a read-only deployment outright.

      3. The package directory itself, for a source checkout. This is the
         historical behaviour and is kept deliberately: a developer running
         from a clone expects logs and databases next to the code, .gitignore
         already covers both, and silently relocating them to a hidden
         per-user directory would be a worse surprise than the one being fixed.

    Cached, so the answer cannot change mid-run. Tests use reset_data_root().
    """
    global _data_root_cache
    if _data_root_cache is None:
        override = os.environ.get('FMOFP_DATA_DIR')
        if override:
            _data_root_cache = os.path.abspath(os.path.expanduser(override))
        else:
            package_dir = fetch_fmofp_path()
            _data_root_cache = (_platform_data_dir() if _looks_installed(package_dir)
                                else package_dir)
    return _data_root_cache


def reset_data_root():
    """Drop the cached data root. For tests only."""
    global _data_root_cache
    _data_root_cache = None


def resolve_data_dir(*parts):
    """Absolute path to a writable location under data_root() (story C11b/C13).

    Split from resolve_resource() because the two have different lifecycles:
    resources are read-only and ship with the distribution, data is written at
    runtime. Every writer in the codebase goes through here, which is what made
    C13 a change to one function rather than another hunt for call sites.
    """
    return os.path.join(data_root(), *parts)
