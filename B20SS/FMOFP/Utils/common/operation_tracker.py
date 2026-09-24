"""Process-scoped operation tracking utility.

Guarantees that an operation runs **once per process**. That is what every
caller in this codebase actually needs: initialise the database manager once,
load the message-rate config once, register the startup threads once, build the
command-word map once.

BLOCKER B11 — why this is no longer persistent
----------------------------------------------
This module used to write a marker *file* per operation under a tracking
directory in the data root, and the docstring advertised that as a feature:
"even across application restarts". Nothing ever removed those files --
`clear_operation_tracking()` had zero callers anywhere in the repository, and
nothing cleared the directory at startup -- so from the second run onward on
any given machine, every tracked operation was skipped forever. Three confirmed
consequences:

  * `core/system_manager.py:574` — `_initialize_database_manager()` never ran
    again, so `async_handler.radar_db` stayed None and every radar DB access
    fell into a lazy-recovery error path.
  * `MIL_STD_1553B/Messaging.py:406` — `messageRateConfig.xml` was never read
    again for the life of the installation. The in-memory `_message_rates_loaded`
    flag resets each process, so the cached-value branch was skipped too, and
    the fallback that calls `set_default_rates()` was gated on that same flag --
    leaving the rate table empty. The 5-minute hot-reload thread was dead for
    the same reason. An operator could edit message rates, restart, and see no
    effect, ever.
  * `Utils/common/thread_manager.py:390` — `startup_threads` was empty on every
    later boot, filling the log with "No thread with the name 'X' exists".

The symptom class is the worst kind to support: the product works on a clean
machine and behaves differently on every machine that has run it before.

Per-process state is the correct scope for idempotence within a process. State
that genuinely must outlive the process (a completed schema migration, say)
belongs in a versioned record that something can invalidate -- not in an
unkeyed marker file that nothing ever deletes.
"""

import threading
from datetime import datetime
from typing import Callable, Optional, Any, Dict

from FMOFP.Utils.logger.sys_logger import get_logger

logger = get_logger()

# Thread safety for the completed/in-progress registries.
_file_lock = threading.Lock()

# Operations completed in THIS process, keyed by "<operation_name>::<identifier>",
# valued by the completion timestamp. Guarded by _file_lock. Replaces the marker
# files described above; deliberately not persisted.
_completed: Dict[str, str] = {}

# Operations currently executing, keyed the same way. Guarded by _file_lock.
# Lets a concurrent caller for the same operation wait for the in-flight
# execution to finish (preserving the old blocking semantics) WITHOUT the
# executing thread holding _file_lock across the callback.
_in_progress: Dict[str, threading.Event] = {}


def _key(operation_name: str, identifier: str) -> str:
    return f"{operation_name}::{identifier}"


def track_operation(operation_name: str, identifier: str, perform_operation_fn: Callable) -> Any:
    """Track and execute operations that should only happen once per process.

    Args:
        operation_name: Type of operation (e.g., 'init', 'config', 'setup')
        identifier: Unique identifier for this specific operation
        perform_operation_fn: Function to call if operation hasn't been done

    Returns:
        Result from perform_operation_fn, or None if already performed in this
        process.
    """
    key = _key(operation_name, identifier)

    # DO NOT hold _file_lock across perform_operation_fn(). The original
    # implementation ran the callback inside `with _file_lock:`, so any
    # tracked callback that itself touched this module — e.g.
    # system_manager's _initialize_database_manager, whose
    # DatabaseManager.__init__ → load_config path calls
    # is_operation_completed() — re-acquired the same non-reentrant Lock
    # and self-deadlocked. Because this ran on the qasync event-loop
    # thread during start_async_components(), EVERY boot silently froze
    # the entire asyncio loop right after reaching SystemState.RUNNING
    # (found via live-boot re-verification + thread stack dump, August 2026).
    #
    # Structure: claim the operation under the lock, run the callback with the
    # lock RELEASED, then record completion under the lock again. A concurrent
    # caller for the same operation while it's in flight waits for it to finish
    # and then returns None, matching the old blocking behavior without the
    # deadlock.
    while True:
        with _file_lock:
            if key in _completed:
                logger.debug(f"Operation {operation_name} for {identifier} already performed - skipping")
                return None
            in_flight = _in_progress.get(key)
            if in_flight is None:
                _in_progress[key] = threading.Event()
                break  # we own the operation — go execute it
        # Someone else is executing this operation: wait, then re-check
        # (the completion record will exist if they succeeded).
        in_flight.wait()

    try:
        # Perform the operation (lock NOT held)
        logger.info(f"Performing {operation_name} for {identifier}")
        result = perform_operation_fn()

        with _file_lock:
            _completed[key] = str(datetime.now())

        return result
    finally:
        # Release any waiters and clear the in-progress claim, whether the
        # callback succeeded or raised (on failure nothing is recorded, so a
        # waiter or a later call will re-attempt the operation).
        with _file_lock:
            ev = _in_progress.pop(key, None)
        if ev is not None:
            ev.set()


def is_operation_completed(operation_name: str, identifier: str) -> bool:
    """Check if an operation has already been completed in this process.

    Args:
        operation_name: Type of operation (e.g., 'init', 'config', 'setup')
        identifier: Unique identifier for this specific operation

    Returns:
        bool: True if the operation has been completed, False otherwise
    """
    with _file_lock:
        return _key(operation_name, identifier) in _completed


def mark_operation_completed(operation_name: str, identifier: str) -> bool:
    """Mark an operation as completed without executing a function.

    Args:
        operation_name: Type of operation (e.g., 'init', 'config', 'setup')
        identifier: Unique identifier for this specific operation

    Returns:
        bool: True if the operation was marked as completed, False if it was
        already completed.
    """
    key = _key(operation_name, identifier)
    with _file_lock:
        if key in _completed:
            logger.debug(f"Operation {operation_name} for {identifier} already marked as completed")
            return False
        _completed[key] = str(datetime.now())
        logger.info(f"Marked operation {operation_name} for {identifier} as completed")
        return True


def clear_operation_tracking(operation_name: Optional[str] = None,
                             identifier: Optional[str] = None) -> None:
    """Clear operation tracking records.

    Args:
        operation_name: Optional specific operation to clear
        identifier: Optional specific identifier to clear
    """
    with _file_lock:
        if operation_name and identifier:
            if _completed.pop(_key(operation_name, identifier), None) is not None:
                logger.info(
                    f"Cleared tracking for operation {operation_name} "
                    f"with identifier {identifier}")
        elif operation_name:
            prefix = f"{operation_name}::"
            doomed = [k for k in _completed if k.startswith(prefix)]
            for k in doomed:
                del _completed[k]
            logger.info(
                f"Cleared tracking for {len(doomed)} operations of type {operation_name}")
        else:
            count = len(_completed)
            _completed.clear()
            logger.info(f"Cleared tracking for all {count} operations")
