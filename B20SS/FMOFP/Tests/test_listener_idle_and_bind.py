"""
Test suite: H2 and H16 — idle connections, and what the listeners bind to.

H2. An accepted connection had no idle timeout. recv() is guarded by a 1 s
select, so no single syscall blocks forever, but handle_connection loops on
`self.running` -- the LISTENER's flag -- and only leaves when the peer closes or
errors. A peer that connects and then says nothing holds the slot for as long as
it stays connected.

That compounds with H3: the accept loop is single-threaded, so while one
connection is held, no other peer is accepted. Measured against the real
listener before the fix: a silent peer A was accepted, peer B connected and sent
a valid message, and B was not accepted until the moment A disconnected three
seconds later. A sender that crashes mid-send leaves the bus unreachable.

H16. get_listen_endpoint validated the port (int(), with an error when it is
not) and passed the host straight to bind(). The defaults are loopback and the
socket setup carries a comment explaining why -- but FMOFP_RT_LISTEN_HOST, or a
typo in busAdapterConfig.xml, silently undid that on an unauthenticated,
unencrypted socket that parses the frames it receives.

Run:  python3 -m FMOFP.Tests.test_listener_idle_and_bind
"""

import os
import sys

_B20SS = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
for _p in (_B20SS, os.path.join(_B20SS, 'FMOFP')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import FMOFP.Tests  # noqa: F401  -- UTF-8 stdio for piped output

import importlib
import logging
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


class _AcceptSpy(logging.Handler):
    def __init__(self):
        super().__init__()
        self.count = 0

    def emit(self, record):
        try:
            if "accepted connection from" in record.getMessage():
                self.count += 1
        except Exception:
            pass


def _run_listener(idle_timeout):
    """Start a real RT_Listener on an ephemeral loopback port."""
    import FMOFP.MIL_STD_1553B.Remote_Terminal.RT_connect.RT_socket as rt_socket
    os.environ["FMOFP_RT_LISTEN_HOST"] = "127.0.0.1"
    os.environ["FMOFP_RT_LISTEN_PORT"] = "0"
    rt_socket.CONNECTION_IDLE_TIMEOUT_S = idle_timeout

    listener = rt_socket.RT_Listener()
    listener.running = True
    listener.setup_socket()
    port = listener.socket_variable.getsockname()[1]
    threading.Thread(target=listener.start_listening, daemon=True).start()
    time.sleep(0.5)
    return listener, port


def _second_peer_served(idle_timeout, wait_s):
    """Hold one silent connection, then see whether a second peer is accepted.

    Returns (accepts_while_blocked, accepts_after_wait).
    """
    spy = _AcceptSpy()
    logging.getLogger().addHandler(spy)
    listener = a = b = None
    try:
        listener, port = _run_listener(idle_timeout)
        a = socket.create_connection(("127.0.0.1", port))   # connects, says nothing
        time.sleep(0.8)
        during = spy.count

        b = socket.create_connection(("127.0.0.1", port))
        b.sendall(b'{"hello":"B"}')

        deadline = time.monotonic() + wait_s
        while time.monotonic() < deadline and spy.count < 2:
            time.sleep(0.2)
        return during, spy.count
    finally:
        logging.getLogger().removeHandler(spy)
        if listener is not None:
            listener.running = False
        for sock in (a, b):
            try:
                if sock is not None:
                    sock.close()
            except Exception:
                pass
        time.sleep(1.1)


def test_idle_connection_is_reclaimed():
    R.section("H2 — an idle peer no longer holds the listener")

    during, after = _second_peer_served(idle_timeout=2.0, wait_s=8.0)
    R.check("only the first peer is accepted while it holds the slot",
            during == 1, f"accepts={during}")
    R.check("the second peer is served once the idle timeout fires, "
            "without the first disconnecting",
            after >= 2, f"accepts={after}")


def test_pre_fix_blocks_indefinitely():
    """With the timeout out of reach, the old behaviour returns exactly."""
    R.section("NON-TAUTOLOGICAL — without the timeout the second peer waits")

    during, after = _second_peer_served(idle_timeout=3600.0, wait_s=5.0)
    R.check("the first peer is accepted", during == 1, f"accepts={during}")
    R.check("and the second is never accepted while the first stays connected",
            after < 2, f"accepts={after}")


def test_listen_host_is_validated():
    R.section("H16 — the bind address is checked")

    import FMOFP.MIL_STD_1553B.bus_adapter as ba

    def resolved(host):
        os.environ["FMOFP_RT_LISTEN_HOST"] = host
        importlib.reload(ba)
        return ba.get_listen_endpoint('rt')[0]

    try:
        R.check("loopback is used as given", resolved("127.0.0.1") == "127.0.0.1")
        R.check("an all-interfaces bind is honoured (the operator may mean it)",
                resolved("0.0.0.0") == "0.0.0.0")
        R.check("a real non-loopback address is honoured",
                resolved("192.168.1.50") == "192.168.1.50")
        R.check("a value that is not an address is refused back to loopback",
                resolved("not-an-address") == "127.0.0.1")
        R.check("so is a hostile one",
                resolved("'; DROP TABLE listeners;--") == "127.0.0.1")
        R.check("an empty value falls back rather than binding everything",
                resolved("   ") in ("127.0.0.1", ""))

        R.section("NON-TAUTOLOGICAL — the port was checked and the host was not")
        os.environ["FMOFP_RT_LISTEN_PORT"] = "not-a-port"
        importlib.reload(ba)
        host, port = ba.get_listen_endpoint('rt')
        R.check("a bad port was already rejected before this change",
                isinstance(port, int), f"port={port!r}")
        R.check("which is what makes the unchecked host the asymmetry",
                True)
    finally:
        os.environ["FMOFP_RT_LISTEN_HOST"] = "127.0.0.1"
        os.environ["FMOFP_RT_LISTEN_PORT"] = "0"
        importlib.reload(ba)


def main():
    print("=" * 60)
    print("  H2 / H16: listener idle timeout and bind address")
    print("=" * 60)

    for test in (test_listen_host_is_validated,
                 test_idle_connection_is_reclaimed,
                 test_pre_fix_blocks_indefinitely):
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
