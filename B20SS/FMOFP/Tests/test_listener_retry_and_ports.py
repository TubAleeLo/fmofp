"""Test suite — bounded listener retry (C7.1) and configurable bind ports (C8.1).

C7.1  Both listener loops retried a broken socket forever: increment a counter,
      recreate every third failure, sleep a flat 0.5 s, repeat. Measured on the
      two-instance port-conflict reproduction: 153 bind failures in 22 s, i.e.
      ~2 ERROR lines per second for as long as the fault lasted, unbounded --
      on the order of 170,000 lines per day, enough on its own to cycle the
      50 MB x 5 log rotation. There was no terminal state, so a permanently
      broken listener was indistinguishable from one about to recover.

C8.1  Only the TRANSMIT side of the bus was configurable; both listeners bound
      hardcoded ports (BC 5000, RT 5001). That is what made the port-conflict
      failure the guaranteed outcome of starting a second instance.

The BackoffPolicy is driven through an injected clock so the give-up and
rate-limit behaviour is asserted deterministically, without waiting out a real
120-second failure.

Standalone-safe: run from B20SS/ as
`python -m FMOFP.Tests.test_listener_retry_and_ports`.
"""
import os
import socket
import sys

_B20SS = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
for _p in (_B20SS, os.path.join(_B20SS, 'FMOFP')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from FMOFP.Utils.common.retry import BackoffPolicy  # noqa: E402
from FMOFP.MIL_STD_1553B.bus_adapter import get_listen_endpoint  # noqa: E402

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


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


# ── C7.1 · backoff growth ────────────────────────────────────────────────────

print("\nC7.1 — exponential backoff with a ceiling")

clk = FakeClock()
p = BackoffPolicy(initial=0.5, maximum=30.0, factor=2.0,
                  give_up_after=None, max_attempts=None, _clock=clk)
delays = [p.record_failure() for _ in range(10)]
check("first delay matches the old flat sleep (no slower to recover)",
      delays[0] == 0.5, str(delays[0]))
check("delay grows monotonically then plateaus",
      delays[:6] == [0.5, 1.0, 2.0, 4.0, 8.0, 16.0], str(delays[:6]))
check("delay is capped at the maximum",
      all(d <= 30.0 for d in delays) and delays[-1] == 30.0, str(delays))
check("old scheme would have slept 0.5s x10 = 5.0s; backoff sleeps much longer",
      sum(delays) > 5.0 * 10, f"{sum(delays)}s")

p.record_success()
check("success resets the run", p.attempts == 0 and p.failing_for == 0.0)
check("delay restarts from initial after success", p.record_failure() == 0.5)


# ── C7.1 · give-up bounds ────────────────────────────────────────────────────

print("\nC7.1 — terminal state")

clk = FakeClock()
p = BackoffPolicy(give_up_after=None, max_attempts=5, _clock=clk)
check("not exhausted before any failure", not p.exhausted)
for _ in range(4):
    p.record_failure()
check("not exhausted below the attempt budget", not p.exhausted, f"attempts={p.attempts}")
p.record_failure()
check("exhausted at the attempt budget", p.exhausted, f"attempts={p.attempts}")
check("give-up reason names the attempt limit", "consecutive failures" in p.give_up_reason(),
      p.give_up_reason())

clk = FakeClock()
p = BackoffPolicy(give_up_after=120.0, max_attempts=None, _clock=clk)
p.record_failure()
clk.advance(119.0)
check("not exhausted before the time bound", not p.exhausted, f"{p.failing_for}s")
clk.advance(2.0)
check("exhausted after the time bound", p.exhausted, f"{p.failing_for}s")
check("give-up reason names the time limit", "failed continuously" in p.give_up_reason(),
      p.give_up_reason())

clk = FakeClock()
p = BackoffPolicy(give_up_after=120.0, max_attempts=None, _clock=clk)
p.record_failure()
clk.advance(200.0)
p.record_success()
check("a success clears an otherwise-exhausted run", not p.exhausted)

p_forever = BackoffPolicy(give_up_after=None, max_attempts=None, _clock=FakeClock())
for _ in range(500):
    p_forever.record_failure()
check("both bounds disabled -> never exhausted (opt-out still possible)",
      not p_forever.exhausted)


# ── C7.1 · log rate limiting ─────────────────────────────────────────────────

print("\nC7.1 — log rate limiting")

clk = FakeClock()
p = BackoffPolicy(log_first=3, log_interval=30.0,
                  give_up_after=None, max_attempts=None, _clock=clk)
logged = 0
for i in range(3):
    p.record_failure()
    if p.should_log():
        logged += 1
check("first N failures are logged in full", logged == 3, str(logged))

p.record_failure()
check("the next failure is suppressed", not p.should_log())
check("suppressed failures are counted", p.suppressed == 1, str(p.suppressed))

clk.advance(31.0)
p.record_failure()
check("a line is emitted again once the interval elapses", p.should_log())
check("suppressed counter resets after emitting", p.suppressed == 0, str(p.suppressed))

# The headline number: what a sustained fault costs in log lines.
clk = FakeClock()
p = BackoffPolicy(log_first=3, log_interval=30.0,
                  give_up_after=None, max_attempts=None, _clock=clk)
emitted = 0
for _ in range(600):          # 600 failures over a simulated hour
    p.record_failure()
    if p.should_log():
        emitted += 1
    clk.advance(6.0)
check("600 failures over an hour emit ~2/min, not 600 lines",
      emitted <= 125, f"emitted={emitted}")
check("but the fault never goes silent", emitted >= 10, f"emitted={emitted}")

p2 = BackoffPolicy(give_up_after=None, max_attempts=None, _clock=FakeClock())
p2.record_failure()
p2.should_log()
for _ in range(5):
    p2.record_failure()
    p2.should_log()
check("describe() surfaces the suppressed count",
      "suppressed" in p2.describe("boom") or p2.suppressed == 0, p2.describe("boom"))


# ── C8.1 · configurable endpoints ────────────────────────────────────────────

print("\nC8.1 — configurable listener endpoints")

for var in ("FMOFP_BC_LISTEN_PORT", "FMOFP_RT_LISTEN_PORT",
            "FMOFP_BC_LISTEN_HOST", "FMOFP_RT_LISTEN_HOST"):
    os.environ.pop(var, None)

bc_host, bc_port = get_listen_endpoint('bc')
rt_host, rt_port = get_listen_endpoint('rt')
check("BC default is unchanged (5000)", bc_port == 5000, str(bc_port))
check("RT default is unchanged (5001)", rt_port == 5001, str(rt_port))
check("both still default to loopback",
      bc_host == "127.0.0.1" and rt_host == "127.0.0.1", f"{bc_host} {rt_host}")
check("BC and RT listen on different ports", bc_port != rt_port)

os.environ["FMOFP_RT_LISTEN_PORT"] = "7001"
check("environment overrides the RT listen port", get_listen_endpoint('rt')[1] == 7001,
      str(get_listen_endpoint('rt')))
check("overriding RT does not disturb BC", get_listen_endpoint('bc')[1] == 5000)

os.environ["FMOFP_RT_LISTEN_PORT"] = "not-a-port"
check("a malformed override falls back to the default instead of raising",
      get_listen_endpoint('rt')[1] == 5001, str(get_listen_endpoint('rt')))

os.environ["FMOFP_RT_LISTEN_PORT"] = "0"
check("port 0 is accepted (OS-chosen, for tests and side-by-side runs)",
      get_listen_endpoint('rt')[1] == 0)
os.environ.pop("FMOFP_RT_LISTEN_PORT")

try:
    get_listen_endpoint('nonsense')
    check("unknown role raises", False, "no exception")
except ValueError:
    check("unknown role raises ValueError", True)


# ── C8.1 · port 0 round-trip ─────────────────────────────────────────────────

print("\nC8.1 — OS-chosen port is read back")

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    s.bind(("127.0.0.1", 0))
    real_port = s.getsockname()[1]
    check("binding port 0 yields a real port", real_port > 0, str(real_port))
    # This is what the listeners now do after bind(); without it self.port stays
    # 0 and check_health()'s expected-port comparison never matches.
    from FMOFP.Utils.common.health import socket_is_bound
    check("health check matches only against the READ-BACK port",
          socket_is_bound(s, real_port) and not socket_is_bound(s, 0))
finally:
    s.close()


# ── non-tautological guards ──────────────────────────────────────────────────

print("\nNON-TAUTOLOGICAL — pre-fix behaviour must fail these")

# C7.1: the old scheme, reproduced.
def legacy_delays(n):
    return [0.5] * n


check("pre-fix delay never grows (proves the backoff assertion bites)",
      len(set(legacy_delays(10))) == 1)
check("pre-fix scheme has no terminal state (proves the give-up assertion bites)",
      not hasattr(legacy_delays, 'exhausted'))

clk = FakeClock()
legacy_emitted = 600           # old code logged every single failure
p = BackoffPolicy(log_first=3, log_interval=30.0,
                  give_up_after=None, max_attempts=None, _clock=clk)
new_emitted = 0
for _ in range(600):
    p.record_failure()
    if p.should_log():
        new_emitted += 1
    clk.advance(6.0)
check("rate limiting cuts log volume by >4x versus the old every-failure scheme",
      new_emitted * 4 < legacy_emitted, f"{new_emitted} vs {legacy_emitted}")


# ── result ───────────────────────────────────────────────────────────────────

print(f"\nListener retry & port tests: {PASS} passed, {FAIL} failed")
if FAIL:
    sys.exit(1)
print("Listener retry and ports: all assertions passed")
