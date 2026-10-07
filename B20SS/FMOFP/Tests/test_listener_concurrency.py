"""
Test suite: H3 — the accept loop served one connection at a time.

Both listeners accepted a connection and then called handle_connection() inline,
on the accept thread. handle_connection() loops until the peer goes away, so for
as long as one peer stayed connected the listener accepted nobody else. Measured
against the real RT_Listener before the fix: peer A connected and said nothing,
peer B connected a second later and sent a valid message, and B was not accepted
until A disconnected. One stalled sender took the bus down for everyone.

H2 added an idle timeout, which bounded how long that lasted but did not change
the shape -- a peer that keeps sending still holds the loop indefinitely. The fix
is to hand each connection to a worker thread and return to accept() at once,
with a ceiling on live workers so a flood cannot spawn threads without limit.

The guard below that matters most is test_pre_fix_serialises: it puts the inline
call back on a real listener and shows the second peer going unserved. Without
it, every assertion here would pass against the unfixed code too.

Run:  python3 -m FMOFP.Tests.test_listener_concurrency
"""

import os
import sys

_B20SS = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
for _p in (_B20SS, os.path.join(_B20SS, 'FMOFP')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import FMOFP.Tests  # noqa: F401  -- UTF-8 stdio for piped output

import inspect
import socket
import threading
import time
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

# Long enough that H2's idle timeout cannot be what frees the listener in any
# of these measurements. What is being measured here is the hand-off, not the
# reclaim; test_listener_idle_and_bind measures the reclaim.
_NO_IDLE_RECLAIM = 3600.0


def _rt_module():
    import FMOFP.MIL_STD_1553B.Remote_Terminal.RT_connect.RT_socket as rt_socket
    return rt_socket


def _start_listener(spawn=None):
    """Start a real RT_Listener on an ephemeral loopback port.

    `spawn`, when given, replaces _spawn_connection_handler on the instance --
    that is how the pre-fix inline behaviour is put back.

    Returns (listener, port, accept_times) where accept_times grows by one
    monotonic timestamp per accepted connection.
    """
    rt_socket = _rt_module()
    os.environ["FMOFP_RT_LISTEN_HOST"] = "127.0.0.1"
    os.environ["FMOFP_RT_LISTEN_PORT"] = "0"
    rt_socket.CONNECTION_IDLE_TIMEOUT_S = _NO_IDLE_RECLAIM

    listener = rt_socket.RT_Listener()
    listener.running = True
    listener.setup_socket()
    port = listener.socket_variable.getsockname()[1]

    accept_times = []
    inner = spawn if spawn is not None else listener._spawn_connection_handler

    def recording(connection, client_address):
        accept_times.append(time.monotonic())
        return inner(connection, client_address)

    listener._spawn_connection_handler = recording

    threading.Thread(target=listener.start_listening, daemon=True).start()
    time.sleep(0.5)
    return listener, port, accept_times


def _shutdown(listener, peers):
    listener.running = False
    for sock in peers:
        try:
            sock.close()
        except Exception:
            pass
    time.sleep(1.1)


def _second_peer_accept_delay(spawn=None, wait_s=6.0):
    """Hold a silent peer, then time how long the next peer waits to be accepted.

    Returns (accepts_after_first, delay_or_None). The silent peer never sends
    and never closes, so under the pre-fix inline call nothing can free the
    accept loop within wait_s.
    """
    listener, port, accepts = _start_listener(spawn=spawn)
    peers = []
    try:
        a = socket.create_connection(("127.0.0.1", port))
        peers.append(a)
        time.sleep(0.8)
        if len(accepts) != 1:
            return len(accepts), None
        first_at = accepts[0]

        b = socket.create_connection(("127.0.0.1", port))
        peers.append(b)
        b.sendall(b'{"type": "status", "data": "B is here"}\n')

        deadline = time.monotonic() + wait_s
        while time.monotonic() < deadline and len(accepts) < 2:
            time.sleep(0.1)
        if len(accepts) < 2:
            return len(accepts), None
        return len(accepts), accepts[1] - first_at
    finally:
        _shutdown(listener, peers)


def test_second_peer_is_accepted_while_the_first_holds_on():
    R.section("H3 — a held connection no longer blocks the accept loop")

    accepts, delay = _second_peer_accept_delay()
    R.check("the second peer is accepted with the first still connected "
            "and silent", accepts >= 2, f"accepts={accepts}")
    R.check("and it does not have to wait for the first to go away",
            delay is not None and delay < 2.0,
            f"delay={None if delay is None else round(delay, 1)}s")


def test_pre_fix_serialises():
    """Put the inline call back and the second peer goes unserved.

    This is the pre-fix expression, not a description of it: handle_connection
    is called on the accept thread exactly as the old loop called it.
    """
    R.section("NON-TAUTOLOGICAL — serving inline reproduces the block")

    captured = {}

    def inline_spawn(connection, client_address):
        captured['listener'].handle_connection(connection, client_address)
        try:
            connection.close()
        except Exception:
            pass
        return True

    rt_socket = _rt_module()
    os.environ["FMOFP_RT_LISTEN_HOST"] = "127.0.0.1"
    os.environ["FMOFP_RT_LISTEN_PORT"] = "0"
    rt_socket.CONNECTION_IDLE_TIMEOUT_S = _NO_IDLE_RECLAIM
    listener = rt_socket.RT_Listener()
    captured['listener'] = listener
    listener.running = True
    listener.setup_socket()
    port = listener.socket_variable.getsockname()[1]

    accepts = []

    def recording(connection, client_address):
        accepts.append(time.monotonic())
        return inline_spawn(connection, client_address)

    listener._spawn_connection_handler = recording
    threading.Thread(target=listener.start_listening, daemon=True).start()
    time.sleep(0.5)

    peers = []
    try:
        a = socket.create_connection(("127.0.0.1", port))
        peers.append(a)
        time.sleep(0.8)
        first = len(accepts)

        b = socket.create_connection(("127.0.0.1", port))
        peers.append(b)
        b.sendall(b'{"type": "status", "data": "B is here"}\n')

        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and len(accepts) < 2:
            time.sleep(0.1)
        second = len(accepts)
    finally:
        _shutdown(listener, peers)

    R.check("the first peer is accepted", first == 1, f"accepts={first}")
    R.check("and the second is never accepted while the first stays connected",
            second < 2, f"accepts={second}")


def test_the_second_peer_is_actually_served_not_just_accepted():
    R.section("H3 — the accepted connection is read, not just taken")

    listener, port, accepts = _start_listener()
    peers = []
    try:
        a = socket.create_connection(("127.0.0.1", port))
        peers.append(a)
        time.sleep(0.8)

        b = socket.create_connection(("127.0.0.1", port))
        peers.append(b)
        # A frame the listener will actually store: 20 bits with a valid sync
        # pattern, carried in the dict form with a request_id.
        b.sendall(b'{"frames": ["10000000000000000000"], '
                  b'"request_id": "h3-second-peer"}')

        deadline = time.monotonic() + 6.0
        while time.monotonic() < deadline and not listener.data_received:
            time.sleep(0.1)
        received = list(listener.data_received)
    finally:
        _shutdown(listener, peers)

    R.check("the second peer's message reaches data_received while the "
            "first is still connected", len(received) >= 1,
            f"data_received={len(received)} entries")
    R.check("and it is that peer's message, read on a worker thread",
            any(isinstance(m, dict) and m.get("request_id") == "h3-second-peer"
                for m in received),
            f"received={received[:1]}")


def test_live_handlers_are_capped():
    R.section("H3 — workers are bounded, not unlimited")

    rt_socket = _rt_module()
    cap = rt_socket.MAX_CONCURRENT_CONNECTIONS
    R.check("there is a declared ceiling on live handlers",
            isinstance(cap, int) and cap >= 2, f"cap={cap!r}")

    listener, port, accepts = _start_listener()
    peers = []
    refused = 0
    try:
        for _ in range(cap + 6):
            try:
                peers.append(socket.create_connection(
                    ("127.0.0.1", port), timeout=2))
            except OSError:
                refused += 1
        time.sleep(2.0)
        with listener._handler_lock:
            alive = len([t for t in listener._handler_threads if t.is_alive()])
        names = {t.name for t in threading.enumerate()
                 if t.name.startswith("RT_LISTENER-conn-")}
        named_threads = [t for t in threading.enumerate()
                         if t.name.startswith("RT_LISTENER-conn-")]
    finally:
        _shutdown(listener, peers)

    R.check(f"live handlers stay at or under the cap of {cap}",
            alive <= cap, f"alive={alive}")
    R.check("and the cap is actually reached, so the limit was exercised",
            alive == cap, f"alive={alive}, cap={cap}, connect errors={refused}")
    R.check("each worker is named for its own peer, not a shared literal",
            len(names) == len(named_threads),
            f"{len(names)} distinct names across {len(named_threads)} threads")
    R.check("and the names interpolate rather than printing the format",
            not any("{" in n for n in names), f"names={sorted(names)[:2]}")


def test_stop_waits_for_handlers():
    R.section("H3 — stop_listening drains in-flight handlers")

    listener, port, accepts = _start_listener()
    peers = []
    try:
        for _ in range(3):
            s = socket.create_connection(("127.0.0.1", port))
            s.sendall(b'{"frames": ["10000000000000000000"], '
                      b'"request_id": "h3-drain"}')
            peers.append(s)
        time.sleep(1.0)
        with listener._handler_lock:
            before = len([t for t in listener._handler_threads if t.is_alive()])

        started = time.monotonic()
        listener.stop_listening()
        drain = time.monotonic() - started
        with listener._handler_lock:
            after = len([t for t in listener._handler_threads if t.is_alive()])
    finally:
        _shutdown(listener, peers)

    R.check("handlers were live before the stop", before >= 1, f"live={before}")
    R.check("and none are left running after it", after == 0, f"live={after}")
    R.check("the drain is bounded, not a hang", drain < 5.5,
            f"drain={drain:.1f}s")


def test_both_listeners_were_fixed():
    """BC and RT are near-duplicates; a fix applied to one only is the usual bug."""
    R.section("H3 — the same fix is present in both listeners")

    import FMOFP.MIL_STD_1553B.Bus_Controller.BC_connect.BC_socket as bc_socket
    rt_socket = _rt_module()

    for mod, cls_name in ((rt_socket, "RT_Listener"), (bc_socket, "BC_Listener")):
        tag = cls_name.split("_")[0]
        cls = getattr(mod, cls_name)
        R.check(f"{tag} declares a handler ceiling",
                isinstance(getattr(mod, "MAX_CONCURRENT_CONNECTIONS", None), int))
        for attr in ("_serve_connection", "_spawn_connection_handler",
                     "_drain_connection_handlers"):
            R.check(f"{tag} has {attr}", callable(getattr(cls, attr, None)))

        accept_src = inspect.getsource(cls.start_listening)
        R.check(f"{tag}'s accept loop hands off instead of serving inline",
                "_spawn_connection_handler" in accept_src
                and "self.handle_connection" not in accept_src)
        R.check(f"{tag}'s stop drains the workers",
                "_drain_connection_handlers" in
                inspect.getsource(cls.stop_listening))


def main():
    print("=" * 60)
    print("  H3: listener connection concurrency")
    print("=" * 60)

    for test in (test_both_listeners_were_fixed,
                 test_second_peer_is_accepted_while_the_first_holds_on,
                 test_the_second_peer_is_actually_served_not_just_accepted,
                 test_live_handlers_are_capped,
                 test_stop_waits_for_handlers,
                 test_pre_fix_serialises):
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
