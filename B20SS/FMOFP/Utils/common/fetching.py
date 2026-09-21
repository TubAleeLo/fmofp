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