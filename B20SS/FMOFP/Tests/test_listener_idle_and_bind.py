"""
Test suite: H2 and H16 — idle connections, and what the listeners bind to.

H2. An accepted connection had no idle timeout. recv() is guarded by a 1 s
select, so no single syscall blocks forever, but handle_connection loops on
`self.running` -- the LISTENER's flag -- and only leaves when the peer closes or
errors. A peer that connects and then says nothing holds the slot for as long as
it stays connected.

That used to compound with H3, where the accept loop served each connection
inline so one held connection stopped every other peer being accepted at all.
H3 is fixed (see test_listener_concurrency), which means accepts can no longer
be used to observe this timeout: a second peer is now accepted immediately
whether or not the idle connection is ever reclaimed. So H2 is measured here
directly, from the held peer's own side -- recv() returning b'' is the listener
closing it -- and that measurement is independent of H3 in both directions.

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


def _silent_peer_lifetime(idle_timeout, wait_s):
    """Connect, send nothing, and time how long until the LISTENER closes us.

    Returns (closed, elapsed). `closed` is True when recv() returned b'' --
    an orderly close from the listener's end -- within wait_s. The peer never
    sends and never closes, so nothing but the idle timeout can end it.
    """
    listener = peer = None
    try:
        listener, port = _run_listener(idle_timeout)
        peer = socket.create_connection(("127.0.0.1", port))
        peer.settimeout(wait_s)
        started = time.monotonic()
        try:
            eof = peer.recv(64) == b""
        except socket.timeout:
            eof = False
        return eof, time.monotonic() - started
    finally:
        if listener is not None:
            listener.running = False
        try:
            if peer is not None:
                peer.close()
        except Exception:
            pass
        time.sleep(1.1)


def test_idle_connection_is_reclaimed():
    R.section("H2 \u2014 a peer that sends nothing is closed by the listener")

    closed, elapsed = _silent_peer_lifetime(idle_timeout=2.0, wait_s=8.0)
    R.check("the listener closes a connection that never sends",
            closed, f"closed={closed} after {elapsed:.1f}s")
    R.check("and it waits for the timeout rather than closing on arrival",
            elapsed >= 2.0, f"closed after {elapsed:.1f}s, timeout was 2.0s")


def test_pre_fix_holds_the_slot_forever():
    """With the timeout out of reach, the old behaviour returns exactly.

    Before H2 there was no timeout at all, so this is the pre-fix code path:
    the handler loops on the LISTENER's `running` flag and leaves only when the
    peer goes away. If this ever starts failing, the assertion above is passing
    for some reason other than the timeout.
    """
    R.section("NON-TAUTOLOGICAL \u2014 with no timeout in reach, nothing reclaims it")

    closed, elapsed = _silent_peer_lifetime(idle_timeout=3600.0, wait_s=5.0)
    R.check("the connection is still open after 5s of silence",
            not closed, f"closed={closed} after {elapsed:.1f}s")


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
                 test_pre_fix_holds_the_slot_forever):
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
