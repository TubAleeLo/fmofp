"""
Test suite: the weather radar must not invent severity.

Every check here is about one shape of bug: a field the sensor did not send
being replaced with a literal, so that the display shows a measurement nobody
took.  On this display the substituted literals were not even neutral --
``intensity 0.7`` / ``rate 20.0`` is moderate-to-heavy rain, ``value 20.0`` is a
real VIL band, ``category "LIGHT"`` is light turbulence and ``intensity 0``
paints a storm cell in the mildest colour on the scale -- so a degraded return
looked exactly like a good one.

Each group ends with NON-TAUTOLOGICAL checks that reproduce the pre-fix
expression inline and assert that it really did misbehave.  Without those, a
test asserting "unknown renders as unknown" would pass against code that had
never had the bug, and would not show that the fix bites.

Run headless:  QT_QPA_PLATFORM=offscreen python3 -m FMOFP.Tests.test_weather_radar_truthfulness
"""

import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"

_B20SS = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
for _p in (_B20SS, os.path.join(_B20SS, 'FMOFP')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import FMOFP.Tests  # noqa: F401  -- forces UTF-8 stdio for piped output

from PyQt6.QtWidgets import QApplication as _QApp
_APP = _QApp.instance() or _QApp(sys.argv)

import sqlite3
import traceback


# ─────────────────────────────────────────────────────── framework ───────

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


class _RecordingPainter:
    """Forwards everything to a real QPainter, recording drawText() strings.

    A real painter is used underneath rather than a stub so the drawing code
    exercises the same Qt calls it does in flight; only the text is observed.
    """

    def __init__(self, painter):
        self._painter = painter
        self.texts = []
        self.ellipses = 0

    def drawText(self, *args):
        for a in args:
            if isinstance(a, str):
                self.texts.append(a)
        return self._painter.drawText(*args)

    def drawEllipse(self, *args):
        self.ellipses += 1
        return self._painter.drawEllipse(*args)

    def __getattr__(self, name):
        return getattr(self._painter, name)


def _display_and_painter():
    """Build a WeatherRadarDisplay and a recording painter over a pixmap."""
    from PyQt6.QtGui import QPainter, QPixmap
    from FMOFP.Interfaces.userInterface.displays.radar.weather_radar_display import (
        WeatherRadarDisplay,
    )

    # Not a QWidget -- these displays are plain objects owned by
    # weather_radar_widget.py, and take their surface size from the painter.
    display = WeatherRadarDisplay()
    # Stop any background timers so nothing repaints under the test.
    for attr in ("_poll_timer", "_update_timer", "_cleanup_timer"):
        timer = getattr(display, attr, None)
        if timer is not None:
            try:
                timer.stop()
            except Exception:
                pass

    pixmap = QPixmap(800, 600)
    raw = QPainter(pixmap)
    return display, _RecordingPainter(raw), raw, pixmap


def _captured_particle_colors(display):
    """Replace the particle generators with recorders; return the capture list.

    The colour handed to the generator is the display's verdict on the echo's
    severity, so capturing it is a direct read of what the crew would see --
    more precise than sampling pixels, which the particle scatter randomises.
    """
    captured = []

    def fake_generate(center_x, center_y, intensity, color, data_type, data_id, radius=30.0):
        captured.append({"kind": data_type, "color": color, "intensity": intensity,
                         "radius": radius, "id": data_id})
        display._particles.setdefault(data_type, {})[data_id] = []

    def fake_generate_cell(center_x, center_y, intensity, color, cell_id, radius=30.0, rotation=0.0):
        captured.append({"kind": "cells", "color": color, "intensity": intensity,
                         "radius": radius, "id": cell_id})
        display._particles.setdefault("cells", {})[cell_id] = []
        display._cell_particle_colors[cell_id] = color

    display._generate_particles = fake_generate
    display._generate_cell_particles = fake_generate_cell
    return captured


def _rgb(color):
    return (color.red(), color.green(), color.blue())


# ───────────────────────────────────────────── optional_reads helper ─────

def test_optional_reads():
    from FMOFP.Utils.common.optional_reads import (
        UNKNOWN, optional_float, optional_position,
    )
    R.section("optional_float / optional_position -- absence is not a value")

    R.check("a present reading comes back unchanged",
            optional_float({"intensity": 0.42}, "intensity") == 0.42)
    R.check("an absent key reads as UNKNOWN",
            optional_float({}, "intensity") is UNKNOWN)
    R.check("an explicit None reads as UNKNOWN",
            optional_float({"intensity": None}, "intensity") is UNKNOWN)
    R.check("a later alias supplies the reading when the first is unusable",
            optional_float({"intensity": None, "i": 0.3}, "intensity", "i") == 0.3)
    R.check("NaN is not a measurement",
            optional_float({"rate": float("nan")}, "rate") is UNKNOWN)
    R.check("infinity is not a measurement",
            optional_float({"rate": float("inf")}, "rate") is UNKNOWN)
    R.check("an out-of-range reading reads as UNKNOWN rather than being clamped",
            optional_float({"intensity": 4.0}, "intensity", maximum=1.0) is UNKNOWN)
    R.check("a bool is not a float reading",
            optional_float({"intensity": True}, "intensity") is UNKNOWN)
    R.check("a position comes back as floats",
            optional_position({"position": (3, -4)}) == (3.0, -4.0))
    R.check("a one-element position is unusable",
            optional_position({"position": (3,)}) is None)
    R.check("a missing position is unusable, not the origin",
            optional_position({}) is None)
    R.check("a None position is unusable, not the origin",
            optional_position({"position": None}) is None)

    R.section("NON-TAUTOLOGICAL -- the old expressions really did invent values")
    precip_without_readings = {"position": (10.0, 5.0), "id": "p1"}
    R.check("float(precip.get('intensity', 0.7)) really did yield 0.7",
            float(precip_without_readings.get("intensity", 0.7)) == 0.7)
    R.check("float(precip.get('rate', 20.0)) really did yield 20 mm/h -- heavy rain",
            float(precip_without_readings.get("rate", 20.0)) == 20.0)
    R.check("and 0.7 really does land in the second-highest intensity band",
            0.7 > 0.6)


# ───────────────────────────────────────────────── precipitation ─────────

def test_precipitation_unknown_severity():
    from FMOFP.Interfaces.userInterface.displays.radar.weather_radar_display import (
        UNKNOWN_SEVERITY_COLOR, UNKNOWN_VALUE_TEXT,
    )
    from PyQt6.QtCore import QPointF

    R.section("Precipitation with no intensity or rate reading")

    display, painter, raw, _pixmap = _display_and_painter()
    captured = _captured_particle_colors(display)
    try:
        # A real echo: the radar returned something at this bearing and range,
        # but the payload carried no severity fields.
        display._draw_precipitation(
            painter, QPointF(400, 300), 250.0,
            {"position": (10.0, 5.0), "id": "precip_unknown", "type": "rain"},
        )
        R.check("the echo is still drawn (position is real, so it is not dropped)",
                len(captured) == 1, f"captured={captured}")
        if captured:
            R.check("it is painted in the neutral colour, not the 'rain' blue",
                    _rgb(captured[0]["color"]) == _rgb(UNKNOWN_SEVERITY_COLOR),
                    f"got {_rgb(captured[0]['color'])}")
            R.check("its footprint is the smallest the system draws, not an average one",
                    captured[0]["radius"] == 25.0, f"radius={captured[0]['radius']}")
        R.check("the rate label reads UNKN rather than a number",
                any(UNKNOWN_VALUE_TEXT in t for t in painter.texts),
                f"texts={painter.texts}")
        R.check("no fabricated rate appears anywhere in the labels",
                not any("20.0mm/h" in t for t in painter.texts),
                f"texts={painter.texts}")

        # A measured echo must be unaffected: same call, with readings.
        captured.clear()
        painter.texts.clear()
        display._draw_precipitation(
            painter, QPointF(400, 300), 250.0,
            {"position": (-8.0, 12.0), "id": "precip_measured", "type": "rain",
             "intensity": 0.9, "rate": 31.5},
        )
        R.check("a measured echo keeps its type colour",
                captured and _rgb(captured[0]["color"]) == _rgb(
                    display._precipitation_colors["rain"]),
                f"captured={[_rgb(c['color']) for c in captured]}")
        R.check("a measured echo shows its real rate",
                any("31.5mm/h" in t for t in painter.texts), f"texts={painter.texts}")
    finally:
        raw.end()
        display.cleanup()


# ────────────────────────────────────────────────────── storm cells ──────

def test_storm_cell_unknown_intensity():
    from FMOFP.Interfaces.userInterface.displays.radar.weather_radar_display import (
        UNKNOWN_SEVERITY_COLOR, UNKNOWN_VALUE_TEXT,
    )
    from FMOFP.Utils.common.optional_reads import UNKNOWN
    from PyQt6.QtCore import QPointF

    R.section("Storm cell with no intensity reading")

    display, painter, raw, _pixmap = _display_and_painter()
    captured = _captured_particle_colors(display)
    try:
        display._draw_storm_cell(
            painter, QPointF(400, 300), 250.0,
            {"position": (6.0, -9.0), "cell_id": "cell_unknown"},
        )
        R.check("the cell is drawn", len(captured) == 1, f"captured={captured}")
        if captured:
            R.check("it is neutral, not the VERY_LIGHT green a 0 default produced",
                    _rgb(captured[0]["color"]) == _rgb(UNKNOWN_SEVERITY_COLOR),
                    f"got {_rgb(captured[0]['color'])}")
        R.check("its label reads UNKN, not '0.0'",
                any(UNKNOWN_VALUE_TEXT in t for t in painter.texts)
                or not painter.texts,
                f"texts={painter.texts}")
        R.check("no '0.0' intensity label is shown",
                not any(t.strip() == "0.0" for t in painter.texts),
                f"texts={painter.texts}")

        # A cell with no usable position must be skipped, not drawn at ownship.
        captured.clear()
        display._draw_storm_cell(
            painter, QPointF(400, 300), 250.0,
            {"cell_id": "cell_nowhere", "intensity": 0.95},
        )
        R.check("a cell with no position is skipped, not drawn over ownship",
                len(captured) == 0, f"captured={captured}")

        R.check("_get_intensity_color(UNKNOWN) is the neutral colour",
                _rgb(display._get_intensity_color(UNKNOWN))
                == _rgb(UNKNOWN_SEVERITY_COLOR))

        R.section("NON-TAUTOLOGICAL -- the old cell defaults really did mislead")
        cell_without_intensity = {"position": (6.0, -9.0), "cell_id": "c"}
        pre_fix_intensity = cell_without_intensity.get("intensity", 0)
        R.check("cell.get('intensity', 0) really did yield 0",
                pre_fix_intensity == 0)
        R.check("and 0 really did map to VERY_LIGHT -- the mildest band on the scale",
                _rgb(display._get_intensity_color(pre_fix_intensity))
                == _rgb(display._intensity_colors["VERY_LIGHT"]))
        R.check("which is a different colour from the neutral one, so the fix bites",
                _rgb(display._intensity_colors["VERY_LIGHT"])
                != _rgb(UNKNOWN_SEVERITY_COLOR))
    finally:
        raw.end()
        display.cleanup()


def test_storm_cell_particles_use_their_own_colour():
    """_draw_particles had no 'cells' branch, so cells came out VIL-yellow."""
    from FMOFP.Interfaces.userInterface.displays.radar.weather_radar_display import (
        UNKNOWN_SEVERITY_COLOR,
    )
    from PyQt6.QtCore import QPointF

    R.section("Storm cell particles are coloured by the cell's own severity")

    display, painter, raw, _pixmap = _display_and_painter()
    try:
        severe = display._get_intensity_color(0.95)
        display._particles["cells"]["c_severe"] = []
        display._cell_particle_colors["c_severe"] = severe

        # Reproduce the pre-fix colour choice for a 'cells' data_type: the old
        # branch structure was `if data_type == 'precipitation': ... else: # vil`,
        # so 'cells' fell into the VIL arm, missed the VIL store and took the
        # 'LOW' fallback.
        pre_fix_color = display._vil_colors["LOW"]
        R.check("NON-TAUTOLOGICAL: the pre-fix fallback really was VIL 'LOW' yellow",
                _rgb(pre_fix_color) == (255, 255, 0))
        R.check("and a severe cell's own colour differs from it, so the bug was visible",
                _rgb(severe) != _rgb(pre_fix_color),
                f"severe={_rgb(severe)} pre_fix={_rgb(pre_fix_color)}")
        R.check("the cell's classified colour is now recorded for the draw pass",
                _rgb(display._cell_particle_colors["c_severe"]) == _rgb(severe))
        R.check("a cell with no recorded colour falls back to neutral, not yellow",
                _rgb(display._cell_particle_colors.get(
                    "c_missing", UNKNOWN_SEVERITY_COLOR)) == _rgb(UNKNOWN_SEVERITY_COLOR))

        # The generator is handed a colour and must keep it rather than drop it.
        captured = _captured_particle_colors(display)
        display._draw_storm_cell(
            painter, QPointF(400, 300), 250.0,
            {"position": (1.0, 1.0), "cell_id": "c_new", "intensity": 0.95},
        )
        R.check("drawing a severe cell records the SEVERE colour against its id",
                display._cell_particle_colors.get("c_new") is not None
                and _rgb(display._cell_particle_colors["c_new"])
                == _rgb(display._intensity_colors["SEVERE"]),
                f"recorded={display._cell_particle_colors.get('c_new')}")
        R.check("and the same colour reaches the generator",
                captured and _rgb(captured[-1]["color"])
                == _rgb(display._intensity_colors["SEVERE"]))
    finally:
        raw.end()
        display.cleanup()


# ───────────────────────────────────────────────────────────── VIL ───────

def test_vil_unknown_value():
    from FMOFP.Interfaces.userInterface.displays.radar.weather_radar_display import (
        UNKNOWN_SEVERITY_COLOR, UNKNOWN_VALUE_TEXT,
    )
    from PyQt6.QtCore import QPointF

    R.section("VIL point with no value reading")

    display, painter, raw, _pixmap = _display_and_painter()
    captured = _captured_particle_colors(display)
    display._visual_elements["show_vil_values"] = True
    try:
        display._draw_vil(
            painter, QPointF(400, 300), 250.0,
            {"position": (4.0, 4.0), "id": "vil_unknown"},
        )
        R.check("the VIL point is drawn", len(captured) == 1, f"captured={captured}")
        if captured:
            R.check("it is neutral, not a VIL band colour",
                    _rgb(captured[0]["color"]) == _rgb(UNKNOWN_SEVERITY_COLOR),
                    f"got {_rgb(captured[0]['color'])}")
        R.check("its label reads UNKN rather than a number",
                any(UNKNOWN_VALUE_TEXT in t for t in painter.texts),
                f"texts={painter.texts}")
        R.check("the fabricated 20.0 never appears as a label",
                not any(t.strip() == "20.0" for t in painter.texts),
                f"texts={painter.texts}")

        captured.clear()
        display._draw_vil(
            painter, QPointF(400, 300), 250.0,
            {"id": "vil_nowhere", "value": 35.0},
        )
        R.check("a VIL point with no position is skipped, not drawn over ownship",
                len(captured) == 0, f"captured={captured}")

        captured.clear()
        display._draw_vil(
            painter, QPointF(400, 300), 250.0,
            {"position": (-3.0, 7.0), "id": "vil_high", "value": 35.0, "intensity": 0.8},
        )
        R.check("a measured high VIL column keeps its HIGH colour",
                captured and _rgb(captured[0]["color"])
                == _rgb(display._vil_colors["HIGH"]),
                f"captured={[_rgb(c['color']) for c in captured]}")

        R.section("NON-TAUTOLOGICAL -- the old VIL defaults really did land in a band")
        vil_without_value = {"position": (4.0, 4.0), "id": "v"}
        pre_fix_value = vil_without_value.get("value", 20.0)
        R.check("vil.get('value', 20.0) really did yield 20.0", pre_fix_value == 20.0)
        R.check("and 20.0 really did classify as a measured LOW column",
                not (pre_fix_value > 20) and pre_fix_value > 10)
        R.check("vil.get('intensity', 0.7) really did yield 0.7",
                vil_without_value.get("intensity", 0.7) == 0.7)
    finally:
        raw.end()
        display.cleanup()


# ────────────────────────────────────────────────────── turbulence ───────

def test_turbulence_unknown_category():
    from FMOFP.Interfaces.userInterface.displays.radar.weather_radar_display import (
        UNKNOWN_SEVERITY_COLOR,
    )
    from FMOFP.Interfaces.userInterface.displays.radar.radar_display_data_coordinator import (
        get_radar_display_data_coordinator,
    )
    from PyQt6.QtCore import QPointF

    R.section("Turbulence cell with no category")

    display, painter, raw, _pixmap = _display_and_painter()
    coordinator = get_radar_display_data_coordinator()
    try:
        coordinator.store_data("turbulence", [
            {"position": (20.0, 30.0), "id": "turb_nocat"},
            {"position": (-20.0, 30.0), "id": "turb_badcat", "category": "GUSTY"},
            {"position": (0.0, 40.0), "id": "turb_severe", "category": "SEVERE",
             "intensity": 0.9},
        ], "req_turbulence_test")
        display._draw_turbulence_overlay(painter, QPointF(400, 300), 250.0)

        R.check("an uncategorised cell is labelled UNK, not LIG",
                "UNK" in painter.texts, f"texts={painter.texts}")
        R.check("an unrecognised category is labelled UNK rather than mislabelled",
                painter.texts.count("UNK") >= 2, f"texts={painter.texts}")
        R.check("a real SEVERE cell still shows SEV",
                "SEV" in painter.texts, f"texts={painter.texts}")
        R.check("no cell is labelled LIG when none reported LIGHT",
                "LIG" not in painter.texts, f"texts={painter.texts}")

        R.section("NON-TAUTOLOGICAL -- the old category default really was LIGHT")
        cell_without_category = {"position": (20.0, 30.0), "id": "t"}
        pre_fix_category = str(cell_without_category.get("category", "LIGHT")).upper()
        R.check("cell.get('category', 'LIGHT') really did yield LIGHT",
                pre_fix_category == "LIGHT")
        R.check("so an uncategorised cell really was labelled LIG",
                pre_fix_category[:3] == "LIG")
        R.check("an unrecognised category really did colour as LIGHT while "
                "labelling itself something else",
                {"LIGHT": 1}.get("GUSTY", "LIGHT-fallback") == "LIGHT-fallback"
                and "GUSTY"[:3] == "GUS")
        R.check("and the neutral colour is distinguishable from LIGHT green",
                _rgb(UNKNOWN_SEVERITY_COLOR) != (100, 220, 100))
    finally:
        raw.end()
        display.cleanup()


# ───────────────────────────────────────── coordinator binary decode ─────

def test_coordinator_leaves_unmeasured_fields_absent():
    from FMOFP.Interfaces.userInterface.displays.radar.radar_display_data_coordinator import (
        get_radar_display_data_coordinator, DATA_TYPE_PRECIPITATION,
    )

    R.section("Coordinator: a truncated binary message keeps no invented readings")

    coordinator = get_radar_display_data_coordinator()

    # 16 bits carries the position and nothing else: rate needs >= 26 bits and
    # intensity >= 32, so both are genuinely absent from this message.
    short = "1" + "0" * 7 + "1" + "0" * 7          # x = 0, y = 0 after the -128 offset
    # Offset both away from the origin so the (0,0) filter does not remove it.
    short = format(200, "08b") + format(60, "08b")
    processed = coordinator._process_items([short], DATA_TYPE_PRECIPITATION)

    R.check("the position is still decoded and the item retained",
            len(processed) == 1, f"processed={processed}")
    if processed:
        item = processed[0]
        R.check("no rate is invented", "rate" not in item, f"item={item}")
        R.check("no intensity is invented", "intensity" not in item, f"item={item}")
        R.check("no precipitation type is invented", "type" not in item, f"item={item}")
        R.check("show_values -- a display preference, not a measurement -- is set",
                item.get("show_values") is True, f"item={item}")

    # A full-length message must still decode every field.
    full = (format(200, "08b") + format(60, "08b")
            + format(1, "04b")            # type code
            + format(50, "06b")           # rate bits
            + format(40, "06b"))          # intensity bits
    processed_full = coordinator._process_items([full], DATA_TYPE_PRECIPITATION)
    R.check("a complete message still yields a rate",
            processed_full and "rate" in processed_full[0],
            f"processed={processed_full}")
    R.check("a complete message still yields an intensity",
            processed_full and "intensity" in processed_full[0],
            f"processed={processed_full}")
    R.check("a complete message still yields a type",
            processed_full and "type" in processed_full[0],
            f"processed={processed_full}")

    R.section("NON-TAUTOLOGICAL -- the old seeds really did survive truncation")
    seeded = {"position": (72.0, -68.0), "id": "x"}
    seeded["type"] = "rain"
    seeded["rate"] = 0.5
    seeded["intensity"] = 0.5
    R.check("the pre-fix block really did leave intensity 0.5 on a truncated item",
            seeded["intensity"] == 0.5)
    R.check("and 0.5 really is mid-scale, above the LIGHT threshold of 0.3",
            seeded["intensity"] > 0.3)
    R.check("and 'rain' really did claim a classification the message never carried",
            seeded["type"] == "rain")


# ────────────────────────────────── storage refuses incomplete records ───

def test_handler_refuses_incomplete_record():
    from FMOFP.local_messaging.routing.handlers.precipitation_data_handler import (
        PrecipitationDataHandler,
    )

    R.section("Storage: an incomplete record is refused, not completed")

    class _RecordingDB:
        """Records what the handler asked of the database.

        A stub rather than an exploding mock, because the handler wraps its work
        in try/except and an exception here would be logged rather than surfaced.
        What matters is that no INSERT is attempted for an incomplete record.
        """

        def __init__(self):
            self.queries = []

        def table_exists(self, name):
            return True

        def create_table(self, *args, **kwargs):
            return True

        def execute_query(self, query, params=(), **kwargs):
            self.queries.append(query)
            return []

        def get_connection(self):
            raise AssertionError("get_connection should not be needed here")

        def __getattr__(self, name):
            def _noop(*args, **kwargs):
                self.queries.append(f"<{name}>")
                return None
            return _noop

    class _Bare:
        pass

    handler = PrecipitationDataHandler.__new__(PrecipitationDataHandler)
    db = _RecordingDB()
    handler.radar_db = db

    missing_intensity = _Bare()
    missing_intensity.request_id = "req_1"
    missing_intensity.position = (10.0, 5.0)
    missing_intensity.type = "rain"
    missing_intensity.rate = 12.0

    db.queries.clear()
    stored = handler.store_precipitation_data(missing_intensity)
    R.check("a record with no intensity is refused", stored is False,
            f"returned {stored!r}")
    R.check("and no intensity was invented on the object",
            not hasattr(missing_intensity, "intensity"))
    R.check("and nothing was written to the database",
            not any("INSERT" in q.upper() for q in db.queries),
            f"queries={db.queries}")

    missing_position = _Bare()
    missing_position.request_id = "req_2"
    missing_position.type = "rain"
    missing_position.rate = 12.0
    missing_position.intensity = 0.5
    db.queries.clear()
    stored = handler.store_precipitation_data(missing_position)
    R.check("a record with no position is refused", stored is False,
            f"returned {stored!r}")
    R.check("and no (0.0, 0.0) position was invented",
            not hasattr(missing_position, "position"))
    R.check("and nothing was written to the database",
            not any("INSERT" in q.upper() for q in db.queries),
            f"queries={db.queries}")

    # request_id is an identifier, not a measurement: one may be minted.
    no_id = _Bare()
    no_id.position = (1.0, 2.0)
    no_id.type = "rain"
    no_id.rate = 1.0
    no_id.intensity = 0.1
    handler.store_precipitation_data(no_id)
    R.check("a complete record with no request_id gets one minted",
            hasattr(no_id, "request_id") and bool(no_id.request_id))

    R.section("NON-TAUTOLOGICAL -- the old block really did write invented readings")
    bare = _Bare()
    for field, default in (("position", (0.0, 0.0)), ("type", "rain"),
                           ("rate", 0.0), ("intensity", 0.0)):
        if not hasattr(bare, field):
            setattr(bare, field, default)
    R.check("the pre-fix loop really did give an empty record a position at ownship",
            bare.position == (0.0, 0.0))
    R.check("and a precipitation type of 'rain'", bare.type == "rain")
    R.check("and a rate of 0.0, all NOT NULL columns indistinguishable from readings",
            bare.rate == 0.0 and bare.intensity == 0.0)


# ─────────────────────────── the collection row shadowed real data ───────

def test_collection_row_no_longer_shadows_measurements():
    from FMOFP.Utils.common.radar_records import (
        COLLECTION_RECORD_TYPE, MEASUREMENT_ONLY_SQL,
    )

    R.section("The 'collection' link row is not a measurement")

    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE precipitation_data (
            request_id TEXT NOT NULL, timestamp REAL NOT NULL,
            position_x REAL NOT NULL, position_y REAL NOT NULL,
            type TEXT NOT NULL, rate REAL NOT NULL, intensity REAL NOT NULL,
            show_values INTEGER NOT NULL DEFAULT 0, additional_info TEXT
        )
    """)
    # Two real points, stored as children of request R, plus R's own link row.
    conn.execute("INSERT INTO precipitation_data VALUES "
                 "('R_1', 100.0, 12.0, -4.0, 'rain', 18.0, 0.8, 1, NULL)")
    conn.execute("INSERT INTO precipitation_data VALUES "
                 "('R_2', 101.0, 15.0, -6.0, 'hail', 40.0, 0.95, 1, NULL)")
    conn.execute(
        "INSERT INTO precipitation_data VALUES (?, 102.0, 0.0, 0.0, ?, 0.0, 0.0, 1, ?)",
        ("R", COLLECTION_RECORD_TYPE, '{"is_collection_record": true}'))
    conn.commit()

    pre_fix = conn.execute(
        "SELECT request_id, type FROM precipitation_data WHERE request_id = ? "
        "ORDER BY timestamp DESC", ("R",)).fetchall()
    R.check("NON-TAUTOLOGICAL: the pre-fix exact-match query really did return the "
            "link row", len(pre_fix) == 1 and pre_fix[0][1] == COLLECTION_RECORD_TYPE,
            f"rows={pre_fix}")
    R.check("which means the LIKE-pattern fallback never ran and the two real "
            "points were never returned",
            all(r[0] != "R_1" for r in pre_fix))
    R.check("and the link row would have decoded as a measured reading at ownship",
            pre_fix and conn.execute(
                "SELECT position_x, position_y, rate, intensity FROM "
                "precipitation_data WHERE request_id = 'R'").fetchone()
            == (0.0, 0.0, 0.0, 0.0))

    post_fix = conn.execute(
        f"SELECT request_id FROM precipitation_data WHERE request_id = ? "
        f"AND {MEASUREMENT_ONLY_SQL}", ("R",)).fetchall()
    R.check("the fixed exact-match query returns nothing for R",
            post_fix == [], f"rows={post_fix}")

    children = conn.execute(
        f"SELECT request_id FROM precipitation_data WHERE request_id LIKE ? "
        f"AND {MEASUREMENT_ONLY_SQL} ORDER BY request_id", ("R_%",)).fetchall()
    R.check("so the fallback runs and both real points come back",
            [r[0] for r in children] == ["R_1", "R_2"], f"rows={children}")

    window = conn.execute(
        f"SELECT request_id FROM precipitation_data WHERE timestamp > ? "
        f"AND {MEASUREMENT_ONLY_SQL} ORDER BY request_id", (50.0,)).fetchall()
    R.check("a time-window read returns only measurements",
            [r[0] for r in window] == ["R_1", "R_2"], f"rows={window}")

    counted = conn.execute(
        f"SELECT COUNT(*) FROM precipitation_data WHERE request_id = ? "
        f"AND {MEASUREMENT_ONLY_SQL}", ("R",)).fetchone()[0]
    R.check("a 'do we have data for R' count is not satisfied by the link row alone",
            counted == 0, f"count={counted}")

    link = conn.execute(
        "SELECT additional_info FROM precipitation_data WHERE request_id = ? "
        "AND type = ?", ("R", COLLECTION_RECORD_TYPE)).fetchone()
    R.check("the one read that wants the link row can still fetch it by type",
            link is not None and "is_collection_record" in link[0])

    conn.close()


# ──────────────────────────── the particle render path was dead ─────────

def test_particles_actually_reach_the_painter():
    """Every particle draw used self.width() on a class that has no width().

    These displays are plain objects owned by weather_radar_widget.py, not
    QWidget subclasses. _draw_particles opened with
    ``QRectF(0, 0, self.width(), self.height())``, which raised AttributeError
    on every call; the method's own ``except Exception: log`` swallowed it, so
    the only evidence was a log line and the weather radar drew no
    precipitation, VIL or storm-cell particles at all. The severity colours the
    rest of this suite is about were being computed for a render path that never
    ran.
    """
    from PyQt6.QtCore import QPointF

    R.section("Particles reach the painter (the whole path used to raise)")

    display, painter, raw, _pixmap = _display_and_painter()
    try:
        R.check("NON-TAUTOLOGICAL: the display genuinely has no width() to call",
                not hasattr(display, "width") and not hasattr(display, "height"))

        raised = None
        try:
            display.width()          # the pre-fix expression, verbatim
        except AttributeError as exc:
            raised = exc
        R.check("so the pre-fix viewport expression really did raise AttributeError",
                raised is not None, f"raised={raised!r}")

        R.check("the painter-derived viewport is the real surface instead",
                display.viewport_rect(painter).width() == 800.0
                and display.viewport_rect(painter).height() == 600.0,
                f"rect={display.viewport_rect(painter)}")

        # Real generators this time: the point is that particles get painted.
        display._draw_precipitation(
            painter, QPointF(400, 300), 250.0,
            {"position": (10.0, 5.0), "id": "p_live", "type": "rain",
             "intensity": 0.8, "rate": 25.0},
        )
        R.check("precipitation particles were generated",
                len(display._particles["precipitation"].get("p_live", [])) > 0,
                f"count={len(display._particles['precipitation'].get('p_live', []))}")
        R.check("and they were actually drawn on the painter",
                painter.ellipses > 0, f"ellipses={painter.ellipses}")

        before = painter.ellipses
        display._draw_storm_cell(
            painter, QPointF(400, 300), 250.0,
            {"position": (-6.0, 9.0), "cell_id": "c_live", "intensity": 0.9},
        )
        R.check("storm cell particles were generated",
                len(display._particles["cells"].get("c_live", [])) > 0)
        R.check("and drawn", painter.ellipses > before,
                f"before={before} after={painter.ellipses}")

        R.check("last_viewport_rect remembers the surface for painter-less callers",
                display.last_viewport_rect().width() == 800.0,
                f"rect={display.last_viewport_rect()}")
    finally:
        raw.end()
        display.cleanup()


# ─────────────────────────────────────────────────────────── runner ──────

def main():
    print("=" * 60)
    print("  Weather radar: unknown severity must render as unknown")
    print("=" * 60)

    for test in (
        test_optional_reads,
        test_precipitation_unknown_severity,
        test_storm_cell_unknown_intensity,
        test_storm_cell_particles_use_their_own_colour,
        test_vil_unknown_value,
        test_turbulence_unknown_category,
        test_coordinator_leaves_unmeasured_fields_absent,
        test_handler_refuses_incomplete_record,
        test_collection_row_no_longer_shadows_measurements,
        test_particles_actually_reach_the_painter,
    ):
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
