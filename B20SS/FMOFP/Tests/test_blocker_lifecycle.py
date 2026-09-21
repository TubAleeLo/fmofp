"""Test suite — boot failure, shutdown drain, event bus teardown (B1, B2, B3, B4).

The four blockers that made the process unable to fail safely.

B1  Flight_Management_Operating_Flight_Program.shutdown() opened with
    `if not self._started: return`, and every early-failure path routes there
    BEFORE _started is ever set. All of them returned immediately, so nothing
    was torn down and -- critically -- nothing stopped the event loop, because
    SystemState.SHUTDOWN is the only thing that reaches
    Initializer._initiate_shutdown and that state is set at the very end of
    stop_system(). The process sat in run_forever() with two 60 FPS QTimers
    firing, never exiting and never returning a status. Separately, the
    shutdown watchdog called os._exit(0) unconditionally, so a fatal error
    terminated with SUCCESS status and no supervisor could tell a crash from a
    clean stop.

B2  initialize_system() logged its exception and returned. Main.initialize()
    awaits it and then sets _initialized = True unconditionally, so boot
    continued into start_FM_system() on a system that never finished
    initializing. The per-component loop was worse: it returned on the first
    failure, after initialize_components() had already set
    _initialization_complete = True.

B3  Every coroutine stop() was scheduled as a fire-and-forget task and the
    SHUTDOWN transition -- which stops the loop -- followed immediately, so
    none of them ran. The same branches also called asyncio.get_event_loop()
    from the "Main_Loop" thread, which raises on 3.12+, aborting stop_system()
    at the first one.

B4  EventBus.stop() joined the processing thread with no timeout while holding
    the class-wide lock that subscribe, unsubscribe, check_health, is_running
    and get_metrics all use.

Standalone-safe: run from B20SS/ as
`python -m FMOFP.Tests.test_blocker_lifecycle`.
"""
import asyncio
import inspect
import os
import sys
import threading
import time
import types

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


# ── B1: a shutdown that never started still stops the loop ───────────────────

print("\nB1 — shutdown on a system that never finished starting")

from FMOFP.Main import Flight_Management_Operating_Flight_Program as FMOFP  # noqa: E402


class _RecordingInitializer:
    def __init__(self):
        self.stop_requests = []

    def request_stop(self, failed=False):
        self.stop_requests.append(failed)

    def get_app(self):
        return None

    def get_loop(self):
        return None


class _RecordingSystemManager:
    def __init__(self, raise_on_stop=False):
        self.stopped = False
        self.waited = False
        self._raise = raise_on_stop

    def stop(self):
        self.stopped = True
        if self._raise:
            raise RuntimeError("half-built system could not be stopped")

    def wait_for_shutdown(self):
        # Blocks forever in the real implementation if stop_system() never
        # reached its SHUTDOWN transition, which is the failed-start case.
        self.waited = True


class _RecordingEventBus:
    def __init__(self):
        self.stopped = False

    def stop(self):
        self.stopped = True


def _never_started_app(**kw):
    """The real shutdown() bound to a never-started instance.

    Built without __init__ so the test does not boot a whole system: shutdown()
    touches only these attributes, and running the REAL method is the point --
    a test against a reimplementation would not have caught the original guard.
    """
    app = FMOFP.__new__(FMOFP)
    app._initializer = _RecordingInitializer()
    app.system_manager = _RecordingSystemManager(**kw)
    app.event_bus = _RecordingEventBus()
    app._started = False          # never started
    app._initialized = False
    app._shutdown_begun = False
    app.running = False
    app._keep_running = True
    app._check_timer = None
    app.shutdown_event = threading.Event()
    return app


app = _never_started_app()
asyncio.run(app.shutdown())

check("shutdown() on a never-started system stops the event loop",
      app._initializer.stop_requests != [],
      "nothing requested a stop -- the process would hang in run_forever (B1)")
check("a failed start is reported as a failure, not a clean stop",
      app._initializer.stop_requests == [True],
      str(app._initializer.stop_requests))
check("shutdown() still tears down the system manager",
      app.system_manager.stopped)
