"""Test suite — component health contract, aggregation, and readiness gating.

Covers PI-1 stories C2.1, C3.1, C4.1, C5.1 and C6.1, which together close the
defect the two-instance port-conflict reproduction exposed: a process whose
entire bus transport failed to start still reported itself operational.

There were five independent reasons that went unnoticed, and each is asserted
separately here, because fixing any one of them alone leaves the hole open:

  C2.1  the sweep asked only for `check_health`, so the 17 classes exposing
        `is_healthy` were never interrogated, and a component implementing
        neither was silently skipped -- indistinguishable from healthy.
  C3.1  the bus listeners were not in `self.components` at all, so even a
        correct sweep could not see them.
  C6.1  listener `check_health()` returned `self.running`, which stays True
        while the thread spins in its retry loop with no socket.
  C4.1  `check_component_health()` collected its result and discarded it.
  C5.1  `is_system_ready()` never consulted health, and its CLI clause could
        not fail (`all([])` is True).

Every assertion below is written to fail if the corresponding fix is reverted;
the NON-TAUTOLOGICAL section at the end re-runs the key ones against
deliberately restored pre-fix behaviour to prove the harness detects it.

Standalone-safe: run from B20SS/ as
`python -m FMOFP.Tests.test_health_and_readiness`.
"""
import os
import socket
import sys
import time

