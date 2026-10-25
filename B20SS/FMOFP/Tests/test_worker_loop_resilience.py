"""
Test suite: a subsystem's worker loop survives a transient error, and says so
honestly when it does not.

Two findings in FuelManagementSystem, both measured.

1. ONE TRANSIENT ERROR KILLED THE WORKER PERMANENTLY. run()'s loop called
   update_fuel_system(), check_fuel_levels() and perform_fuel_transfer()
   OUTSIDE its try, which covered only the monitor/transfer pair below them.
   Anything the first three raised propagated out of the daemon thread and
   fuel management stopped for the rest of the process's life. Reproduced by
   injecting a single RuntimeError on the second pass: worker gone.

   An AST sweep of all nine safety-critical subsystems found this was the
   ONLY one with unguarded calls in its worker loop. The other eight wrap
   the whole body, log, back off on the stop Event and continue. That shape
   is adopted here, and the sweep is kept as a regression guard.

2. get_status() REPORTED running=True OVER A DEAD THREAD. It returned
   self.running, a plain bool that run() set True and nothing ever reset --
   so the subsystem's own status said it was running while its worker was
   gone. Measured in the same reproduction. The other eight report thread
   liveness, which cannot lie this way, and this one now does too.

AND THE CONSEQUENCE OF FIXING THE FIRST. Guarding the loop converts "the
worker died" into "the worker is alive and achieving nothing", and a
liveness-only health check calls that HEALTHY forever. So run() counts
consecutive failures and health_report() passes them to worker_health(),
which reports UNHEALTHY once a subsystem has failed UNHEALTHY_AFTER_FAILURES
passes in a row, with the last error attached. The other eight share that
blind spot until they track failures too; worker_health() defaults to the
liveness-only behaviour for them.

Run:  python3 -m FMOFP.Tests.test_worker_loop_resilience
"""

import os
import sys

_B20SS = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
for _p in (_B20SS, os.path.join(_B20SS, 'FMOFP')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import ast
import pathlib
import textwrap
import threading
import time
import traceback

from FMOFP.Utils.common.health import HealthState, worker_health


class _Results:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self._failures = []

    def check(self, name, cond, detail=""):
        if cond:
            self.passed += 1
            print(f"  PASS  {name}")
        else:
            self.failed += 1
            msg = f"  FAIL  {name}" + (f"  [{detail}]" if detail else "")
            print(msg)
            self._failures.append(msg)

    def section(self, title):
        print(f"\n{title}")

    def summary(self):
        total = self.passed + self.failed
        print(f"\n  {self.passed}/{total} passed")
        if self._failures:
            print("\n  Failures:")
            for f in self._failures:
                print(f"    {f}")
        return self.failed == 0


R = _Results()

SUBSYSTEMS = {
    "FCC": "FMOFP/Systems/flightControlSys/flightControlComputer/flightControlComputer.py",
    "nav": "FMOFP/Systems/nav/navService.py",
    "ECU": "FMOFP/Systems/engineManagement/ecu/engineControlUnit.py",
    "surfaces": "FMOFP/Systems/flightSurfaces/flightSurfaceService.py",
    "power": "FMOFP/Systems/powerManagement/elec/powerManagementSystem.py",
    "fuel": "FMOFP/Systems/engineManagement/fuelManagement/fuelControl.py",
    "thrust": "FMOFP/Systems/engineManagement/thrustManagement/thrustManagement.py",
    "hydraulics": "FMOFP/Systems/hydraulics/hydrControl.py",
    "GCAS": ("FMOFP/Systems/flightControlSys/groundCollisionAvoidanceSys/"
             "groundCollisionAvoidanceSys.py"),
}

# Calls that are part of the loop's own plumbing rather than its work.
_PLUMBING = {"sleep", "wait", "is_set", "monotonic", "time", "clear", "set"}


def unguarded_calls(source):
    """Calls made directly in a while-loop body, outside any try.

    A substring search for 'try:' near the loop is not enough and gave the
    wrong answer when this was first checked by eye: fuel's loop DID contain
    a try, several lines below three unguarded calls. This walks the loop
    body's top-level statements instead.
    """
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.While):
            continue
        for stmt in node.body:
            if isinstance(stmt, ast.Try):
                continue
            for sub in ast.walk(stmt):
                if not isinstance(sub, ast.Call):
                    continue
                fn = sub.func
                name = (fn.attr if isinstance(fn, ast.Attribute)
                        else getattr(fn, "id", "?"))
                if name not in _PLUMBING:
                    found.append((node.lineno, name, sub.lineno))
    return found


