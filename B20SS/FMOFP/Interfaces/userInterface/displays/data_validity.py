"""Field-level data validity for flight displays.

Why this exists (H9 and the wider display-fabrication findings, Sept 2026):
every display in this project seeded its fields with plausible flight values and
then kept the last value forever, because the update path is written as

    self.altitude = flight_data['navigation'].get('altitude', self.altitude)

With no publisher, or after one stops, the display shows a fully populated and
entirely fictitious picture -- the PFD read 30,000 ft / 450 kt / Mach 0.75 --
indistinguishable from live data. There was no validity flag anywhere in
displays/pfd.py and no X-flag drawn.

The rule this module enforces: a value is only shown when a publisher actually
supplied it recently. Otherwise the display says so, visibly.

Two pieces:

  FieldValidity        -- per-field "when did real data last arrive"
  draw_invalid_overlay -- the amber crosshatch + X that replaces a readout

Deliberately has no Qt dependency in FieldValidity, so it is testable headless
without a QApplication; only the painter helper touches PyQt6.
"""

import time

# How long a field stays valid after its last update. Displays poll their
# sources at 10 Hz, so two seconds is ~20 missed updates: long enough not to
# flicker on a single hiccup, short enough that a dead feed is obvious.
DEFAULT_STALE_AFTER_S = 2.0

# Amber, per the convention for "data invalid" on a flight display.
INVALID_COLOUR = (255, 176, 0)


class FieldValidity:
    """Tracks, per named field, when a publisher last supplied a real value.

    Fields start INVALID: nothing has been published yet, which is exactly the
    state the displays previously misrepresented as level flight.
    """

    def __init__(self, stale_after_s: float = DEFAULT_STALE_AFTER_S):
        self.stale_after_s = stale_after_s
        self._stamps = {}

    def mark(self, *names: str) -> None:
        """Record that real data just arrived for these fields."""
        now = time.monotonic()
        for name in names:
            self._stamps[name] = now

    def mark_from(self, source: dict, mapping: dict) -> None:
        """Mark each field whose key is actually present in `source`.

        `mapping` is {field_name: key_in_source}. A key that is absent leaves
        the field's previous validity untouched, so it ages out and goes stale
        rather than being refreshed by its own last value.
        """
        present = [field for field, key in mapping.items() if key in source]
        if present:
            self.mark(*present)

    def is_valid(self, name: str, now: float = None) -> bool:
        stamp = self._stamps.get(name)
        if stamp is None:
            return False
        now = time.monotonic() if now is None else now
        return (now - stamp) <= self.stale_after_s

    def age(self, name: str, now: float = None):
        """Seconds since the field last had real data, or None if it never has."""
        stamp = self._stamps.get(name)
        if stamp is None:
            return None
        now = time.monotonic() if now is None else now
        return now - stamp

    def invalidate(self, *names: str) -> None:
        for name in names:
            self._stamps.pop(name, None)

    def any_invalid(self, *names: str) -> bool:
        return any(not self.is_valid(n) for n in names)


def draw_invalid_overlay(painter, rect, label: str = "NO DATA") -> None:
    """Paint the standard invalid-data marking over `rect`.

    An amber X across the box plus diagonal crosshatch, and the label if it
    fits. Drawn instead of a numeric readout, never on top of one, so there is
    no way to read a stale number through the flag.
    """
    from PyQt6.QtCore import Qt, QLineF
    from PyQt6.QtGui import QPen, QColor, QFont

    amber = QColor(*INVALID_COLOUR)
    x1, y1 = float(rect.left()), float(rect.top())
    x2, y2 = float(rect.right()), float(rect.bottom())

    painter.save()
    try:
        # Crosshatch, light enough to read the label over.
        painter.setPen(QPen(amber, 1, Qt.PenStyle.SolidLine))
        step = 8.0
        span = (x2 - x1) + (y2 - y1)
        offset = 0.0
        while offset <= span:
            painter.drawLine(QLineF(
                max(x1, x1 + offset - (y2 - y1)), min(y2, y1 + offset),
                min(x2, x1 + offset), max(y1, y1 + offset - (x2 - x1))))
            offset += step

        # The X itself, heavier so it reads at a glance.
        painter.setPen(QPen(amber, 2, Qt.PenStyle.SolidLine))
        painter.drawLine(QLineF(x1, y1, x2, y2))
        painter.drawLine(QLineF(x1, y2, x2, y1))
        painter.drawRect(rect)

        if label and (x2 - x1) >= 40:
            font = QFont("Arial", 8, QFont.Weight.Bold)
            painter.setFont(font)
            painter.setPen(QPen(amber))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)
    finally:
        painter.restore()
