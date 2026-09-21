"""Test suite — singleton re-initialisation, run-once scope, import index (B5, B11, B12).

Three production blockers that share a shape: work that is supposed to happen
exactly once, and a guard that did not actually make it so.

B5  DatabaseManager.__init__ ran its ENTIRE body on every construction. Only
    `self.config_path = ...` sat inside the `if not self.initialized:` guard;
    `__new__` returns the same singleton, so all 43 non-test call sites re-ran
    load_config, built a fresh ThreadPoolExecutor(max_workers=20) over the top
    of the previous one, and replaced self.systems wholesale -- orphaning every
    pooled SQLite connection in it. Three of those call sites are on the boot
    and shutdown path.

B11 Operation tracking wrote marker FILES that outlived the process, and
    nothing ever removed them: clear_operation_tracking() had zero callers.
    From the second run on any machine onward, every tracked operation was
    skipped forever -- the database manager was never initialised, and
    messageRateConfig.xml was never read again for the life of the install.

B12 Utils/common/paths built its import index at MODULE IMPORT time, walking
    up to the first directory containing an 'FMOFP' child and then os.walk +
    MD5 + ast.parse'ing everything below it. In an installed package that root
    is site-packages, so boot parsed PyQt6, numpy and scipy. userCLI built a
    second instance of its own, on the live boot path.

Standalone-safe: run from B20SS/ as
`python -m FMOFP.Tests.test_blocker_singleton_and_state`.
"""
import os
import sys

_B20SS = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _B20SS not in sys.path:
    sys.path.insert(0, _B20SS)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

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


# ── B5: DatabaseManager re-initialisation is a no-op ─────────────────────────

print("\nB5 — repeat construction of the DatabaseManager singleton")

from FMOFP.storage.DBM import DatabaseManager  # noqa: E402

dbm1 = DatabaseManager('FMOFP/dbConfig.xml')
pool1 = dbm1.worker_pool
systems1 = dbm1.systems
config_path1 = dbm1.config_path

check("first construction initialises", dbm1.initialized is True)
check("first construction builds a worker pool", pool1 is not None)

dbm2 = DatabaseManager('FMOFP/dbConfig.xml')

check("__new__ still returns the same instance", dbm2 is dbm1)
check("worker pool is NOT replaced on re-construction",
      dbm2.worker_pool is pool1,
      "a second ThreadPoolExecutor was created; the first leaks (B5)")
check("systems dict is NOT replaced on re-construction",
      dbm2.systems is systems1,
      "pooled SQLite connections in the old dict were orphaned (B5)")
check("config_path survives re-construction", dbm2.config_path == config_path1)

# Ten more constructions must be free. Pre-fix this produced ten more thread
# pools and discarded ten more sets of connections.
pools = set()
for _ in range(10):
    pools.add(id(DatabaseManager('FMOFP/dbConfig.xml').worker_pool))
check("10 further constructions create 0 further worker pools",
      pools == {id(pool1)}, f"{len(pools)} distinct pools seen")


# ── B11: run-once tracking is scoped to the process ──────────────────────────

print("\nB11 — operation tracking scope")

from FMOFP.Utils.common import operation_tracker as OT  # noqa: E402

calls = []
OT.clear_operation_tracking('b11_probe', 'unit')

OT.track_operation('b11_probe', 'unit', lambda: calls.append('ran'))
check("first call in a process runs the operation", calls == ['ran'])

OT.track_operation('b11_probe', 'unit', lambda: calls.append('ran-again'))
check("second call in the same process is skipped", calls == ['ran'])

check("is_operation_completed reports it", OT.is_operation_completed('b11_probe', 'unit'))

OT.clear_operation_tracking('b11_probe', 'unit')
check("clear_operation_tracking actually clears it",
      not OT.is_operation_completed('b11_probe', 'unit'))

OT.track_operation('b11_probe', 'unit', lambda: calls.append('ran-after-clear'))
check("a cleared operation runs again (what the 5-minute message-rate "
      "reload thread depends on)", calls == ['ran', 'ran-after-clear'])