def test_every_worker_loop_guards_its_body():
    R.section("all nine worker loops guard their whole body")

    for label, rel in SUBSYSTEMS.items():
        src = pathlib.Path(os.path.join(_B20SS, rel)).read_text(encoding="utf-8")
        found = unguarded_calls(src)
        R.check(f"{label}: no unguarded call in a worker loop",
                not found,
                ", ".join(f"{n}() L{ln}" for _, n, ln in found[:5]))


def test_the_scanner_can_see_an_unguarded_loop():
    R.section("NON-TAUTOLOGICAL — the scanner is not simply blind")

    # The exact pre-fix shape of fuel's loop: a try that covers only the
    # tail, with the real work above it.
    planted = textwrap.dedent('''
        def run(self):
            while self.running:
                self.update_fuel_system()
                self.check_fuel_levels()
                try:
                    self.monitor.poll(1)
                except Exception as e:
                    pass
                time.sleep(1)
    ''')
    found = unguarded_calls(planted)
    names = {n for _, n, _ in found}
    R.check("it flags the two calls above the try",
            {"update_fuel_system", "check_fuel_levels"} <= names, str(sorted(names)))
    R.check("...and does not flag the one inside it",
            "poll" not in names, str(sorted(names)))
    R.check("...nor the loop's own sleep", "sleep" not in names, str(sorted(names)))

    guarded = textwrap.dedent('''
        def run(self):
            while not self._running.is_set():
                try:
                    self.work()
                    self.more_work()
                except Exception as e:
                    self._running.wait(5)
                    continue
                self._running.wait(1)
    ''')
    R.check("and it passes a loop whose body is wholly inside the try",
            unguarded_calls(guarded) == [], str(unguarded_calls(guarded)))


def _fuel():
    from FMOFP.Systems.engineManagement.fuelManagement.fuelControl import (
        get_fuel_management_system)
    f = get_fuel_management_system()
    f.update_interval = 0.05
    f.ERROR_BACKOFF_S = 0.1
    f._consecutive_failures = 0
    f._last_error = ""
    return f


def test_one_transient_error_is_not_fatal():
    R.section("a single transient error no longer kills fuel management")

    f = _fuel()
    calls = {"n": 0}
    real = f.update_fuel_system

    def flaky():
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("transient sensor glitch")
        return real()

    f.update_fuel_system = flaky
    try:
        f.start()
        time.sleep(1.0)
        alive = f._thread.is_alive()
        report = f.health_report()
        passes = calls["n"]
    finally:
        f.update_fuel_system = real
        f.stop()

    # Pre-fix this was: alive False, passes 2, health UNHEALTHY.
    R.check("the worker is still alive after the error", alive, str(alive))
    R.check("...and kept working past it (more than the 2 passes it used to "
            "manage)", passes > 2, f"passes={passes}")
    R.check("...and reports HEALTHY, because one glitch is not a failure",
            report.state is HealthState.HEALTHY, str(report))


def test_sustained_failure_reports_unhealthy():
    R.section("alive is not the same as working")

    f = _fuel()
    real = f.update_fuel_system

    def always():
        raise RuntimeError("pump offline")

    f.update_fuel_system = always
    try:
        f.start()
        time.sleep(1.0)
        alive = f._thread.is_alive()
        report = f.health_report()
        failures = f._consecutive_failures
        # Taken here, while the worker is still up: after the finally below
        # the thread is stopped and a liveness check would say UNHEALTHY for
        # the wrong reason.
        liveness_only = worker_health("FUEL", f._thread, stop_requested=False,
                                      consecutive_failures=0)
    finally:
        f.update_fuel_system = real
        f.stop()

    R.check("the guard keeps the worker alive", alive, str(alive))
    R.check("...so a liveness-only check would have called this HEALTHY",
            liveness_only.state is HealthState.HEALTHY, str(liveness_only))
    R.check("but health_report() says UNHEALTHY",
            report.state is HealthState.UNHEALTHY, str(report))
    R.check("...and names the error", "pump offline" in report.reason,
            report.reason)
    R.check("...and the count passed the threshold",
            failures >= f.UNHEALTHY_AFTER_FAILURES,
            f"{failures} vs {f.UNHEALTHY_AFTER_FAILURES}")

    # And it recovers: a subsystem that starts working again must go back to
    # HEALTHY rather than latching.
    f = _fuel()
    try:
        f.start()
        time.sleep(0.5)
        recovered = f.health_report()
    finally:
        f.stop()
    R.check("a recovered subsystem reports HEALTHY again, not latched",
            recovered.state is HealthState.HEALTHY, str(recovered))