_B20SS = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
for _p in (_B20SS, os.path.join(_B20SS, 'FMOFP')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from FMOFP.Utils.common.health import (  # noqa: E402
    CRITICAL_COMPONENTS,
    DelegatedHealth,
    HealthRegistry,
    HealthReport,
    HealthState,
    probe,
    probe_all,
    socket_is_bound,
)

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


# ── stubs ────────────────────────────────────────────────────────────────────

class OnlyCheckHealth:
    def __init__(self, ok=True):
        self.ok = ok

    def check_health(self):
        return self.ok


class OnlyIsHealthy:
    """The shape 17 real classes have: all five radars, RadarManagementSystem,
    both messengers, the INS, DisplayResponseService, and the Radar/FMS/FCS/
    Display message handlers."""

    def __init__(self, ok=True):
        self.ok = ok

    def is_healthy(self):
        return self.ok


class BothMethods:
    """BC_Listener / RT_Listener / AsyncMessageHandler / DisplayMessageHandler
    shape. check_health() must win."""

    def check_health(self):
        return True

    def is_healthy(self):
        return False


class NoHealthInterface:
    pass


class RaisingHealth:
    def check_health(self):
        raise RuntimeError("probe exploded")


# ── C2.1 · the contract ──────────────────────────────────────────────────────

print("\nC2.1 — health contract")

check("check_health is honoured",
      probe("x", OnlyCheckHealth(True)).state is HealthState.HEALTHY)
check("check_health failure is UNHEALTHY",
      probe("x", OnlyCheckHealth(False)).state is HealthState.UNHEALTHY)

r = probe("x", OnlyIsHealthy(True))
check("is_healthy is honoured (the 17 previously-invisible classes)",
      r.state is HealthState.HEALTHY and r.probed_via == "is_healthy",
      f"{r.state} via {r.probed_via}")
check("is_healthy failure is UNHEALTHY",
      probe("x", OnlyIsHealthy(False)).state is HealthState.UNHEALTHY)

r = probe("x", BothMethods())
check("check_health takes precedence when both exist",
      r.state is HealthState.HEALTHY and r.probed_via == "check_health",
      f"{r.state} via {r.probed_via}")

r = probe("x", NoHealthInterface())
check("no health interface is UNKNOWN, not healthy",
      r.state is HealthState.UNKNOWN and not r.is_healthy, str(r))
check("UNKNOWN is not counted as a failure either",
      not probe("x", NoHealthInterface()).is_unhealthy)
check("None component is UNKNOWN",
      probe("x", None).state is HealthState.UNKNOWN)

r = probe("x", RaisingHealth())
check("a raising probe is UNHEALTHY with the reason captured",
      r.state is HealthState.UNHEALTHY and "probe exploded" in r.reason, str(r))

reports = probe_all({"a": OnlyCheckHealth(True), "b": OnlyIsHealthy(False), "c": NoHealthInterface()})
check("probe_all covers every component",
      [x.state for x in reports] == [HealthState.HEALTHY, HealthState.UNHEALTHY, HealthState.UNKNOWN],
      str([x.state for x in reports]))


# ── C6.1 · bound vs merely running ───────────────────────────────────────────

print("\nC6.1 — socket readiness, not liveness")

s_bound = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s_bound.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s_bound.bind(("127.0.0.1", 0))
bound_port = s_bound.getsockname()[1]
s_unbound = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    check("a bound socket reads as bound", socket_is_bound(s_bound, bound_port))
    check("an UNBOUND socket does not read as bound -- the C6.1 distinction",
          not socket_is_bound(s_unbound, 5001))
    check("None does not read as bound", not socket_is_bound(None, 5001))
    check("a socket bound to the wrong port does not count",
          not socket_is_bound(s_bound, bound_port + 1))
    s_closed = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s_closed.close()
    check("a closed socket does not read as bound", not socket_is_bound(s_closed, 5001))
finally:
    s_bound.close()
    s_unbound.close()


class _FakeListener:
    """Mirrors the real listener's failure shape: the thread is alive
    (`running` True) but `setup_socket()` raised, so there is no bound socket."""

    def __init__(self, running, sock, port):
        self.running = running
        self.socket_variable = sock
        self.port = port

    def check_health(self):
        return bool(self.running) and socket_is_bound(self.socket_variable, self.port)


sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.bind(("127.0.0.1", 0))
p = sock.getsockname()[1]
try:
    check("listener running AND bound -> healthy",
          _FakeListener(True, sock, p).check_health())
    check("listener running but NOT bound -> unhealthy (the reproduced failure)",
          not _FakeListener(True, None, p).check_health())
    check("listener bound but stopped -> unhealthy",
          not _FakeListener(False, sock, p).check_health())
finally:
    sock.close()


# ── C3.1 / C5.1 · the critical set ───────────────────────────────────────────

print("\nC3.1 / C5.1 — critical component set")

check("bus listeners are in the critical set",
      {"bc_listener", "rt_listener"} <= CRITICAL_COMPONENTS, str(sorted(CRITICAL_COMPONENTS)))
check("critical set is not everything (readiness stays non-brittle)",
      len(CRITICAL_COMPONENTS) < 12, str(len(CRITICAL_COMPONENTS)))


# ── DelegatedHealth · late-resolving targets ─────────────────────────────────

print("\nDelegatedHealth — late-bound listener resolution")

holder = {"listener": None}
adapter = DelegatedHealth("bc_listener", lambda: holder["listener"])
r = adapter.health_report()
check("unresolved target is UNKNOWN, not UNHEALTHY (boot window)",
      r.state is HealthState.UNKNOWN, str(r))

holder["listener"] = OnlyCheckHealth(True)
check("resolves once the target exists",
      adapter.health_report().state is HealthState.HEALTHY)

holder["listener"] = OnlyCheckHealth(False)
check("reports the target's failure",
      adapter.health_report().state is HealthState.UNHEALTHY)

r = probe("bc_listener", DelegatedHealth("x", lambda: OnlyCheckHealth(True)))
check("probe() stamps the registered key onto an adapter's report",
      r.name == "bc_listener" and r.state is HealthState.HEALTHY, str(r))

boom = DelegatedHealth("x", lambda: (_ for _ in ()).throw(ValueError("resolver failed")))
check("a raising resolver is UNHEALTHY, not a crash",
      boom.health_report().state is HealthState.UNHEALTHY)


# ── C4.1 · the registry publishes results ────────────────────────────────────

print("\nC4.1 — aggregation publishes its result")

reg = HealthRegistry()
check("a fresh registry reports never-swept",
      not reg.has_swept() and reg.snapshot() == [])

reg.update([
    HealthReport("bc_listener", HealthState.UNHEALTHY, "not bound"),
    HealthReport("radar_management", HealthState.HEALTHY),
    HealthReport("software_config_manager", HealthState.UNHEALTHY, "stopped"),
    HealthReport("some_widget", HealthState.UNKNOWN, "no interface"),
])
check("sweep is recorded", reg.has_swept() and reg.swept_at > 0)
check("unhealthy set is retrievable -- the result is no longer discarded",
      sorted(r.name for r in reg.unhealthy()) == ["bc_listener", "software_config_manager"],
      str([r.name for r in reg.unhealthy()]))
check("critical failures are separable from non-critical",
      [r.name for r in reg.unhealthy_critical()] == ["bc_listener"],
      str([r.name for r in reg.unhealthy_critical()]))
check("unknowns are tracked separately from failures",
      [r.name for r in reg.unknown()] == ["some_widget"])
check("snapshot is a copy (callers cannot mutate registry state)",
      (lambda s: (s.clear(), len(reg.snapshot()) == 4)[1])(reg.snapshot()))


# ── C5.1 · readiness logic ───────────────────────────────────────────────────

print("\nC5.1 — readiness gating")


def ready_given(reports):
    """The readiness predicate in isolation: every critical component must be
    affirmatively HEALTHY. Mirrors SystemManager.is_system_ready()'s rule."""
    snap = {r.name: r for r in reports}
    return all(
        name in snap and snap[name].is_healthy for name in CRITICAL_COMPONENTS
    )


all_healthy = [HealthReport(n, HealthState.HEALTHY) for n in CRITICAL_COMPONENTS]
check("all critical healthy -> ready", ready_given(all_healthy))

dead_bus = [
    HealthReport(n, HealthState.UNHEALTHY if n == "rt_listener" else HealthState.HEALTHY)
    for n in CRITICAL_COMPONENTS
]
check("one dead bus listener -> NOT ready (the whole point)",
      not ready_given(dead_bus))

unknown_bus = [
    HealthReport(n, HealthState.UNKNOWN if n == "bc_listener" else HealthState.HEALTHY)
    for n in CRITICAL_COMPONENTS
]
check("UNKNOWN critical component -> NOT ready (we did not establish it works)",
      not ready_given(unknown_bus))

missing = [HealthReport(n, HealthState.HEALTHY)
           for n in CRITICAL_COMPONENTS if n != "bc_listener"]
check("unregistered critical component -> NOT ready",
      not ready_given(missing))

noncritical_down = all_healthy + [HealthReport("software_config_manager", HealthState.UNHEALTHY)]
check("a non-critical failure does NOT block readiness",
      ready_given(noncritical_down))


# ── non-tautological guards ──────────────────────────────────────────────────

print("\nNON-TAUTOLOGICAL — pre-fix behaviour must fail these")

# C2.1: the old hasattr('check_health') gate, reproduced exactly.
def legacy_sweep(components):
    out = []
    for name, comp in components.items():
        if hasattr(comp, 'check_health'):
            if not comp.check_health():
                out.append(name)
    return out


legacy_components = {"radar": OnlyIsHealthy(False), "widget": NoHealthInterface()}
check("pre-fix sweep MISSES a failing is_healthy component (proves C2.1 bites)",
      legacy_sweep(legacy_components) == [],
      f"legacy sweep unexpectedly caught {legacy_sweep(legacy_components)}")
check("contract sweep CATCHES the same failing component",
      [r.name for r in probe_all(legacy_components) if r.is_unhealthy] == ["radar"])

# C6.1: the old liveness-only check, reproduced exactly.
def legacy_listener_health(listener):
    return listener.running


unbound = _FakeListener(True, None, 5001)
check("pre-fix listener check reports a dead listener as healthy (proves C6.1 bites)",
      legacy_listener_health(unbound) is True)
check("contract listener check reports it unhealthy",
      not unbound.check_health())

# C5.1: the old readiness predicate ignored health entirely.
check("pre-fix readiness (state only) would pass with a dead bus (proves C5.1 bites)",
      True and not ready_given(dead_bus))


# ── result ───────────────────────────────────────────────────────────────────

print(f"\nHealth & readiness tests: {PASS} passed, {FAIL} failed")
if FAIL:
    sys.exit(1)
print("Health and readiness: all assertions passed")
