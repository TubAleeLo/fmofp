"""
Test suite: H5 — a threading.Lock held across an await.

`RadarMessageHandler.send_request` wrapped its whole body in
`with self._message_lock:` -- a `threading.Lock` -- and awaited three times
inside it: `_create_request`, the `sendMsg.send_message` network write, and the
`sync_response` wait. `FMSResponseService.send_response` did the same across
`await callback(response)`.

A thread lock blocks the THREAD, not the task, and an event loop has exactly one
thread. So two concurrent sends did not serialise -- they deadlocked the loop
permanently. Measured on the real handler before the fix: one send reached the
wire, the lock stayed held, and the loop never ran again. An
`asyncio.wait_for()` wrapped around the pair could not even fire, because the
timeout needed the loop it was waiting on.

The radar handler now takes a per-loop `asyncio.Lock` from
`_loop_bound_lock(purpose)`; FMSResponseService keeps a thread lock but narrows
it to the dictionary access it actually guards.

Anything that could hang runs in a SUBPROCESS with a timeout, so a regression
here fails this suite rather than parking the runner for its whole watchdog.

Run:  python3 -m FMOFP.Tests.test_handler_lock_discipline
"""

import os
import sys

_B20SS = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
for _p in (_B20SS, os.path.join(_B20SS, 'FMOFP')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import FMOFP.Tests  # noqa: F401  -- UTF-8 stdio for piped output

import ast
import asyncio
import subprocess
import textwrap
import threading
import traceback


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

_PRELUDE = f"""
import asyncio, os, sys, threading
sys.path.insert(0, {_B20SS!r})
sys.path.insert(0, {os.path.join(_B20SS, 'FMOFP')!r})
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
"""


def _run_isolated(body, timeout=25.0):
    """Run `body` in a subprocess. Returns (finished, stdout).

    finished is False when it had to be killed -- which is what a deadlock
    looks like from the outside, and the only safe way to observe one.
    """
    script = _PRELUDE + textwrap.dedent(body)
    try:
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True, timeout=timeout,
            cwd=_B20SS,
        )
    except subprocess.TimeoutExpired as e:
        return False, (e.stdout or "") if isinstance(e.stdout, str) else ""
    return True, proc.stdout


# --------------------------------------------------------------------------
# The shape itself, in isolation. No project code: this is what the defect
# IS, so if these two stop disagreeing the rest of the suite means nothing.
# --------------------------------------------------------------------------

def test_the_shape_is_really_a_deadlock():
    R.section("NON-TAUTOLOGICAL — a thread lock across an await hangs one loop")

    finished, out = _run_isolated("""
        lock = threading.Lock()
        async def worker(n):
            with lock:
                print(f"entered {n}", flush=True)
                await asyncio.sleep(0.1)
            print(f"left {n}", flush=True)
        async def main():
            await asyncio.gather(worker(1), worker(2))
            print("BOTH FINISHED", flush=True)
        asyncio.run(main())
    """, timeout=12.0)
    R.check("two tasks under one threading.Lock never finish",
            not finished and "BOTH FINISHED" not in out,
            f"finished={finished}")

    finished, out = _run_isolated("""
        async def main():
            lock = asyncio.Lock()
            async def worker(n):
                async with lock:
                    await asyncio.sleep(0.1)
            await asyncio.gather(worker(1), worker(2))
            print("BOTH FINISHED", flush=True)
        asyncio.run(main())
    """, timeout=12.0)
    R.check("the same pair under an asyncio.Lock finishes",
            finished and "BOTH FINISHED" in out, f"finished={finished}")


# --------------------------------------------------------------------------
# The real handler.
# --------------------------------------------------------------------------

_SEND_HARNESS = """
from FMOFP.local_messaging.routing.handlers.system_message_handlers.RadarMessageHandler import (
    RadarMessageHandler)
h = RadarMessageHandler()
order = []
class Sender:
    async def send_message(self, command_word, data_words, request_id, metadata):
        order.append(('enter', request_id))
        await asyncio.sleep(0.15)
        order.append(('leave', request_id))
        return {'ok': True}
h.sendMsg = Sender()
class AH:
    started = True
h.async_handler = AH()
h.started = True

async def main():
    ids = await asyncio.gather(
        h.send_request('weather_radar', 'status'),
        h.send_request('weather_radar', 'status'),
    )
    print(f"IDS={len([i for i in ids if i])}", flush=True)
    print(f"ORDER={[o[0] for o in order]}", flush=True)
    print("BOTH FINISHED", flush=True)
asyncio.run(main())
"""


def test_concurrent_sends_complete():
    R.section("H5 — two concurrent radar sends no longer deadlock the loop")

    finished, out = _run_isolated(_SEND_HARNESS, timeout=40.0)
    R.check("both send_request calls return", finished and "BOTH FINISHED" in out,
            f"finished={finished}, tail={out.strip().splitlines()[-1:]}")
    R.check("and both produced a request id", "IDS=2" in out,
            next((l for l in out.splitlines() if l.startswith("IDS=")), "no IDS line"))
    R.check("the bus is still serialised, not interleaved",
            "ORDER=['enter', 'leave', 'enter', 'leave']" in out,
            next((l for l in out.splitlines() if l.startswith("ORDER=")), "no ORDER line"))