# The defining property: no marker survives the process. Nothing this module
# writes may live on disk, or a second run inherits the first run's decisions.
check("tracker exposes no on-disk tracking directory",
      not hasattr(OT, 'TRACKING_DIR'),
      "a persistent marker directory is back (B11)")

import inspect  # noqa: E402
_tracker_src = inspect.getsource(OT)
for forbidden in ('os.path.exists(track_file)', 'os.replace(temp_file', 'os.listdir(TRACKING_DIR)'):
    check(f"tracker no longer does {forbidden!r}", forbidden not in _tracker_src)


# ── B12: the import index is lazy and package-scoped ─────────────────────────

print("\nB12 — import index construction")

from FMOFP.Utils.common import paths as P  # noqa: E402

# getattr, not attribute access: pre-fix this module had no _paths_instance at
# all (it had an eagerly built `paths_instance`), and a bare access would raise
# rather than report a failure.
check("importing the module builds no index",
      getattr(P, '_paths_instance', 'EAGER') is None,
      "paths() ran at import time again (B12)")

import FMOFP.Utils.debug.userCLI as _userCLI  # noqa: E402,F401

check("importing userCLI builds no index either",
      getattr(P, '_paths_instance', 'EAGER') is None,
      "userCLI constructed paths() at import/boot (B12)")

index = (P.get_paths_instance() if hasattr(P, 'get_paths_instance')
         else P.paths_instance)
check("the index builds on demand",
      getattr(P, '_paths_instance', None) is not None)

_fmofp_pkg = os.path.join(_B20SS, 'FMOFP')
check("the scan root is the FMOFP package, not its parent",
      os.path.realpath(index.project_root) == os.path.realpath(_fmofp_pkg),
      index.project_root)

# The scan must not be able to reach a sibling of the package. Pre-fix the root
# was the directory CONTAINING FMOFP -- B20SS here, site-packages once
# installed -- so everything beside the package was indexed too.
check("the scan root cannot reach files outside the package",
      not os.path.realpath(_B20SS) == os.path.realpath(index.project_root))

check("environment directories are pruned from the walk",
      {'venv', 'site-packages', 'dist-packages'} <= set(getattr(P.paths, '_SKIP_DIRS', ())),
      str(sorted(getattr(P.paths, '_SKIP_DIRS', ()))))

check("get_import_statement still works through the lazy accessor",
      P.get_import_statement('DatabaseManager', __file__) is not None)


# ── non-tautological guard ───────────────────────────────────────────────────

print("\nNON-TAUTOLOGICAL — pre-fix behaviour must fail these")

# B5: prove the assertion has teeth by showing what the old shape did. Running
# the old body twice really does produce two pools.
import concurrent.futures  # noqa: E402


class _PreFixShape:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.initialized = False
        return cls._instance

    def __init__(self):
        if not self.initialized:           # guard covers only the next line
            self.config_path = 'x'
        self.worker_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.initialized = True


_a = _PreFixShape()
_pool_a = _a.worker_pool
_b = _PreFixShape()
check("pre-fix guard shape really did replace the pool (proves B5 bites)",
      _b.worker_pool is not _pool_a)
_pool_a.shutdown(wait=False)
_b.worker_pool.shutdown(wait=False)

# B11: a file-backed tracker would still report completion after the in-memory
# state is cleared. Ours must not.
OT.clear_operation_tracking()
check("clearing all tracking leaves nothing behind (a file-backed tracker "
      "would still report completed)",
      not OT.is_operation_completed('b11_probe', 'unit'))

# B12: the pre-fix root resolution really did land outside the package.
_legacy_root = os.path.dirname(os.path.abspath(P.__file__))
while _legacy_root != os.path.dirname(_legacy_root):
    if os.path.exists(os.path.join(_legacy_root, 'FMOFP')):
        break
    _legacy_root = os.path.dirname(_legacy_root)
check("pre-fix root resolution lands outside the package (proves B12 bites)",
      os.path.realpath(_legacy_root) != os.path.realpath(index.project_root),
      f"legacy={_legacy_root} current={index.project_root}")


print(f"\nSingleton, run-once and import-index tests: {PASS} passed, {FAIL} failed")
if FAIL:
    sys.exit(1)
print("Singleton, run-once scope and import index: all assertions passed")
