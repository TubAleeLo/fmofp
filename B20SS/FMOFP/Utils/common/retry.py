"""
Bounded retry policy for the bus listeners (PI-1 story C7.1).

WHY THIS EXISTS
---------------
Both listener loops handled a socket error by incrementing a counter,
recreating the socket every third failure, sleeping a flat 0.5 s, and
repeating -- with no cap, no backoff, no escalation and no terminal state.

Measured on the two-instance port-conflict reproduction: 31 failed attempts
in 18 s from one listener, and 153 bind failures in 22 s across both. The
total is a function of runtime, not of the fault: roughly two errors per
second, indefinitely, at ERROR level. A single stuck listener would emit on
the order of 170,000 ERROR lines per day, which on its own cycles the
50 MB x 5 log rotation and destroys any chance of finding an unrelated
problem in the log.

WHAT THIS PROVIDES
------------------
Three things the old loop lacked, as one object so BC and RT cannot drift:

  * Exponential backoff with a ceiling, so a persistent fault costs one
    attempt every `maximum` seconds rather than two per second.

  * A give-up condition -- by elapsed time, attempt count, or both -- after
    which `exhausted` is True. The caller is expected to stop looping and
    let the health contract report the listener as unhealthy, which is what
    turns a silent log flood into an observable state (stories C6.1/C5.1).

  * Log rate limiting: the first `log_first` failures are logged, then at
    most one line per `log_interval` seconds carrying the suppressed count,
    so a persistent fault stays visible without drowning everything else.

Deliberately has no socket or logging dependency -- it decides, the caller
acts. That keeps it directly unit-testable with tiny values instead of
requiring a real 120-second failure to exercise.
"""

import time
from typing import Optional


class BackoffPolicy:
    """Decides how long to wait, whether to give up, and whether to log.

    Not thread-safe by design: each listener owns its own policy and drives it
    from its own loop thread.
    """

    def __init__(
        self,
        name: str = "listener",
        initial: float = 0.5,
        maximum: float = 30.0,
        factor: float = 2.0,
        give_up_after: Optional[float] = 120.0,
        max_attempts: Optional[int] = None,
        log_first: int = 3,
        log_interval: float = 30.0,
        _clock=time.monotonic,
    ) -> None:
        """
        Args:
            name: used by callers in log lines; carried here so the policy can
                be identified in a message without the caller re-deriving it.
            initial: first backoff delay, in seconds. Matches the old flat
                0.5 s sleep so the first retry is no slower than before.
            maximum: ceiling for the backoff delay.
            factor: multiplier applied per consecutive failure.
            give_up_after: seconds of *continuous* failure after which
                `exhausted` becomes True. None disables the time bound.
            max_attempts: consecutive failures after which `exhausted` becomes
                True. None disables the count bound. Whichever bound trips
                first wins; with both None the policy backs off forever but
                never gives up.
            log_first: how many consecutive failures to log in full before
                rate limiting engages.
            log_interval: minimum seconds between logged lines once rate
                limiting has engaged.
            _clock: injectable monotonic clock, for tests.
        """
        self.name = name
        self.initial = float(initial)
        self.maximum = float(maximum)
        self.factor = float(factor)
        self.give_up_after = give_up_after
        self.max_attempts = max_attempts
        self.log_first = int(log_first)
        self.log_interval = float(log_interval)
        self._clock = _clock

        self.attempts = 0
        self._first_failure_at: Optional[float] = None
        self._last_logged_at: Optional[float] = None
        self._suppressed = 0

    # ── state ────────────────────────────────────────────────────────────

    @property
    def exhausted(self) -> bool:
        """True once the caller should stop retrying and report unhealthy."""
        if self.attempts == 0:
            return False
        if self.max_attempts is not None and self.attempts >= self.max_attempts:
            return True
        if self.give_up_after is not None and self._first_failure_at is not None:
            return (self._clock() - self._first_failure_at) >= self.give_up_after
        return False

    @property
    def failing_for(self) -> float:
        """Seconds since the first failure of the current run, 0.0 if healthy."""
        if self._first_failure_at is None:
            return 0.0
        return self._clock() - self._first_failure_at

    @property
    def suppressed(self) -> int:
        """Failures not logged since the last logged line."""
        return self._suppressed

    # ── transitions ──────────────────────────────────────────────────────

    def record_failure(self) -> float:
        """Register one failure. Returns the number of seconds to wait."""
        now = self._clock()
        if self._first_failure_at is None:
            self._first_failure_at = now
        self.attempts += 1
        delay = min(self.initial * (self.factor ** (self.attempts - 1)), self.maximum)
        return delay

    def record_success(self) -> None:
        """Register a success, clearing the failure run entirely."""
        self.attempts = 0
        self._first_failure_at = None
        self._last_logged_at = None
        self._suppressed = 0

    def should_log(self) -> bool:
        """Whether this failure should produce a log line.

        Call once per failure, after record_failure(). Returns True for the
        first `log_first` failures of a run, then at most once per
        `log_interval`. When it returns True the suppressed counter is
        reset, so callers should read `suppressed` BEFORE acting on it --
        `describe()` does this correctly.
        """
        now = self._clock()
        if self.attempts <= self.log_first:
            self._last_logged_at = now
            self._suppressed = 0
            return True
        if self._last_logged_at is None or (now - self._last_logged_at) >= self.log_interval:
            self._last_logged_at = now
            self._suppressed = 0
            return True
        self._suppressed += 1
        return False

    def describe(self, detail: str = "") -> str:
        """A log line for the current failure run, including suppressed count."""
        parts = [f"{self.name}: attempt {self.attempts}"]
        if self._first_failure_at is not None:
            parts.append(f"failing for {self.failing_for:.1f}s")
        if self._suppressed:
            parts.append(f"{self._suppressed} similar suppressed")
        if detail:
            parts.append(detail)
        return " — ".join(parts)

    def give_up_reason(self) -> str:
        """Why `exhausted` is True, for the single ERROR line on giving up."""
        if self.max_attempts is not None and self.attempts >= self.max_attempts:
            return f"{self.attempts} consecutive failures (limit {self.max_attempts})"
        return f"failed continuously for {self.failing_for:.1f}s (limit {self.give_up_after}s)"