check("shutdown() still stops the event bus", app.event_bus.stopped)
check("shutdown() does not wait on a shutdown event that will never be set",
      not app.system_manager.waited,
      "wait_for_shutdown() was called on a system that never started (B1)")
check("the shutdown event is set so anything waiting is released",
      app.shutdown_event.is_set())

# A component that cannot be stopped must not prevent the loop from stopping.
app = _never_started_app(raise_on_stop=True)
asyncio.run(app.shutdown())
check("a failure while stopping still stops the loop",
      app._initializer.stop_requests == [True],
      str(app._initializer.stop_requests))
check("a failure while stopping does not prevent the event bus stopping",
      app.event_bus.stopped)

# Re-entrancy: two signals arriving together must not run the sequence twice.
app = _never_started_app()


async def _double_shutdown():
    await asyncio.gather(app.shutdown(), app.shutdown())


asyncio.run(_double_shutdown())
check("a second concurrent shutdown() does not re-run the stop sequence",
      len(app._initializer.stop_requests) == 1,
      str(app._initializer.stop_requests))


# ── B1: the exit status ──────────────────────────────────────────────────────

print("\nB1 — exit status reflects failure")

from FMOFP.core import initializer as INIT  # noqa: E402

probe = INIT.Initializer.__new__(INIT.Initializer)
probe._shutdown_started = False
probe._exit_status = 0
probe._loop = None

check("a fresh initializer reports success", probe.get_exit_status() == 0)
probe._initiate_shutdown(failed=False)
check("a clean shutdown keeps status 0", probe.get_exit_status() == 0)

probe = INIT.Initializer.__new__(INIT.Initializer)
probe._shutdown_started = False
probe._exit_status = 0
probe._loop = None
probe._initiate_shutdown(failed=True)
check("a failed shutdown sets status 1", probe.get_exit_status() == 1,
      str(probe.get_exit_status()))

# An ERROR arriving during an already-running shutdown still means failure.
probe._initiate_shutdown(failed=True)
check("a failure recorded after shutdown began is still a failure",
      probe.get_exit_status() == 1)

probe2 = INIT.Initializer.__new__(INIT.Initializer)
probe2._shutdown_started = False
probe2._exit_status = 0
probe2._loop = None
probe2._initiate_shutdown(failed=False)
probe2._initiate_shutdown(failed=True)
check("a failure after a clean shutdown began upgrades the status",
      probe2.get_exit_status() == 1, str(probe2.get_exit_status()))

_init_src = inspect.getsource(INIT)
_init_code = '\n'.join(line for line in _init_src.split('\n')
                       if not line.lstrip().startswith('#'))
check("the shutdown watchdog no longer hardcodes os._exit(0)",
      'os._exit(0)' not in _init_code,
      "a crash would exit with SUCCESS status again (B1)")
check("the watchdog exits with the recorded status",
      'os._exit(self._exit_status)' in _init_code)
check("logging is flushed before the watchdog force-exits",
      'logging.shutdown()' in _init_code,
      "the lines explaining the failure are lost (B1)")
check("_handle_error_state marks the shutdown as failed",
      '_initiate_shutdown(failed=True)' in _init_code)


# ── B2: initialization failure propagates ────────────────────────────────────

print("\nB2 — initialization failure is not swallowed")

from FMOFP.core.system_manager import get_system_manager  # noqa: E402
from FMOFP.Utils.common.system_states import SystemState  # noqa: E402

sm = get_system_manager()


class _FailingComponent:
    def initialize(self):
        raise RuntimeError("component refused to initialize")


# Record state transitions rather than firing them: a real ERROR transition
# reaches Initializer._handle_error_state, which arms a watchdog that would
# force-exit this test process.
recorded_states = []
real_set_state = sm.state_manager.set_state
sm.state_manager.set_state = lambda state: recorded_states.append(state)

real_initialize_components = sm.initialize_components


def _one_failing_component():
    sm.components.clear()
    sm.components['deliberately_failing'] = _FailingComponent()


sm.initialize_components = _one_failing_component
sm._initialization_complete = False

