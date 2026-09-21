import os
import sys

def fetch():
    # Determine project root dynamically
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
    sys.path.insert(0, project_root)
    fmofp_path = os.path.join(project_root, 'FMOFP')
    sys.path.insert(0, fmofp_path)

    # This module is imported (directly or transitively) by nearly
    # everything in the codebase very early on, which makes fetch()
    # the best available single choke point for installing the
    # dual-path import alias shim -- see Utils/dual_path_compat.py for
    # why this is needed. Installing it here (immediately after the
    # two sys.path entries above are in place) means both "import
    # Systems.X" and "from FMOFP.Systems.X import Y" resolve to the
    # same module/class objects for essentially every entry point in
    # this codebase, without needing to duplicate this call in each
    # one individually.
    try:
        from Utils.dual_path_compat import install as _install_dual_path_alias
        _install_dual_path_alias()
    except ImportError:
        pass  # dual_path_compat not present (e.g. older checkout) -- degrade gracefully

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


def resolve_data_dir(*parts):
    """Absolute path to a writable data location inside the package.

    Split out from resolve_resource() because the two have different futures:
    resources are read-only and ship with the distribution, whereas data
    (databases, logs) is written at runtime and should move out of the package
    entirely -- that is story C13. Routing every writer through here now means
    C13 changes one function instead of hunting call sites again.
    """
    return os.path.join(fetch_fmofp_path(), *parts)

# Add project paths immediately when this module is imported
fetch()



# For debugging purposes
if __name__ == "__main__":
    print(f"Project root: {fetch_project_root()}")
    print(f"FMOFP path: {fetch_fmofp_path()}")