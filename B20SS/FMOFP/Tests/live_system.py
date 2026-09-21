"""Boot the real FMOFP application in-process and run a test body against it.

WHY THIS EXISTS (PI-1 story C14)
--------------------------------
Ten test files -- the five per-radar suites plus fms_system_test,
flight_control_system_test, predefined_messages_test,
combined_precipitation_vil_flow_test and weather_radar_surveillance_mode_test,
6,991 lines in total -- were excluded from run_all_tests.py because running
them standalone printed "This test should be run via the user CLI 'test'
command" and exited 1. That is two thirds of the project's test code never
executing in CI, covering the largest and most-changed part of the codebase.

They were not neglected. They genuinely need a live system: their subjects are
components reached through SystemManager, and the message paths they exercise
only work once the async handler, routing service and display tree are all
started. Attempts to stand up a partial system fail concretely --
`initialize_components()` alone leaves `AsyncMessageHandler.started` False, and
`start_async_components()` on its own raises "Display tree manager not
initialized".

So this harness does the honest thing: it boots the actual application, the
same way Main.main() does, waits for readiness, runs the test body on that
event loop, and shuts down. A full boot to NORMAL measures ~1.2 s, which is
cheap enough to do per suite.

USAGE
-----
    from FMOFP.Tests.live_system import run_against_live_system

    async def body(sm):
        radar = sm.components['radar_management'].radars['weather_radar']
        ...
        return failures          # 0 means pass

    sys.exit(run_against_live_system(body))

The body receives the started SystemManager and may return an int exit status
(0 = pass) or a bool (True = pass). Anything it raises is reported and becomes
a failure.

NOTES FOR SUITE AUTHORS
-----------------------
  * Run each suite in its own process. The application is full of singletons
    (SystemManager, EventBus, the bus listeners, DatabaseManager) and booting
    twice in one interpreter does not give you a clean system.
    run_all_tests.py already subprocess-isolates every suite, so this is free.

  * The bus listeners bind fixed ports (5000/5001 by default), so two suites
    booting concurrently will collide. The runner is sequential; keep it that
    way, or set FMOFP_BC_LISTEN_PORT / FMOFP_RT_LISTEN_PORT per suite
    (see story C8.1).

  * Assert on STATE, not on log text. The suites this harness was built for
    verify by regex-matching captured log output, which breaks whenever a
    message is reworded and can pass by coincidence. See
    test_weather_radar_live.py for the pattern to copy.
"""
import asyncio
import os
import sys
import time
import traceback

_B20SS = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _B20SS not in sys.path:
    sys.path.insert(0, _B20SS)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

BOOT_TIMEOUT = 90.0
BODY_TIMEOUT = 240.0
SHUTDOWN_GRACE = 15.0


def run_against_live_system(body, boot_timeout=BOOT_TIMEOUT, body_timeout=BODY_TIMEOUT):
    """Boot the application, await `body(system_manager)`, shut down.

    Returns a process exit status: 0 when the body reports success, 1 otherwise.
    Never raises -- a failure to boot, a body exception and a timeout all become
    a nonzero status with an explanation on stdout, because the caller is a test
    process whose job is to exit with a meaningful code.
    """
    from FMOFP.core.initializer import get_initializer

    initializer = get_initializer()
    initializer.initialize()
    loop = initializer.get_loop()

    outcome = {"status": 1, "detail": "did not run"}

    async def _drive():
        from FMOFP.core.system_manager import get_system_manager
        from FMOFP.Main import Flight_Management_Operating_Flight_Program

        app = None
        try:
            started = time.time()
            app = Flight_Management_Operating_Flight_Program()
            await app.initialize()
            app.start()

            sm = get_system_manager()
            deadline = time.time() + boot_timeout
            while not sm.is_system_ready() and time.time() < deadline:
                await asyncio.sleep(0.1)

            if not sm.is_system_ready():
                outcome.update(status=1,
                               detail=f"system did not become ready within {boot_timeout:.0f}s")
                return

            print(f"  [harness] booted to ready in {time.time() - started:.1f}s")

            result = await asyncio.wait_for(body(sm), timeout=body_timeout)

            if isinstance(result, bool):
                ok = result
            elif isinstance(result, int):
                ok = (result == 0)
            else:
                ok = (result is None)
            outcome.update(status=0 if ok else 1,
                           detail=f"body returned {result!r}")

        except asyncio.TimeoutError:
            outcome.update(status=1, detail=f"body exceeded {body_timeout:.0f}s")
        except Exception as exc:  # noqa: BLE001 - the harness must not lose the reason
            outcome.update(status=1, detail=f"{type(exc).__name__}: {exc}")
            traceback.print_exc()
        finally:
            # Shut down even on failure: the bus listeners hold ports 5000/5001
            # and leaking them would break the next suite in the runner.
            if app is not None:
                try:
                    await asyncio.wait_for(app.shutdown(), timeout=SHUTDOWN_GRACE)
                except Exception as exc:  # noqa: BLE001 - shutdown is best-effort
                    print(f"  [harness] shutdown problem (ignored): "
                          f"{type(exc).__name__}: {exc}")
            loop.call_soon_threadsafe(loop.stop)

    loop.create_task(_drive())
    loop.run_forever()

    if outcome["status"] != 0:
        print(f"  [harness] FAILED: {outcome['detail']}")
    return outcome["status"]


async def await_condition(predicate, timeout=10.0, interval=0.1):
    """Poll `predicate()` until it is truthy, or `timeout` elapses.

    Returns True if it became true. Needed because much of this system is
    supervised asynchronously -- e.g. RadarManagementSystem reasserts each
    radar's commanded mode on its own update loop, so state converges over a
    tick rather than changing the instant you set it. Polling asserts
    convergence; a bare sleep asserts a guess about timing.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(interval)
    return predicate()