raised = None
try:
    asyncio.run(sm.initialize_system())
except Exception as exc:
    raised = exc
finally:
    sm.initialize_components = real_initialize_components
    sm.state_manager.set_state = real_set_state

check("a component that fails to initialize aborts initialize_system()",
      raised is not None,
      "the failure was swallowed and boot would continue (B2)")
check("the failing component is named in the error",
      raised is not None and 'deliberately_failing' in str(raised), str(raised))
check("the system is put into the ERROR state",
      SystemState.ERROR in recorded_states, str(recorded_states))
check("initialization is NOT marked complete after a component failure",
      sm._initialization_complete is False,
      "the flag says boot finished on a half-initialized system (B2)")
check("the system never reaches INITIALIZED",
      SystemState.INITIALIZED not in recorded_states, str(recorded_states))

_sm_src = inspect.getsource(sys.modules['FMOFP.core.system_manager'])
_sm_code = '\n'.join(line for line in _sm_src.split('\n')
                     if not line.lstrip().startswith('#'))
check("initialize_system re-raises rather than returning",
      'Error during system initialization' in _sm_code
      and _sm_code.count('raise') > 0)


# ── B3: shutdown drains the coroutine stops ──────────────────────────────────

print("\nB3 — coroutine stops are drained, not discarded")

check("stop_system no longer calls asyncio.get_event_loop() per branch",
      _sm_code.count('asyncio.get_event_loop()') <= 1,
      f"found {_sm_code.count('asyncio.get_event_loop()')} call sites")
check("SystemManager exposes a drain for loop-thread callers",
      hasattr(sm, 'await_stop_tasks'))
check("SystemManager exposes a drain for off-loop callers",
      hasattr(sm, 'wait_for_stop_tasks'))


class _AsyncStopComponent:
    def __init__(self, delay=0.05):
        self.delay = delay
        self.stopped = False

    async def stop(self):
        await asyncio.sleep(self.delay)
        self.stopped = True


async def _drain_on_loop():
    component = _AsyncStopComponent()
    sm._stop_waiters = []
    scheduled = sm._schedule_stop(component, 'probe')
    # Before the drain the stop has not finished -- that is the whole point:
    # pre-fix, SHUTDOWN followed immediately and it never would.
    not_yet = not component.stopped
    await sm.await_stop_tasks(timeout=2.0)
    return scheduled, not_yet, component.stopped


scheduled, not_yet, stopped = asyncio.run(_drain_on_loop())
check("a coroutine stop is scheduled on the loop", scheduled)
check("the stop has not completed before the drain", not_yet)
check("await_stop_tasks runs the stop to completion",
      stopped, "the component's stop() never ran (B3)")


def _drain_off_loop():
    """The ERROR path: stop_system runs on the 'Main_Loop' thread."""
    loop = asyncio.new_event_loop()
    ready = threading.Event()

    def _run():
        asyncio.set_event_loop(loop)
        loop.call_soon(ready.set)
        loop.run_forever()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    ready.wait(timeout=5)

    component = _AsyncStopComponent()
    sm._stop_waiters = []
    real_loop_getter = sm._shutdown_loop
    sm._shutdown_loop = lambda: loop
    try:
        # This whole block runs on a thread with no event loop of its own,
        # which is what made asyncio.get_event_loop() raise pre-fix.
        result = {}

        def _worker():
            try:
                result['scheduled'] = sm._schedule_stop(component, 'probe')
                sm.wait_for_stop_tasks(timeout=2.0)
                result['stopped'] = component.stopped
            except Exception as exc:     # noqa: BLE001 - recorded, asserted below
                result['error'] = exc

        w = threading.Thread(target=_worker)
        w.start()
        w.join(timeout=10)
        return result
    finally:
        sm._shutdown_loop = real_loop_getter
        loop.call_soon_threadsafe(loop.stop)
        t.join(timeout=5)


off_loop = _drain_off_loop()
check("scheduling a stop from a thread with no event loop does not raise",
      'error' not in off_loop, str(off_loop.get('error')))
check("the stop is scheduled from an off-loop thread",
      off_loop.get('scheduled') is True, str(off_loop))
