"""
Component health contract (PI-1 story C2.1).

WHY THIS EXISTS
---------------
Before this module there were two competing health interfaces in the codebase
and no definition of which one was authoritative:

    check_health()   9 definitions across 7 files
    is_healthy()    22 definitions across 21 files

`SystemManager.check_component_health()` interrogated components with

    if hasattr(component, 'check_health'):

so the 17 classes that expose ONLY `is_healthy()` -- all five radars,
`RadarManagementSystem`, both messengers, the INS, `DisplayResponseService`,
and the Radar/FMS/FCS/Display message handlers -- were never asked at all.
Of the registered components, at most ~8 could be interrogated, and a
component implementing neither method was silently treated as healthy
because the `hasattr` guard simply skipped it.

That last part is the dangerous half. "We never asked" and "we asked and it
said yes" were indistinguishable, so the health sweep could report a clean
sweep over a system it had barely inspected.

THE CONTRACT
------------
A component is health-interrogable if it exposes `health_report()`,
`check_health()` or `is_healthy()`, resolved in that order. `health_report()`
returns a HealthReport directly and exists for adapters that must resolve their
real target at probe time (see DelegatedHealth); the other two return a bool.
The bool forms are supported permanently -- `is_healthy()` has eight
live internal call sites (RadarMessageHandler, DisplayMessageHandler,
FMSMessageHandler) that are not going away, and renaming 22 definitions to
unify the spelling would be churn with no behavioural benefit.

Where a class defines both `check_health()` and `is_healthy()` -- BC_Listener,
RT_Listener, AsyncMessageHandler, DisplayMessageHandler -- `check_health()`
wins, which is the historical behaviour of the sweep.

Three outcomes, not two:

    HEALTHY    the component was asked and said yes
    UNHEALTHY  the component was asked and said no, or raised
    UNKNOWN    the component exposes no health interface -- we did not ask

UNKNOWN is deliberately NOT an alias for HEALTHY. A caller deciding whether
the system is ready must be able to distinguish "nothing is wrong" from
"we have no idea", and the previous code could not.

Deliberately dependency-free (stdlib + the project logger) so it can be
imported from the socket layer, the system manager, and the tests without
creating an import cycle.
"""

import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from FMOFP.Utils.logger.sys_logger import get_logger

logger = get_logger()


class HealthState(Enum):
    """Outcome of interrogating one component."""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class HealthReport:
    """One component's health at one moment.

    `probed_via` records which method answered ('health_report', 'check_health',
    'is_healthy', or None when the component exposes none of them), so a
    confusing result can be traced back to the interface that produced it
    without re-deriving it.
    """

    name: str
    state: HealthState
    reason: str = ""
    probed_via: Optional[str] = None

    @property
    def is_healthy(self) -> bool:
        """True only for HEALTHY. UNKNOWN is not healthy -- see module docstring."""
        return self.state is HealthState.HEALTHY

    @property
    def is_unhealthy(self) -> bool:
        """True only for UNHEALTHY. UNKNOWN is not a failure either."""
        return self.state is HealthState.UNHEALTHY


#: Components whose failure means the system cannot do useful work, and which
#: therefore block readiness (story C5.1). The criterion is "if this is down,
#: the simulation cannot move data end to end" -- not "this is important".
#:
#: The bus listeners are here because a dead transport is exactly the failure
#: the two-instance port-conflict reproduction exposes, and the whole point of
#: this work is that such a system must not report itself operational.
#:
#: Deliberately NOT critical: the software config manager, flight-data
#: monitoring, fitness monitoring, the CLI threads, and the various airframe
#: monitors. Any of those being down degrades the simulation without making it
#: dishonest, and grounding boot on them would make readiness brittle.
CRITICAL_COMPONENTS = frozenset({
    "bc_listener",
    "rt_listener",
    "async_message_handler",
    "message_routing_service",
    "radar_management",
    "flightManagementSystem",
})


def probe(name: str, component: Any) -> HealthReport:
    """Interrogate one component against the contract above.

    Never raises: a component whose health check itself blows up is reported
    UNHEALTHY with the exception text as the reason, which is strictly more
    informative than the previous behaviour of logging and appending the name
    with no detail.
    """
    if component is None:
        return HealthReport(name, HealthState.UNKNOWN, "component is None")

    reporter = getattr(component, "health_report", None)
    if callable(reporter):
        try:
            report = reporter()
        except Exception as exc:  # noqa: BLE001
            return HealthReport(
                name,
                HealthState.UNHEALTHY,
                f"health_report() raised {type(exc).__name__}: {exc}",
                "health_report",
            )
        if isinstance(report, HealthReport):
            # Adapters don't know the key they were registered under; stamp it.
            return HealthReport(name, report.state, report.reason, report.probed_via)

    for method_name in ("check_health", "is_healthy"):
        method = getattr(component, method_name, None)
        if not callable(method):
            continue
        try:
            result = method()
        except Exception as exc:  # noqa: BLE001 - contract: a raising probe is a failure
            return HealthReport(
                name,
                HealthState.UNHEALTHY,
                f"{method_name}() raised {type(exc).__name__}: {exc}",
                method_name,
            )
        if result:
            return HealthReport(name, HealthState.HEALTHY, "", method_name)
        return HealthReport(
            name, HealthState.UNHEALTHY, f"{method_name}() returned {result!r}", method_name
        )

    return HealthReport(
        name,
        HealthState.UNKNOWN,
        "exposes no health interface "
        "(health_report(), check_health() or is_healthy())",
        None,
    )