def test_fms_response_service_concurrency():
    R.section("H5 — concurrent FMS responses no longer deadlock the loop")

    finished, out = _run_isolated("""
        from FMOFP.local_messaging.routing.response_services.system_response_services.FMSResponseService import (
            FMSResponseService)
        svc = FMSResponseService()
        async def slow(response):
            await asyncio.sleep(0.15)
        async def main():
            await svc.register_response_callback('a', slow)
            await svc.register_response_callback('b', slow)
            ok = await asyncio.gather(svc.send_response('a', {}),
                                      svc.send_response('b', {}))
            print(f"OK={ok}", flush=True)
            print(f"DRAINED={len(svc.response_callbacks)}", flush=True)
            print("BOTH FINISHED", flush=True)
        asyncio.run(main())
    """, timeout=40.0)
    R.check("both send_response calls return",
            finished and "BOTH FINISHED" in out, f"finished={finished}")
    R.check("both reported success", "OK=[True, True]" in out,
            next((l for l in out.splitlines() if l.startswith("OK=")), "no OK line"))
    R.check("and each callback was consumed exactly once", "DRAINED=0" in out,
            next((l for l in out.splitlines() if l.startswith("DRAINED=")), "no line"))


# --------------------------------------------------------------------------
# _loop_bound_lock's contract.
# --------------------------------------------------------------------------

def test_loop_bound_lock_contract():
    R.section("H5 — the lock registry's contract")

    from FMOFP.local_messaging.routing.handlers.system_message_handlers.RadarMessageHandler import (
        RadarMessageHandler)
    h = RadarMessageHandler()

    R.check("the old threading.Lock on the send path is gone",
            not hasattr(h, "_message_lock"))
    R.check("set_async_handler's init lock is still a thread lock, correctly "
            "-- it never awaits",
            isinstance(h._init_lock, type(threading.Lock())))

    seen = {}

    async def probe():
        a = h._loop_bound_lock('bus')
        b = h._loop_bound_lock('bus')
        c = h._loop_bound_lock('pending')
        seen['same'] = a is b
        seen['distinct'] = a is not c
        seen['type'] = isinstance(a, asyncio.Lock)
        # The cleanup path holds 'pending' and calls into the send path, which
        # takes 'bus'. That must not block.
        async with h._loop_bound_lock('pending'):
            try:
                await asyncio.wait_for(
                    h._loop_bound_lock('bus').acquire(), timeout=1.0)
                seen['nested_ok'] = True
                h._loop_bound_lock('bus').release()
            except asyncio.TimeoutError:
                seen['nested_ok'] = False
        # ...whereas one shared lock for both would deadlock. Same expression,
        # one lock instead of two.
        shared = asyncio.Lock()
        async with shared:
            try:
                await asyncio.wait_for(shared.acquire(), timeout=1.0)
                seen['shared_ok'] = True
                shared.release()
            except asyncio.TimeoutError:
                seen['shared_ok'] = False
        seen['first'] = a

    asyncio.run(probe())

    R.check("it hands back an asyncio.Lock", seen.get('type'))
    R.check("the same purpose on one loop is the same lock", seen.get('same'))
    R.check("different purposes are different locks", seen.get('distinct'))
    R.check("'pending' then 'bus' nests, so cleanup can call send",
            seen.get('nested_ok'))

    R.section("NON-TAUTOLOGICAL — merging the two locks would self-deadlock")
    R.check("one shared lock cannot be re-entered the same way",
            seen.get('shared_ok') is False,
            f"shared_ok={seen.get('shared_ok')}")

    R.section("H5 — locks do not leak across event loops")

    async def other_loop():
        seen['other'] = h._loop_bound_lock('bus')

    asyncio.run(other_loop())
    R.check("a second loop gets its own lock, never the dead one",
            seen.get('other') is not None and seen['other'] is not seen['first'])

    h.started = True
    h.stop()
    R.check("stop() drops the registry so a restart rebinds",
            h._loop_locks == {}, f"registry={h._loop_locks!r}")


# --------------------------------------------------------------------------
# Nothing anywhere in the package holds a thread lock across an await.
# --------------------------------------------------------------------------

_BAD_SAMPLE = """
import threading
lock = threading.Lock()
async def f():
    with lock:
        await g()
"""


def _lock_await_sites(source, label):
    sites = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.With):
            items = ' '.join(ast.dump(i) for i in node.items)
            if 'lock' in items.lower():
                for sub in ast.walk(node):
                    if isinstance(sub, (ast.Await, ast.AsyncFor, ast.AsyncWith)):
                        sites.append((label, node.lineno))
                        break
    return sites


def test_no_lock_held_across_await_anywhere():
    R.section("H5 — the shape is absent from the whole package")

    R.section("NON-TAUTOLOGICAL — the scanner finds a planted instance")
    R.check("a known-bad sample is detected",
            len(_lock_await_sites(_BAD_SAMPLE, "sample")) == 1,
            f"found {len(_lock_await_sites(_BAD_SAMPLE, 'sample'))}")

    R.section("H5 — and finds none in the shipped code")
    found = []
    scanned = 0
    pkg = os.path.join(_B20SS, 'FMOFP')
    for root, _dirs, files in os.walk(pkg):
        if os.path.sep + 'Tests' in root:
            continue
        for f in files:
            if not f.endswith('.py'):
                continue
            path = os.path.join(root, f)
            try:
                src = open(path, encoding='utf-8', errors='replace').read()
            except OSError:
                continue
            scanned += 1
            found.extend(_lock_await_sites(src, os.path.relpath(path, _B20SS)))

    R.check(f"no synchronous lock is held across an await ({scanned} files scanned)",
            not found, f"{found}")


def main():
    print("=" * 60)
    print("  H5: a threading.Lock held across an await")
    print("=" * 60)

    for test in (test_the_shape_is_really_a_deadlock,
                 test_loop_bound_lock_contract,
                 test_no_lock_held_across_await_anywhere,
                 test_concurrent_sends_complete,
                 test_fms_response_service_concurrency):
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