def test_get_status_cannot_claim_a_dead_worker_is_running():
    R.section("get_status() reports the thread, not an unresettable flag")

    f = _fuel()
    f.start()
    time.sleep(0.2)
    running_while_up = f.get_status()["running"]
    f.stop()
    time.sleep(0.2)
    running_after_stop = f.get_status()["running"]

    R.check("running is True while the worker is up", running_while_up is True)
    # Pre-fix this was True: run() set self.running = True and nothing reset
    # it, so a dead worker still reported running.
    R.check("running is False once the worker has gone",
            running_after_stop is False, str(running_after_stop))
    R.check("...and it is derived from the thread, so it cannot disagree "
            "with health_report()",
            (f.health_report().state is not HealthState.HEALTHY)
            and running_after_stop is False)


def test_stop_interrupts_the_error_backoff():
    R.section("the backoff waits on the stop Event, it does not sleep")

    f = _fuel()
    f.ERROR_BACKOFF_S = 30.0
    real = f.update_fuel_system
    f.update_fuel_system = lambda: (_ for _ in ()).throw(RuntimeError("x"))
    try:
        f.start()
        time.sleep(0.3)
        t0 = time.monotonic()
        f.stop()
        elapsed = time.monotonic() - t0
        alive = f._thread.is_alive()
    finally:
        f.update_fuel_system = real

    # A time.sleep(30) backoff would have made stop()'s join(timeout=2)
    # return after ~2s with the thread still alive -- the exact failure the
    # note in FlightControlComputer._update_loop records.
    R.check("stop() returns promptly even mid-backoff, not after the join "
            "timeout", elapsed < 1.5, f"{elapsed:.2f}s")
    R.check("...and the worker is actually gone, not merely reported stopped",
            not alive, str(alive))


def test_worker_health_failure_threshold():
    R.section("worker_health's failure arguments")

    class _T:
        def __init__(self, alive=True, name="W"):
            self._alive = alive
            self.name = name

        def is_alive(self):
            return self._alive

    live = _T()
    R.check("below the threshold stays HEALTHY",
            worker_health("x", live, stop_requested=False,
                          consecutive_failures=2,
                          failure_threshold=3).state is HealthState.HEALTHY)
    R.check("at the threshold becomes UNHEALTHY",
            worker_health("x", live, stop_requested=False,
                          consecutive_failures=3,
                          failure_threshold=3).state is HealthState.UNHEALTHY)
    R.check("the last error is carried into the reason",
            "boom" in worker_health("x", live, stop_requested=False,
                                    consecutive_failures=3,
                                    failure_threshold=3,
                                    last_error="boom").reason)
    R.check("a threshold of 0 disables the check, for subsystems that do "
            "not count failures",
            worker_health("x", live, stop_requested=False,
                          consecutive_failures=99,
                          failure_threshold=0).state is HealthState.HEALTHY)
    R.check("the default is liveness-only, so the other eight are unchanged",
            worker_health("x", live, stop_requested=False).state
            is HealthState.HEALTHY)
    R.check("a dead worker is UNHEALTHY regardless of the counters",
            worker_health("x", _T(alive=False), stop_requested=False,
                          consecutive_failures=0).state is HealthState.UNHEALTHY)
    R.check("stop requested still wins over the failure count",
            worker_health("x", live, stop_requested=True,
                          consecutive_failures=99).state is HealthState.UNKNOWN)


def main():
    print("=" * 60)
    print("  Worker loops: survive a glitch, admit a real failure")
    print("=" * 60)

    for test in (test_every_worker_loop_guards_its_body,
                 test_the_scanner_can_see_an_unguarded_loop,
                 test_one_transient_error_is_not_fatal,
                 test_sustained_failure_reports_unhealthy,
                 test_get_status_cannot_claim_a_dead_worker_is_running,
                 test_stop_interrupts_the_error_backoff,
                 test_worker_health_failure_threshold):
        try:
            test()
        except Exception:
            R.failed += 1
            R._failures.append(f"  FAIL  {test.__name__} raised")
            print(f"  FAIL  {test.__name__} raised:")
            traceback.print_exc()

    print("\n" + "=" * 60)
    ok = R.summary()
    print("=" * 60)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