class DelegatedHealth:
    """Health adapter that resolves its real target at probe time.

    Needed because the two bus listeners cannot simply be registered directly
    (story C3.1):

      * `Bus_Controller` and `Remote_Terminal` -- the objects `SystemManager`
        holds -- are thin wrappers that expose no health interface at all.
        Registering them would report UNKNOWN forever, which is the same blind
        spot in a new costume.

      * `BC_Listener` is NOT a singleton. `Bus_Controller.start_listener()`
        constructs a fresh `BC_Listener()` and keeps it as `self._listener`,
        so the module-level instance returned by `get_bc_listener()` is a
        DIFFERENT object that never binds a port and would report unhealthy
        forever -- a false negative that would block boot outright. (RT does
        use the global via `get_rt_listener()`; the two sides differ.)

      * The BC listener is created inside the listener THREAD, so it does not
        exist at registration time. Resolving late is the only correct option.

    Before the target exists the adapter reports UNKNOWN rather than UNHEALTHY,
    so a component that simply has not started yet is never mistaken for one
    that has failed.
    """

    def __init__(self, description: str, resolver: Any) -> None:
        self._description = description
        self._resolver = resolver

    def health_report(self) -> HealthReport:
        try:
            target = self._resolver()
        except Exception as exc:  # noqa: BLE001
            return HealthReport(
                self._description,
                HealthState.UNHEALTHY,
                f"resolving {self._description} raised {type(exc).__name__}: {exc}",
                "health_report",
            )
        if target is None:
            return HealthReport(
                self._description,
                HealthState.UNKNOWN,
                f"{self._description} not created yet",
                "health_report",
            )
        return probe(self._description, target)


def probe_all(components: Dict[str, Any]) -> List[HealthReport]:
    """Probe every component, preserving iteration order."""
    return [probe(name, component) for name, component in components.items()]


def socket_is_bound(sock: Any, expected_port: Optional[int] = None) -> bool:
    """True only if `sock` is a live socket actually bound to `expected_port`.

    This is the distinction story C6.1 turns on. A listener whose `setup_socket()`
    failed still holds a socket OBJECT -- construction succeeded, only `bind()`
    raised -- and its thread is still alive, spinning in the retry loop. Testing
    `self.running`, or even `socket_variable is not None`, reports such a listener
    as healthy while it can neither accept nor receive anything.

    An unbound socket answers `getsockname()` with port 0, so comparing the bound
    port against the port we intended is what actually separates "listening" from
    "holding a useless file descriptor".
    """
    if sock is None:
        return False
    try:
        if sock.fileno() < 0:  # closed
            return False
        bound_host, bound_port = sock.getsockname()[:2]
    except Exception:
        # Closed, detached, or not a socket -- all mean "not listening".
        return False
    if not bound_port:
        return False
    if expected_port is not None and bound_port != expected_port:
        return False
    return True


class HealthRegistry:
    """Thread-safe holder for the most recent sweep.

    The health monitor runs on its own thread while readiness is evaluated from
    a Qt timer on the main thread, so the last result crosses threads and needs
    a lock. Reads are cheap and frequent (every 100 ms during boot); writes
    happen once per health-check interval.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._reports: List[HealthReport] = []
        self._swept_at: float = 0.0

    def update(self, reports: List[HealthReport]) -> None:
        with self._lock:
            self._reports = list(reports)
            self._swept_at = time.time()

    def snapshot(self) -> List[HealthReport]:
        with self._lock:
            return list(self._reports)

    @property
    def swept_at(self) -> float:
        """Wall-clock time of the last sweep, or 0.0 if none has run."""
        with self._lock:
            return self._swept_at

    def unhealthy(self) -> List[HealthReport]:
        return [r for r in self.snapshot() if r.is_unhealthy]

    def unknown(self) -> List[HealthReport]:
        return [r for r in self.snapshot() if r.state is HealthState.UNKNOWN]

    def unhealthy_critical(self) -> List[HealthReport]:
        return [r for r in self.unhealthy() if r.name in CRITICAL_COMPONENTS]

    def has_swept(self) -> bool:
        return self.swept_at > 0.0