check("wait_for_stop_tasks runs the stop to completion off the loop",
      off_loop.get('stopped') is True,
      "the ERROR path abandoned every remaining stop (B3)")


# ── B4: the event bus stops without deadlocking ──────────────────────────────

print("\nB4 — EventBus teardown")

from FMOFP.core.event_driven_communication import EventBus, Event  # noqa: E402

bus = EventBus()
if not bus.is_running():
    bus.start()

released = threading.Event()
blocked_entered = threading.Event()


def _blocking_subscriber(_data):
    blocked_entered.set()
    released.wait(timeout=30)


bus.subscribe('b4_probe', _blocking_subscriber)
bus.publish(Event('b4_probe', {'x': 1}))
blocked_entered.wait(timeout=10)

# While a subscriber callback is blocked inside the processing thread, the
# lock-taking accessors must still answer. Pre-fix, stop() held the lock across
# an unbounded join, so these wedged too.
other_thread_result = {}


def _probe_accessors():
    try:
        other_thread_result['running'] = bus.is_running()
        other_thread_result['health'] = bus.check_health()
    except Exception as exc:          # noqa: BLE001 - recorded, asserted below
        other_thread_result['error'] = exc


start = time.time()
stopper = threading.Thread(target=bus.stop, daemon=True)
stopper.start()
time.sleep(0.2)
probe_thread = threading.Thread(target=_probe_accessors, daemon=True)
probe_thread.start()
probe_thread.join(timeout=5)
elapsed_to_probe = time.time() - start

check("health accessors still answer while stop() is joining",
      'running' in other_thread_result and 'error' not in other_thread_result,
      "stop() is holding the shared lock across the join again (B4)")
check("the accessor answered promptly", elapsed_to_probe < 5.0,
      f"{elapsed_to_probe:.1f}s")

stopper.join(timeout=EventBus.STOP_JOIN_TIMEOUT + 5)
check("stop() returns even though a subscriber is blocked",
      not stopper.is_alive(),
      "stop() joined an unresponsive thread forever (B4)")
check("stop() is bounded by the documented timeout",
      time.time() - start < EventBus.STOP_JOIN_TIMEOUT + 5,
      f"{time.time() - start:.1f}s")
released.set()

_bus_src = inspect.getsource(sys.modules['FMOFP.core.event_driven_communication'])
_bus_code = '\n'.join(line for line in _bus_src.split('\n')
                      if not line.lstrip().startswith('#'))
check("the join is bounded", 'join(timeout=' in _bus_code)
check("no unbounded join remains", 'self.thread.join()' not in _bus_code)
check("_handle_event snapshots the subscriber list under the lock",
      'callbacks = list(self.subscribers.get(' in _bus_code,
      "iterating the live list can raise mid-dispatch (B4)")


# ── non-tautological guard ───────────────────────────────────────────────────

print("\nNON-TAUTOLOGICAL — pre-fix behaviour must fail these")

# B1: the pre-fix guard really did return before doing anything.
pre_fix_reached = []


async def _pre_fix_shutdown(self):
    if not self._started:
        return
    pre_fix_reached.append(True)


stub = types.SimpleNamespace(_started=False)
asyncio.run(_pre_fix_shutdown(stub))
check("the pre-fix guard really did skip the whole body (proves B1 bites)",
      pre_fix_reached == [])

# B3: a fire-and-forget task really is discarded when the loop stops straight
# after scheduling it.
discarded = {'ran': False}


async def _slow():
    await asyncio.sleep(0.05)
    discarded['ran'] = True


async def _schedule_and_return():
    asyncio.get_running_loop().create_task(_slow())
    # returning immediately is what stop_system did before transitioning to
    # SHUTDOWN, which stops the loop


asyncio.run(_schedule_and_return())
check("a fire-and-forget stop really is lost when the loop ends "
      "(proves B3 bites)", discarded['ran'] is False)


print(f"\nLifecycle tests: {PASS} passed, {FAIL} failed")
if FAIL:
    sys.exit(1)
print("Boot failure, shutdown drain and event bus teardown: all assertions passed")
