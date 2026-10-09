"""
Test suite: H4 — the radar send gate that never ran.

`RadarMessageHandler.send_request` guarded itself with

    if not self._can_send_request():
        while not self._can_send_request():
            await asyncio.sleep(0.01)

on an `async def`. An un-awaited coroutine object is always truthy, so `not` was
always False, the body never ran, and the method itself never executed. Two
separate guards were lost: the rate limit, and -- more seriously -- the
readiness check inside it, which decides whether there is anything on the other
end to receive the message.

The naive repair, adding `await` and keeping the loop, would have been worse: the
only reason the call returns False is a handler that has not started, and
sleeping does not start one, so the `while` becomes an infinite spin. The method
already waits for the gap internally, so the loop had to go.

Run:  python3 -m FMOFP.Tests.test_radar_send_rate_limit
"""

import os
import sys

_B20SS = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
for _p in (_B20SS, os.path.join(_B20SS, 'FMOFP')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import FMOFP.Tests  # noqa: F401  -- UTF-8 stdio for piped output

import asyncio
import time
import traceback
import warnings


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


class _FakeAsyncHandler:
    def __init__(self, started=True):
        self.started = started


def _handler(started=True, system=True, rate=10, sender=True):
    """A RadarMessageHandler with only the fields the send gate reads."""
    from FMOFP.local_messaging.routing.handlers.system_message_handlers.RadarMessageHandler import (
        RadarMessageHandler,
    )
    h = RadarMessageHandler.__new__(RadarMessageHandler)
    h.async_handler = _FakeAsyncHandler(started) if started is not None else None
    h.system_handler = object() if system else None
    h.sendMsg = object() if sender else None
    h.request_rate_limit = rate
    h.last_request_time = 0
    # H5: the three ad-hoc lazy locks (_lock, _send_slot_lock, _message_lock)
    # became one registry keyed by purpose. _loop_bound_lock() reads it without
    # a getattr default on purpose -- a half-built handler should raise here
    # rather than quietly make itself a lock, so this factory has to name it.
    h._loop_locks = {}
    h._warned_response_path_down = False
    return h


# ─────────────────────────────── the gate runs at all ───────────────────────

def test_gate_actually_executes():
    R.section("The gate executes, and refuses only what makes sending impossible")

    async def run():
        h = _handler(sender=False)
        R.check("no message sender refuses the slot",
                await h._acquire_send_slot() is False)

        h = _handler()
        R.check("a ready handler grants the slot",
                await h._acquire_send_slot() is True)

        # The original guard refused the send unless async_handler.started and
        # system_handler were both set. Neither is on the send path, and turning
        # that check on unchanged refused 23 working sends in
        # test_predefined_messages_live -- four radars stuck in STANDBY. The
        # gate must not block on either.
        h = _handler(started=False)
        R.check("an unstarted async handler does NOT block the send",
                await h._acquire_send_slot() is True)
        R.check("...but it is reported, once",
                h._warned_response_path_down is True)

        h = _handler(system=False)
        R.check("a missing system handler does NOT block the send",
                await h._acquire_send_slot() is True)

    asyncio.run(run())

    R.section("NON-TAUTOLOGICAL -- the pre-fix call really could not refuse")

    async def pre_fix():
        h = _handler(sender=False)         # the gate would say False
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")   # 'coroutine was never awaited'
            coro = h._acquire_send_slot()
            truthy = bool(coro)
            negated = not coro
            coro.close()
        R.check("an un-awaited coroutine object is truthy", truthy is True)
        R.check("so `not self._acquire_send_slot()` is False even when the "
                "handler is down", negated is False)
        R.check("while awaiting the same call on the same object says False",
                await h._acquire_send_slot() is False)

    asyncio.run(pre_fix())


# ─────────────────────────────────── the limit holds ────────────────────────

def test_rate_limit_is_enforced():
    R.section("The rate limit paces sends")

    async def run():
        # 20/s -> a 0.05 s gap. Four sequential slots span at least three gaps.
        h = _handler(rate=20)
        start = time.monotonic()
        for _ in range(4):
            assert await h._acquire_send_slot()
        elapsed = time.monotonic() - start
        R.check("four sequential sends at 20/s take at least three gaps",
                elapsed >= 0.15 - 0.02, f"elapsed={elapsed:.3f}s")

        # Concurrency: without the lock every coroutine reads the same stale
        # last_request_time and they all leave together.
        h = _handler(rate=20)
        start = time.monotonic()
        await asyncio.gather(*(h._acquire_send_slot() for _ in range(4)))
        elapsed = time.monotonic() - start
        R.check("four concurrent sends are serialised, not released together",
                elapsed >= 0.15 - 0.02, f"elapsed={elapsed:.3f}s")

        # A single acquisition must never block for longer than one gap.
        h = _handler(rate=2)                    # 0.5 s gap
        h.last_request_time = time.monotonic() + 30.0   # corrupt: in the future
        start = time.monotonic()
        granted = await h._acquire_send_slot()
        elapsed = time.monotonic() - start
        R.check("a last_request_time in the future cannot park the caller",
                granted and elapsed <= 0.75, f"elapsed={elapsed:.3f}s")

    asyncio.run(run())

    R.section("NON-TAUTOLOGICAL -- the pre-fix path imposed no delay at all")

    async def pre_fix():
        h = _handler(rate=20)
        start = time.monotonic()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for _ in range(4):
                c = h._acquire_send_slot()      # the un-awaited call
                if not c:
                    pass
                c.close()
        elapsed = time.monotonic() - start
        R.check("four un-awaited calls return instantly, so nothing was paced",
                elapsed < 0.01, f"elapsed={elapsed:.4f}s")
        R.check("and last_request_time was never updated",
                h.last_request_time == 0, f"got {h.last_request_time}")

    asyncio.run(pre_fix())


# ────────────────────────────── send_request gives up ───────────────────────

def test_send_request_gives_up_rather_than_spinning():
    """The repaired caller must return, not loop, when it genuinely cannot send."""
    R.section("send_request returns instead of spinning when it cannot send")

    async def run():
        h = _handler(sender=False)
        # Only the gate is exercised: anything past it needs the full handler.
        try:
            result = await asyncio.wait_for(
                h.send_request("weather_radar", "status"), timeout=2.0)
            R.check("it returns None rather than hanging", result is None,
                    f"got {result!r}")
        except asyncio.TimeoutError:
            R.check("it returns None rather than hanging", False,
                    "timed out -- the caller is spinning")
        except Exception as exc:
            R.check("it returns None rather than hanging", False,
                    f"raised {type(exc).__name__}: {exc}")

    asyncio.run(run())

    R.section("NON-TAUTOLOGICAL -- awaiting the old loop would spin forever")

    async def pre_fix():
        calls = {"n": 0}

        async def never_ready():
            calls["n"] += 1
            return False

        async def old_shape():
            # The repair that keeps the loop, which the punch list warned about.
            if not await never_ready():
                while not await never_ready():
                    await asyncio.sleep(0.01)
            return "sent"

        try:
            await asyncio.wait_for(old_shape(), timeout=0.5)
            R.check("the awaited-but-still-looping form spins forever", False,
                    "it returned, which it should not have")
        except asyncio.TimeoutError:
            R.check("the awaited-but-still-looping form spins forever",
                    calls["n"] > 5, f"gate polled {calls['n']} times in 0.5s")

    asyncio.run(pre_fix())


def main():
    print("=" * 60)
    print("  H4: the radar send gate that never ran")
    print("=" * 60)

    for test in (test_gate_actually_executes,
                 test_rate_limit_is_enforced,
                 test_send_request_gives_up_rather_than_spinning):
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
