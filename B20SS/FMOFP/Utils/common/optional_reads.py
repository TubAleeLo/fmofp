"""Reading optional fields out of sensor payloads without inventing a value.

A display that substitutes a literal for a field the sensor did not send is
presenting a measurement that was never taken.  On a weather radar that is
not a cosmetic problem: ``precip.get('intensity', 0.7)`` paints a grey area
of the sky as moderate-to-heavy rain, and ``cell.get('intensity', 0)``
paints a storm cell of unknown strength as harmless.  Both readings look
exactly like real ones to the crew -- same colour band, same numeric
label -- so there is nothing on screen to tell them apart.

The convention here is that an absent or unusable field reads back as
``None`` (exported as ``UNKNOWN`` for readability at the call site), and the
caller is then responsible for rendering "unknown" distinguishably rather
than picking a number.  Callers must not paper over the ``None``; the point
of returning it is that it cannot be mistaken for a measurement.
"""

from typing import Any, Mapping, Optional

# Re-exported so call sites can read ``if intensity is UNKNOWN:`` rather than
# comparing against a bare None, which is easy to skim past.
UNKNOWN = None

__all__ = ["UNKNOWN", "optional_float", "optional_position"]


def optional_float(
    source: Mapping[str, Any],
    *keys: str,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
) -> Optional[float]:
    """Return the first present key's value as a float, or ``None``.

    Args:
        source: mapping to read from.  A non-mapping reads as ``None``.
        *keys: candidate key names, tried in order.  The first key that is
            present and parses as a finite float wins; a key present with an
            unusable value (``None``, ``''``, ``'unknown'``, a dict) is
            skipped so a later alias can still supply the reading.
        minimum: if given, a value below this reads as ``None`` rather than
            being clamped -- an out-of-range reading is a broken reading, and
            clamping it would hand the caller a plausible-looking number.
        maximum: as ``minimum``, for the upper bound.

    Returns:
        The float, or ``None`` when no key yielded a usable one.
    """
    if not isinstance(source, Mapping):
        return None

    for key in keys:
        if key not in source:
            continue
        raw = source[key]
        if raw is None or isinstance(raw, bool):
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        # NaN and the infinities are not measurements.
        if value != value or value in (float("inf"), float("-inf")):
            continue
        if minimum is not None and value < minimum:
            continue
        if maximum is not None and value > maximum:
            continue
        return value

    return None


def optional_position(source: Mapping[str, Any], key: str = "position"):
    """Return ``(x, y)`` as floats, or ``None`` when the position is unusable.

    There is deliberately no ``(0.0, 0.0)`` fallback: on a plan-position
    display the origin is ownship, so a fallback of ``(0, 0)`` does not mean
    "somewhere unknown", it means "directly underneath the aircraft".
    """
    if not isinstance(source, Mapping):
        return None

    raw = source.get(key)
    if not isinstance(raw, (tuple, list)) or len(raw) < 2:
        return None

    try:
        x = float(raw[0])
        y = float(raw[1])
    except (TypeError, ValueError):
        return None

    if x != x or y != y:  # NaN
        return None

    return (x, y)
