"""
Engine Indicating and Crew Alerting System (EICAS)

Displays:
  - Engine parameters  (thrust, EGT, N1/N2 RPM, oil pressure/temp, vibration)
  - Fuel state         (quantity, flow, balance)
  - Hydraulic systems  (pressure — three independent circuits)
  - Electrical systems (bus voltage, generator status)
  - Crew alert list    (caution / warning / advisory messages)

Data source: FMS via get_flight_data() and fmsControl.get_tactical_status().
The EICAS polls at 10 Hz; individual caution/warning lines are colour-coded:
  - RED    = WARNING  (immediate crew action required)
  - AMBER  = CAUTION  (timely crew action required)
  - CYAN   = ADVISORY (awareness only)
"""

import math
import threading
import time

from .data_validity import FieldValidity
import traceback
from typing import Dict, List

from PyQt6.QtCore import Qt, QPointF, QRectF, QTimer
from PyQt6.QtGui import QColor, QFont, QPainter, QPen

from .base_display import BaseDisplay, DisplayType
from FMOFP.Utils.logger.sys_logger import get_logger

logger = get_logger()

# ─────────────────────────────────────────────────────── colour palette ──
_GREEN  = QColor(0,   255, 100)
_AMBER  = QColor(255, 200,   0)
_RED    = QColor(255,  60,  60)
_CYAN   = QColor(0,   220, 255)
_WHITE  = QColor(240, 240, 240)
_DIM    = QColor(100, 100, 100)

# Shown in place of a number for a parameter that has no current reading.
# Dashes rather than a value, because every alternative is a measurement the
# aircraft did not make: leaving the seed in place reads as nominal, and
# substituting zero reads as an emergency -- FUEL TOTAL 0 kg renders red and
# would send a crew looking for a fuel leak that does not exist.
_UNKNOWN_TEXT = "----" 
_BG     = QColor(10,   12,  16)
_PANEL  = QColor(22,   26,  32)

# Alert severity levels
_WARN   = "WARNING"
_CAUT   = "CAUTION"
_ADV    = "ADVISORY"


class EICASDisplay(BaseDisplay):
    """
    Engine Indicating and Crew Alerting System display widget.

    Layout (800 × 600):
    ┌──────────────────────────────────────────┐
    │  Title bar                               │
    ├──────────────┬───────────────────────────┤
    │  Engine      │  Fuel / Hydraulic /       │
    │  gauges (L)  │  Electrical summary (R)   │
    ├──────────────┴───────────────────────────┤
    │  Alert / crew message window             │
    └──────────────────────────────────────────┘
    """

    def __init__(self, parent=None):
        super().__init__(DisplayType.EICAS, parent=parent)

        # ── simulated / FMS-derived engine parameters ──────────────────────
        # Which of these fields has actually had real data published to it.
        # Everything starts UNKNOWN; the seeded numbers below exist only so the
        # panel can lay out, and are not shown unless marked valid.
        self._validity = FieldValidity()

        self._engine = {
            "thrust_pct": 70.0,       # 0-100 %
            "n1_pct":     78.5,       # fan speed  (%)
            "n2_pct":     84.2,       # core speed (%)
            "egt_c":      620.0,      # exhaust gas temp (°C)
            "ff_kgh":     2400.0,     # fuel flow (kg/h)
            "oil_psi":    62.0,       # oil pressure (psi)
            "oil_temp_c": 95.0,       # oil temperature (°C)
            "vib":        0.3,        # vibration (engine units)
        }

        # ── fuel state ─────────────────────────────────────────────────────
        self._fuel = {
            # Was 6800.0 -- a hardcoded starting quantity this display then
            # integrated down, making it the aircraft's fuel authority. Now only
            # a layout placeholder; validity decides whether it is shown.
            "total_kg":   0.0,
            "flow_kgh":   2400.0,
            # Never written by anything: a constant 0.0, which also made the
            # "FUEL IMBALANCE" alarm below (abs(balance) > 200) unreachable.
            # Supply it through set_engine_readings() when a source exists.
            "balance_kg": 0.0,        # L-R imbalance
        }

        # ── systems health ──────────────────────────────────────────────────
        # Layout placeholders, not readings. Nothing in this project publishes
        # hydraulic system C, any electrical value, or the generator states:
        # _electrical was written once here and thereafter only read, so
        # MAIN BUS 115.0 V and GEN 1/2 NORM were constants on the panel and the
        # "ELEC MAIN BUS LO" alarm below could never fire -- the same dead-alarm
        # shape as the oil-pressure sine waves. Systems A and B are modelled
        # from g-load in _poll_data and are valid only while a real g_force is
        # published. Supply anything real through set_system_readings().
        self._hydraulic = {
            "sys_a_psi": 3000,
            "sys_b_psi": 3000,
            "sys_c_psi": 2950,
        }
        self._electrical = {
            "main_bus_v":  115.0,
            "ess_bus_v":   115.0,
            "gen1_ok":     True,
            "gen2_ok":     True,
        }

        # ── FCS / GCAS / BITS / ECS state ─────────────────────────────────
        self._fcs_alerts: List[Dict]   = []
        self._bits_results: List[str]  = []
        self._ecs_state: Dict          = {
            "cabin_alt_ft": 8000, "cabin_temp_c": 22, "oxy_psi": 1800,
        }

        # ── defensive systems state ────────────────────────────────────────
        self._defensive: Dict = {
            "chaff_remaining":  60,
            "flares_remaining": 30,
            "ecm_mode":         "STANDBY",
            "jamming_active":   False,
            "threat_count":     0,
            "rwr_contacts":     [],
        }

        # ── sensor management state ────────────────────────────────────────
        self._sensor_health: str = "INITIALISING"
        self._fused_track_count: int = 0
        self._fused_hostile_count: int = 0

        # ── weather processor severity ─────────────────────────────────────
        self._wx_windshear:  str  = "NONE"   # NONE / LOW / MODERATE / SEVERE
        self._wx_turbulence: str  = "NONE"   # NONE / LIGHT / MODERATE / SEVERE / EXTREME
        self._wx_microburst: bool = False

        # ── active alert messages ──────────────────────────────────────────
        self._alerts: List[Dict] = []   # [{'text', 'severity', 'ts'}]

        # ── FMS handles ───────────────────────────────────────────────────
        self._fms = None
        self._fms_control = None
        self._lock = threading.Lock()

        # ── poll timer (10 Hz) ────────────────────────────────────────────
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(100)
        self._poll_timer.timeout.connect(self._poll_data)
        self._poll_timer.start()

        logger.info("[EICAS] Display initialised")

    # ───────────────────────────────────────────────── data layer ──────────

    def set_engine_readings(self, **readings):
        """Supply real ECU readings, e.g. oil_psi=48.0, vib=0.9.

        Oil pressure, oil temperature and vibration have no feed in this
        project. They used to be generated as sine waves whose ranges could
        never cross their own alarm thresholds, so ENG OIL PRESSURE LO, ENG OIL
        TEMP HIGH and ENG VIBRATION HIGH were dead code while the panel read
        nominal. Anything supplied here is marked valid and IS alarm-checked.
        """
        with self._lock:
            for key, value in readings.items():
                if value is None:
                    continue
                if key in self._engine:
                    self._engine[key] = value
                elif key in self._fuel:
                    self._fuel[key] = value
                else:
                    continue
                self._validity.mark(key)

    def set_system_readings(self, **readings):
        """Supply real hydraulic, electrical or ECS values.

        Mirrors set_engine_readings for the system panels. Anything supplied
        here is marked valid and IS alarm-checked; anything never supplied
        reads as unknown rather than as its placeholder.
        """
        with self._lock:
            for key, value in readings.items():
                if value is None:
                    continue
                if key in self._hydraulic:
                    self._hydraulic[key] = value
                elif key in self._electrical:
                    self._electrical[key] = value
                elif key in self._ecs_state:
                    self._ecs_state[key] = value
                else:
                    continue
                self._validity.mark(key)

    def has_valid(self, field):
        """True when `field` has had real data recently."""
        return self._validity.is_valid(field)

    def _lazy_fms(self):
        """Lazy-import FMS handles (avoids circular imports at module load)."""
        if self._fms is None:
            try:
                from FMOFP.Systems.flightManagementSys.flightManagementSystem import (
                    get_flightManagementSystem,
                )
                from FMOFP.Systems.flightManagementSys.fmsControl import (
                    get_fms_control,
                )
                self._fms = get_flightManagementSystem()
                self._fms_control = get_fms_control()
            except Exception as exc:
                logger.warning(f"[EICAS] FMS not available yet: {exc}")

    def _poll_data(self):
        """Pull live data from FMS and synthesise engine/systems state."""
        try:
            self._lazy_fms()
            if not self._fms:
                return

            fd = self._fms.get_flight_data()
            with self._lock:
                # ── map FMS fields to engine display ──────────────────────
                tactical = fd.get("tactical", {})
                velocity = fd.get("velocity", {})
                nav      = fd.get("navigation", {})

                # No fabricated fallbacks. These used to default to 300 kt /
                # 30,000 ft / 70% thrust, so with the FMS silent the display
                # showed a complete engine picture derived from three constants.
                airspeed = velocity.get("airspeed")
                altitude = nav.get("altitude")
                self._validity.mark_from(velocity, {'airspeed': 'airspeed'})
                self._validity.mark_from(nav, {'altitude': 'altitude'})

                # Thrust comes from fmsControl or not at all.
                thrust = None
                if self._fms_control:
                    ts = self._fms_control.get_tactical_status() or {}
                    profile = ts.get("profile_limits", {})
                    if "engine_power" in profile:
                        thrust = profile["engine_power"] * 100

                if thrust is not None:
                    # These four are a documented MODEL of the engine, derived
                    # from commanded thrust -- not measurements. They are valid
                    # only while a real thrust value is being published.
                    self._engine["thrust_pct"] = thrust
                    self._engine["n1_pct"]     = 0.8  * thrust + 18
                    self._engine["n2_pct"]     = 0.75 * thrust + 22
                    self._engine["egt_c"]      = 350  + thrust * 4.5
                    self._engine["ff_kgh"]     = thrust * 42
                    self._validity.mark('thrust_pct', 'n1_pct', 'n2_pct',
                                        'egt_c', 'ff_kgh')

                # Oil pressure, oil temperature and vibration were SINE WAVES
                # presented as engine instruments, and their alarm thresholds
                # were mathematically unreachable as a result:
                #
                #   oil_psi    60 + 4*sin()        -> [56, 64]   vs <50 caution
                #   oil_temp_c 92 + 8*sin()        -> [84, 100]  vs >130 warning
                #   vib        0.2 + 0.15*|sin()|  -> [0.20, 0.35] vs >0.8 caution
                #
                # So three alarm families could never fire, while the panel read
                # reassuringly nominal. There is no ECU feed for these, so they
                # stay UNKNOWN until set_engine_readings() supplies real values.

                # Fuel is NOT owned by this display any more. It used to start
                # at a hardcoded 6800 kg and integrate its own burn here, which
                # made EICAS the sole authority on fuel quantity -- so closing
                # and reopening the display reset the aircraft's fuel. Quantity
                # now comes from a real source or reads UNKNOWN.
                if thrust is not None:
                    self._fuel["flow_kgh"] = self._engine["ff_kgh"]
                    self._validity.mark('flow_kgh')
                # Hydraulic: a MODEL of pressure droop under G-load, not a
                # measurement, and only meaningful while a real g_force is being
                # published. The default of 1.0 used to stand in for a missing
                # reading, which pinned both systems at exactly 3000 psi -- a
                # healthy-looking number derived from nothing.
                g = tactical.get("g_force")
                if g is not None:
                    self._hydraulic["sys_a_psi"] = 3000 - max(0, (g - 5) * 20)
                    self._hydraulic["sys_b_psi"] = 3000 - max(0, (g - 6) * 15)
                    self._validity.mark('sys_a_psi', 'sys_b_psi')

                # Build alert list
                self._alerts = self._compute_alerts(thrust)

                # GCAS alerts → master alert list
                try:
                    from FMOFP.Systems.flightControlSys.groundCollisionAvoidanceSys.groundCollisionAvoidanceSys import get_gcas
                    self._fcs_alerts = get_gcas().get_alerts()
                    for a in self._fcs_alerts:
                        sev = _WARN if a['severity'] == 1 else _CAUT
                        self._alerts.append({'text': f"FCS  {a['message']}", 'severity': sev, 'ts': time.time()})
                except Exception:
                    logger.debug("EICAS: GCAS not yet running", exc_info=True)

                # Performance exceedances → alert list
                try:
                    from FMOFP.Systems.flightControlSys.performaneMonitoring.performaneMonitoring import get_performance_monitor
                    for exc in get_performance_monitor().get_exceedances():
                        self._alerts.append({'text': f"PERF {exc['parameter'].upper()[:8]} EXCEED", 'severity': _WARN, 'ts': time.time()})
                except Exception:
                    logger.debug("EICAS: PerformanceMonitor not yet running", exc_info=True)

                # ECU live data overrides FMS-derived engine values
                try:
                    from FMOFP.Systems.engineManagement.ecu.engineControlUnit import get_engine_control_unit
                    ecu = get_engine_control_unit().get_data()
                    if ecu:
                        self._engine['n1_pct']    = ecu.get('n1_pct',    self._engine['n1_pct'])
                        self._engine['n2_pct']    = ecu.get('n2_pct',    self._engine['n2_pct'])
                        self._engine['egt_c']     = ecu.get('egt_c',     self._engine['egt_c'])
                        self._engine['ff_kgh']    = ecu.get('ff_kgh',    self._engine['ff_kgh'])
                        self._engine['oil_psi']   = ecu.get('oil_psi',   self._engine['oil_psi'])
                        self._engine['oil_temp_c']= ecu.get('oil_temp_c',self._engine['oil_temp_c'])
                        self._engine['vib']       = ecu.get('vibration', self._engine['vib'])
                except Exception:
                    logger.debug("EICAS: ECU not yet running", exc_info=True)

                # BITS — lazy-load on first poll
                try:
                    from FMOFP.Systems.builtInTestSystems.bitControl import BuiltInTestController
                    if not self._bits_results:
                        bits = BuiltInTestController()
                        self._bits_results = [f"{t['id']}: PASS" for t in bits.self_tests]
                except Exception:
                    logger.debug("EICAS: BITS not yet running", exc_info=True)

                # Defensive Systems — RWR, countermeasures, ECM
                try:
                    from FMOFP.Systems.defensiveSys.defensiveService import get_defensive_service
                    self._defensive = get_defensive_service().get_data()
                except Exception:
                    logger.debug("EICAS: DefensiveService not yet running", exc_info=True)

                # Sensor Management — health and fused track count
                try:
                    from FMOFP.Systems.sensorManagement.sensorService import get_sensor_service
                    sd = get_sensor_service().get_data()
                    self._sensor_health      = sd.get("health", "UNKNOWN")
                    self._fused_track_count  = sd.get("fused_track_count", 0)
                except Exception:
                    logger.debug("EICAS: SensorService not yet running", exc_info=True)

                # Radar Data Fusion — hostile track count for EICAS alerts
                try:
                    from FMOFP.Systems.radarManagement.radar_data_fusion import get_radar_data_fusion
                    # RadarDataFusion has no get_hostile_tracks() -- the real API is
                    # get_threat_tracks(), which already returns only tracks with
                    # threat == "HOSTILE" (see its docstring: "Return only tracks
                    # assessed as HOSTILE"). The old call raised AttributeError on
                    # every single poll (confirmed live: 110 times in 6 seconds of
                    # boot), silently swallowed by the except below, so this EICAS
                    # counter has never actually worked (production readiness deep
                    # dive, found via live system boot).
                    self._fused_hostile_count = len(get_radar_data_fusion().get_threat_tracks())
                except Exception:
                    logger.debug("EICAS: RadarDataFusion not yet running", exc_info=True)

                # Weather processors — wind shear and turbulence severity
                try:
                    from FMOFP.Systems.radarManagement.radarControl import get_radar_management_system
                    from FMOFP.Systems.radarManagement.weather.weather_radar import weather_radar
                    rms = get_radar_management_system()
                    for radar in rms.radars.values():
                        if isinstance(radar, weather_radar):
                            ws = radar.windshear_proc
                            tb = radar.turbulence_proc
                            last_ws = ws.get_last_result()
                            self._wx_windshear = (
                                max(last_ws, key=lambda e: e.severity_level()).severity
                                if last_ws else "NONE"
                            )
                            self._wx_turbulence  = tb.max_category()
                            self._wx_microburst  = ws.has_microburst()
                            break
                except Exception:
                    logger.debug("EICAS: weather processors not yet running", exc_info=True)

                # Append new-system alerts to master list
                self._alerts.extend(self._compute_defensive_alerts())
                self._alerts.extend(self._compute_sensor_alerts())
                self._alerts.extend(self._compute_weather_alerts())

            self._safe_update()

        except Exception as exc:
            logger.error(f"[EICAS] Poll error: {exc}")

    def _compute_alerts(self, thrust: float) -> List[Dict]:
        """Generate the active alert list from current system state."""
        now   = time.time()
        msgs: List[Dict] = []

        def add(text, sev):
            msgs.append({"text": text, "severity": sev, "ts": now})

        # Engine warnings
        # Each check runs only on a field that has real data. An UNKNOWN
        # reading must not be silently treated as in-limits: it is reported as
        # unknown instead, which is the honest state and is itself actionable.
        v = self._validity

        if v.is_valid('egt_c'):
            if self._engine["egt_c"] > 800:
                add("ENG  EGT HIGH", _WARN)
            elif self._engine["egt_c"] > 750:
                add("ENG  EGT CAUTION", _CAUT)
        else:
            add("ENG  EGT UNKNOWN", _CAUT)

        if v.is_valid('oil_psi'):
            if self._engine["oil_psi"] < 40:
                add("ENG  OIL PRESSURE LO", _WARN)
            elif self._engine["oil_psi"] < 50:
                add("ENG  OIL PRESS LOW", _CAUT)
        else:
            add("ENG  OIL PRESS UNKNOWN", _CAUT)

        if v.is_valid('oil_temp_c'):
            if self._engine["oil_temp_c"] > 130:
                add("ENG  OIL TEMP HIGH", _WARN)
        else:
            add("ENG  OIL TEMP UNKNOWN", _CAUT)

        if v.is_valid('vib'):
            if self._engine["vib"] > 0.8:
                add("ENG  VIBRATION HIGH", _CAUT)
        else:
            add("ENG  VIB UNKNOWN", _CAUT)

        # Fuel warnings
        if not v.is_valid('total_kg'):
            add("FUEL QTY UNKNOWN", _CAUT)
        elif self._fuel["total_kg"] < 500:
            add("FUEL  QUANTITY LOW", _WARN)
        elif self._fuel["total_kg"] < 1000:
            add("FUEL  QUANTITY CAUTION", _CAUT)

        if not v.is_valid('balance_kg'):
            add("FUEL  BALANCE UNKNOWN", _CAUT)
        elif abs(self._fuel["balance_kg"]) > 200:
            add("FUEL  IMBALANCE", _CAUT)

        # Hydraulic warnings. An unmonitored system is reported as unmonitored;
        # running the threshold against a placeholder reads as "in limits" and
        # is indistinguishable from a healthy measured system.
        for name, field in [("HYD A", "sys_a_psi"),
                            ("HYD B", "sys_b_psi"),
                            ("HYD C", "sys_c_psi")]:
            if not v.is_valid(field):
                add(f"{name}  PRESSURE UNKNOWN", _CAUT)
                continue
            psi = self._hydraulic[field]
            if psi < 2000:
                add(f"{name}  PRESSURE LOW", _WARN)
            elif psi < 2500:
                add(f"{name}  PRESS REDUCED", _CAUT)

        # Electrical. Nothing publishes these, so in the current system every
        # one of them reports UNKNOWN -- which is the point: the panel used to
        # show a nominal bus voltage and two healthy generators that no part of
        # the aircraft had ever asserted.
        if not v.is_valid('gen1_ok'):
            add("ELEC  GEN 1 UNKNOWN", _CAUT)
        elif not self._electrical["gen1_ok"]:
            add("ELEC  GEN 1 FAULT", _WARN)

        if not v.is_valid('gen2_ok'):
            add("ELEC  GEN 2 UNKNOWN", _CAUT)
        elif not self._electrical["gen2_ok"]:
            add("ELEC  GEN 2 FAULT", _WARN)

        if not v.is_valid('main_bus_v'):
            add("ELEC  BUS VOLTS UNKNOWN", _CAUT)
        elif self._electrical["main_bus_v"] < 100:
            add("ELEC  MAIN BUS LO", _CAUT)

        # Advisory: high thrust without afterburner selected
        if thrust > 95:
            add("ENG  MAX CONTINUOUS THRUST", _ADV)

        return msgs

    def _compute_defensive_alerts(self) -> List[Dict]:
        """Generate alerts from defensive systems state."""
        now  = time.time()
        msgs: List[Dict] = []

        def add(text, sev):
            msgs.append({"text": text, "severity": sev, "ts": now})

        d = self._defensive

        # RWR threat contacts
        hostile = [c for c in d.get("rwr_contacts", []) if c.get("hostile")]
        hi_pri  = [c for c in hostile if c.get("priority", 99) == 1]
        if hi_pri:
            add(f"RWR  {len(hi_pri)} HIGH-PRI THREAT(S)", _WARN)
        elif hostile:
            add(f"RWR  {len(hostile)} THREAT CONTACT(S)", _CAUT)

        # Countermeasure inventory
        chaff  = d.get("chaff_remaining", 60)
        flares = d.get("flares_remaining", 30)
        if chaff == 0:
            add("CMDS  CHAFF DEPLETED", _WARN)
        elif chaff <= 10:
            add(f"CMDS  CHAFF LOW ({chaff})", _CAUT)

        if flares == 0:
            add("CMDS  FLARES DEPLETED", _WARN)
        elif flares <= 5:
            add(f"CMDS  FLARES LOW ({flares})", _CAUT)

        # ECM state advisory
        if d.get("ecm_mode") == "ACTIVE":
            add("EW   ECM ACTIVE", _ADV)

        return msgs

    def _compute_sensor_alerts(self) -> List[Dict]:
        """Generate alerts from sensor management health and radar data fusion."""
        now  = time.time()
        msgs: List[Dict] = []

        def add(text, sev):
            msgs.append({"text": text, "severity": sev, "ts": now})

        health = self._sensor_health
        if health == "FAULT":
            add("SENSOR  SYSTEM FAULT", _WARN)
        elif health == "DEGRADED":
            add("SENSOR  DEGRADED MODE", _CAUT)

        # Fused hostile track alerts from RadarDataFusion
        hostile = self._fused_hostile_count
        if hostile >= 3:
            add(f"FUSION  {hostile} HOSTILE TRACKS", _WARN)
        elif hostile >= 1:
            add(f"FUSION  {hostile} HOSTILE TRACK(S)", _CAUT)

        return msgs

    def _compute_weather_alerts(self) -> List[Dict]:
        """Generate alerts from weather radar processors."""
        now  = time.time()
        msgs: List[Dict] = []

        def add(text, sev):
            msgs.append({"text": text, "severity": sev, "ts": now})

        # Wind shear
        if self._wx_microburst:
            add("WX   MICROBURST ALERT", _WARN)
        elif self._wx_windshear == "SEVERE":
            add("WX   SEVERE WINDSHEAR", _WARN)
        elif self._wx_windshear == "MODERATE":
            add("WX   MODERATE WINDSHEAR", _CAUT)
        elif self._wx_windshear == "LOW":
            add("WX   WINDSHEAR AHEAD", _ADV)

        # Turbulence
        if self._wx_turbulence == "EXTREME":
            add("WX   EXTREME TURBULENCE", _WARN)
        elif self._wx_turbulence == "SEVERE":
            add("WX   SEVERE TURBULENCE", _WARN)
        elif self._wx_turbulence == "MODERATE":
            add("WX   MODERATE TURBULENCE", _CAUT)
        elif self._wx_turbulence == "LIGHT":
            add("WX   LIGHT TURBULENCE", _ADV)

        return msgs

    # ───────────────────────────────────────────────── paint ───────────────

    def paint_display(self, painter: QPainter):
        """Paint the full EICAS display."""
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            painter.save()

            w, h = float(self.width()), float(self.height())
            title_h  = h * 0.07
            engine_w = w * 0.45
            right_w  = w - engine_w
            # Right side: systems text panel (60%) | defensive visual panel (40%)
            sys_w    = right_w * 0.60
            def_w    = right_w - sys_w
            body_h   = h * 0.55
            alert_h  = h - title_h - body_h

            # Regions
            title_r  = QRectF(0,                0,       w,       title_h)
            engine_r = QRectF(0,                title_h, engine_w, body_h)
            sys_r    = QRectF(engine_w,         title_h, sys_w,    body_h)
            def_r    = QRectF(engine_w + sys_w, title_h, def_w,    body_h)
            alert_r  = QRectF(0,     title_h + body_h,  w,        alert_h)

            with self._lock:
                self._draw_title(painter, title_r)
                self._draw_engine_panel(painter, engine_r)
                self._draw_systems_panel(painter, sys_r)
                self._draw_defensive_panel(painter, def_r)
                self._draw_alert_panel(painter, alert_r)

            painter.restore()
        except Exception as exc:
            logger.error(f"[EICAS] Paint error: {exc}")
            logger.error(traceback.format_exc())
            raise

    # ── title bar ───────────────────────────────────────────────────────────

    def _draw_title(self, painter: QPainter, r: QRectF):
        painter.fillRect(r, QColor(20, 20, 30))
        painter.setPen(QPen(_WHITE))
        f = QFont("Monospace", 11, QFont.Weight.Bold)
        painter.setFont(f)
        painter.drawText(r, Qt.AlignmentFlag.AlignCenter, "EICAS — ENGINE / SYSTEMS")
        # bottom separator
        painter.setPen(QPen(_DIM, 1))
        painter.drawLine(int(r.left()), int(r.bottom()),
                         int(r.right()), int(r.bottom()))

    # ── engine panel ────────────────────────────────────────────────────────

    def _draw_engine_panel(self, painter: QPainter, r: QRectF):
        painter.fillRect(r, _PANEL)
        painter.setPen(QPen(_DIM, 1))
        painter.drawRect(r)

        f_label = QFont("Monospace", 8)
        f_value = QFont("Monospace", 10, QFont.Weight.Bold)

        # Each row names the validity field behind it. A parameter with no
        # current reading is drawn as dashes in amber, and its threshold colour
        # is not evaluated at all -- the numbers in self._engine are layout
        # seeds, and colouring them green was the display asserting a nominal
        # engine while nothing was feeding it.
        def reading(field, fmt, colour_fn=None):
            if not self._validity.is_valid(field):
                return (_UNKNOWN_TEXT, _AMBER)
            value = self._engine[field]
            return (fmt(value), colour_fn(value) if colour_fn else _GREEN)

        params = [
            ("THRUST",  *reading('thrust_pct', lambda v: f"{v:5.1f} %")),
            ("N1",      *reading('n1_pct',     lambda v: f"{v:5.1f} %")),
            ("N2",      *reading('n2_pct',     lambda v: f"{v:5.1f} %")),
            ("EGT",     *reading('egt_c',      lambda v: f"{v:5.0f} °C",
                                 lambda v: _RED if v > 800 else
                                           _AMBER if v > 750 else _GREEN)),
            ("FF",      *reading('ff_kgh',     lambda v: f"{v:5.0f} kg/h")),
            ("OIL PSI", *reading('oil_psi',    lambda v: f"{v:5.1f}",
                                 lambda v: _RED if v < 40 else
                                           _AMBER if v < 50 else _GREEN)),
            ("OIL °C",  *reading('oil_temp_c', lambda v: f"{v:5.1f}",
                                 lambda v: _RED if v > 130 else _GREEN)),
            ("VIB",     *reading('vib',        lambda v: f"{v:5.2f}",
                                 lambda v: _AMBER if v > 0.8 else _GREEN)),
        ]

        row_h = r.height() / (len(params) + 1)
        section_label_r = QRectF(r.left() + 8, r.top() + 4,
                                 r.width() - 16, row_h)
        painter.setFont(f_label)
        painter.setPen(QPen(_DIM))
        painter.drawText(section_label_r, Qt.AlignmentFlag.AlignVCenter,
                         "─── ENGINE 1 ───")

        for i, (label, value, colour) in enumerate(params):
            y   = r.top() + row_h * (i + 1)
            l_r = QRectF(r.left() + 8,  y, r.width() * 0.5, row_h)
            v_r = QRectF(r.left() + r.width() * 0.52, y,
                         r.width() * 0.46, row_h)
            painter.setFont(f_label)
            painter.setPen(QPen(_DIM))
            painter.drawText(l_r, Qt.AlignmentFlag.AlignVCenter, label)
            painter.setFont(f_value)
            painter.setPen(QPen(colour))
            painter.drawText(v_r, Qt.AlignmentFlag.AlignVCenter |
                             Qt.AlignmentFlag.AlignRight, value)

    # ── systems panel ───────────────────────────────────────────────────────

    def _draw_systems_panel(self, painter: QPainter, r: QRectF):
        painter.fillRect(r, _PANEL)
        painter.setPen(QPen(_DIM, 1))
        painter.drawRect(r)

        f_hd  = QFont("Monospace", 8)
        f_val = QFont("Monospace", 9, QFont.Weight.Bold)
        line_h = 18.0
        y = r.top() + 8

        def section(title):
            nonlocal y
            painter.setFont(f_hd)
            painter.setPen(QPen(_DIM))
            hr = QRectF(r.left() + 6, y, r.width() - 12, line_h)
            painter.drawText(hr, Qt.AlignmentFlag.AlignVCenter, title)
            y += line_h + 2

        def row(label, value, colour):
            nonlocal y
            l_r = QRectF(r.left() + 10, y, r.width() * 0.55, line_h)
            v_r = QRectF(r.left() + r.width() * 0.57, y,
                         r.width() * 0.40, line_h)
            painter.setFont(f_hd)
            painter.setPen(QPen(_DIM))
            painter.drawText(l_r, Qt.AlignmentFlag.AlignVCenter, label)
            painter.setFont(f_val)
            painter.setPen(QPen(colour))
            painter.drawText(v_r, Qt.AlignmentFlag.AlignVCenter |
                             Qt.AlignmentFlag.AlignRight, value)
            y += line_h + 1

        # ── Fuel ────────────────────────────────────────────────────────────
        section("─── FUEL ────────────")
        # Quantity is not owned by this display any more, and nothing currently
        # publishes it, so TOTAL reads as unknown rather than as the 0 kg the
        # layout placeholder holds -- 0 would be drawn red, i.e. as a fuel
        # emergency, which is the opposite of "no reading".
        if self._validity.is_valid('total_kg'):
            total = self._fuel["total_kg"]
            fuel_col = (_RED   if total < 500  else
                        _AMBER if total < 1000 else _GREEN)
            row("TOTAL", f"{total:6.0f} kg", fuel_col)
        else:
            row("TOTAL", _UNKNOWN_TEXT, _AMBER)

        if self._validity.is_valid('flow_kgh'):
            row("FLOW", f"{self._fuel['flow_kgh']:6.0f} kg/h", _GREEN)
        else:
            row("FLOW", _UNKNOWN_TEXT, _AMBER)

        if self._validity.is_valid('balance_kg'):
            bal = self._fuel["balance_kg"]
            row("BALANCE", f"{bal:+6.0f} kg", _AMBER if abs(bal) > 200 else _GREEN)
        else:
            row("BALANCE", _UNKNOWN_TEXT, _AMBER)

        y += 4
        # ── Hydraulics ──────────────────────────────────────────────────────
        section("─── HYDRAULIC ───────")
        for sys_name, field in [("SYS A", "sys_a_psi"),
                                ("SYS B", "sys_b_psi"),
                                ("SYS C", "sys_c_psi")]:
            if not self._validity.is_valid(field):
                row(sys_name, _UNKNOWN_TEXT, _AMBER)
                continue
            psi = self._hydraulic[field]
            col = (_RED   if psi < 2000 else
                   _AMBER if psi < 2500 else _GREEN)
            row(sys_name, f"{psi:5.0f} psi", col)

        y += 4
        # ── Electrical ──────────────────────────────────────────────────────
        section("─── ELECTRICAL ──────")
        if self._validity.is_valid('main_bus_v'):
            mb = self._electrical["main_bus_v"]
            row("MAIN BUS", f"{mb:5.1f} V", _AMBER if mb < 100 else _GREEN)
        else:
            row("MAIN BUS", _UNKNOWN_TEXT, _AMBER)

        if self._validity.is_valid('ess_bus_v'):
            row("ESS BUS", f"{self._electrical['ess_bus_v']:5.1f} V", _GREEN)
        else:
            row("ESS BUS", _UNKNOWN_TEXT, _AMBER)

        for label, field in (("GEN 1", "gen1_ok"), ("GEN 2", "gen2_ok")):
            if not self._validity.is_valid(field):
                row(label, _UNKNOWN_TEXT, _AMBER)
            else:
                ok = self._electrical[field]
                row(label, "NORM" if ok else "FAIL", _GREEN if ok else _RED)

        y += 4
        # ── FCS / GCAS ──────────────────────────────────────────────────────
        section("─── FCS / GCAS ──────")
        if self._fcs_alerts:
            for a in self._fcs_alerts[:2]:
                row(a.get("code", "FCS")[:8], a.get("message", ""), _RED)
        else:
            row("FCS",  "NOMINAL", _GREEN)
            row("GCAS", "ARMED",   _GREEN)

        y += 4
        # ── Environmental (ECS) ─────────────────────────────────────────────
        section("─── ECS ─────────────")
        if self._validity.is_valid('cabin_alt_ft'):
            alt = self._ecs_state['cabin_alt_ft']
            row("CAB ALT", f"{alt:5.0f} ft", _AMBER if alt > 10000 else _GREEN)
        else:
            row("CAB ALT", _UNKNOWN_TEXT, _AMBER)

        if self._validity.is_valid('cabin_temp_c'):
            row("CAB TEMP", f"{self._ecs_state['cabin_temp_c']:5.1f} °C", _GREEN)
        else:
            row("CAB TEMP", _UNKNOWN_TEXT, _AMBER)

        if self._validity.is_valid('oxy_psi'):
            oxy = self._ecs_state['oxy_psi']
            row("OXY PSI", f"{oxy:5.0f} psi", _RED if oxy < 500 else _GREEN)
        else:
            row("OXY PSI", _UNKNOWN_TEXT, _AMBER)

        y += 4
        # ── BITS ────────────────────────────────────────────────────────────
        if self._bits_results:
            section("─── BITS ────────────")
            for result in self._bits_results[:3]:
                col = _GREEN if "PASS" in result else _RED
                row(result[:12], result[12:] if len(result) > 12 else "", col)

        y += 4
        # ── Defensive Systems ───────────────────────────────────────────────
        section("─── DEFENSIVE ───────")
        d = self._defensive
        chaff  = d.get("chaff_remaining", 60)
        flares = d.get("flares_remaining", 30)
        chaff_col  = (_RED   if chaff  == 0  else
                      _AMBER if chaff  <= 10 else _GREEN)
        flare_col  = (_RED   if flares == 0  else
                      _AMBER if flares <= 5  else _GREEN)
        ecm_mode   = d.get("ecm_mode", "STANDBY")
        ecm_col    = _CYAN if ecm_mode == "ACTIVE" else _GREEN
        threats    = d.get("threat_count", 0)
        threat_col = (_RED   if threats >= 3 else
                      _AMBER if threats >= 1 else _GREEN)
        row("CHAFF",    f"{chaff:3d} REM",  chaff_col)
        row("FLARES",   f"{flares:3d} REM", flare_col)
        row("ECM",      ecm_mode,            ecm_col)
        row("RWR",      f"{threats:2d} CTX", threat_col)

        y += 4
        # ── Sensor Management ───────────────────────────────────────────────
        section("─── SENSORS ─────────")
        health_col = (_RED   if self._sensor_health == "FAULT"    else
                      _AMBER if self._sensor_health == "DEGRADED" else _GREEN)
        row("HEALTH",  self._sensor_health,          health_col)
        row("TRACKS",  f"{self._fused_track_count:3d} FUSED", _GREEN)

    # ── defensive panel ─────────────────────────────────────────────────────

    def _draw_defensive_panel(self, painter: QPainter, r: QRectF):
        """
        Defensive systems visual panel.

        Layout (top → bottom):
          ① Section header
          ② Mini RWR bearing ring — hostile contacts plotted at bearing on edge
          ③ Chaff inventory bar
          ④ Flare inventory bar
          ⑤ ECM mode indicator
        """
        painter.fillRect(r, _PANEL)
        painter.setPen(QPen(_DIM, 1))
        painter.drawRect(r)

        f_hd  = QFont("Monospace", 7)
        f_val = QFont("Monospace", 8, QFont.Weight.Bold)

        # ── section header ─────────────────────────────────────────────────
        painter.setFont(f_hd)
        painter.setPen(QPen(_DIM))
        hdr_r = QRectF(r.left() + 4, r.top() + 4, r.width() - 8, 16)
        painter.drawText(hdr_r, Qt.AlignmentFlag.AlignVCenter,
                         "─ DEFENSIVE ─")

        d        = self._defensive
        contacts = d.get("rwr_contacts", [])
        chaff    = d.get("chaff_remaining", 60)
        flares   = d.get("flares_remaining", 30)
        ecm_mode = d.get("ecm_mode", "STANDBY")

        # ── RWR mini bearing ring ──────────────────────────────────────────
        ring_top    = r.top() + 24
        ring_h      = r.height() * 0.48
        cx          = r.left() + r.width() / 2
        cy          = ring_top + ring_h / 2
        rad         = min(r.width() * 0.40, ring_h * 0.44)

        # Background disc
        painter.setPen(QPen(_DIM, 0.5))
        painter.setBrush(QColor(18, 22, 28))
        painter.drawEllipse(QPointF(cx, cy), rad, rad)

        # Cardinal tick marks
        painter.setPen(QPen(_DIM, 0.5))
        for deg in range(0, 360, 45):
            a     = math.radians(deg - 90)
            inner = rad * 0.85
            ox    = cx + inner * math.cos(a)
            oy    = cy + inner * math.sin(a)
            tx    = cx + rad  * math.cos(a)
            ty    = cy + rad  * math.sin(a)
            painter.drawLine(QPointF(ox, oy), QPointF(tx, ty))

        # "N" label at top
        painter.setFont(QFont("Monospace", 6))
        painter.setPen(QPen(_DIM))
        painter.drawText(
            QRectF(cx - 5, ring_top, 10, 10),
            Qt.AlignmentFlag.AlignCenter, "N"
        )

        # Own-ship centre cross
        cs = 4
        painter.setPen(QPen(_GREEN, 1))
        painter.drawLine(QPointF(cx - cs, cy), QPointF(cx + cs, cy))
        painter.drawLine(QPointF(cx, cy - cs), QPointF(cx, cy + cs))

        # RWR contacts — dot on ring edge at bearing; red=hostile, amber=unknown
        for contact in contacts:
            bearing = contact.get("bearing_deg", 0)
            hostile = contact.get("hostile", False)
            band    = contact.get("band", "?")
            ang     = math.radians(bearing - 90)
            px      = cx + rad * math.cos(ang)
            py      = cy + rad * math.sin(ang)
            col     = _RED if hostile else _AMBER
            painter.setPen(QPen(col, 1))
            painter.setBrush(col)
            painter.drawEllipse(QPointF(px, py), 3.5, 3.5)
            # Band label just outside the dot
            lx = cx + (rad + 7) * math.cos(ang) - 6
            ly = cy + (rad + 7) * math.sin(ang) - 4
            painter.setFont(QFont("Monospace", 5))
            painter.setPen(QPen(col))
            painter.drawText(QRectF(lx, ly, 14, 8),
                             Qt.AlignmentFlag.AlignCenter, band)

        # No-contacts label
        if not contacts:
            painter.setFont(f_hd)
            painter.setPen(QPen(_GREEN))
            painter.drawText(
                QRectF(cx - 20, cy - 6, 40, 12),
                Qt.AlignmentFlag.AlignCenter, "CLEAR"
            )

        # ── inventory bars ─────────────────────────────────────────────────
        bar_top   = ring_top + ring_h + 6
        bar_w     = r.width() - 16
        bar_h     = 10.0
        bar_x     = r.left() + 8

        def inv_bar(label, value, max_val, warn, crit, y_pos):
            frac     = max(0.0, min(1.0, value / max_val))
            col      = (_RED   if value <= crit else
                        _AMBER if value <= warn else _GREEN)
            # Label
            painter.setFont(f_hd)
            painter.setPen(QPen(_DIM))
            lbl_r = QRectF(bar_x, y_pos, 36, bar_h)
            painter.drawText(lbl_r, Qt.AlignmentFlag.AlignVCenter, label)
            # Background track
            track_x = bar_x + 38
            track_w = bar_w - 38 - 26
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(30, 34, 40))
            painter.drawRect(QRectF(track_x, y_pos + 1, track_w, bar_h - 2))
            # Fill
            painter.setBrush(col)
            painter.drawRect(QRectF(track_x, y_pos + 1,
                                    track_w * frac, bar_h - 2))
            # Count
            painter.setFont(f_val)
            painter.setPen(QPen(col))
            cnt_r = QRectF(track_x + track_w + 2, y_pos, 22, bar_h)
            painter.drawText(cnt_r,
                             Qt.AlignmentFlag.AlignVCenter |
                             Qt.AlignmentFlag.AlignRight,
                             str(value))

        inv_bar("CHAF", chaff,  60, 10, 0,    bar_top)
        inv_bar("FLRE", flares, 30,  5, 0,    bar_top + bar_h + 4)

        # ── ECM mode indicator ─────────────────────────────────────────────
        ecm_y   = bar_top + 2 * (bar_h + 4) + 6
        ecm_col = (_CYAN  if ecm_mode == "ACTIVE"  else
                   _AMBER if ecm_mode == "PASSIVE" else _GREEN)
        ecm_r   = QRectF(r.left() + 6, ecm_y, r.width() - 12, 14)

        painter.setPen(QPen(ecm_col, 1))
        painter.setBrush(QColor(0, 0, 0, 0))
        painter.drawRect(ecm_r)
        painter.setFont(f_val)
        painter.setPen(QPen(ecm_col))
        painter.drawText(ecm_r, Qt.AlignmentFlag.AlignCenter,
                         f"ECM  {ecm_mode}")

    # ── alert panel ─────────────────────────────────────────────────────────

    def _draw_alert_panel(self, painter: QPainter, r: QRectF):
        painter.fillRect(r, QColor(12, 14, 18))
        painter.setPen(QPen(_DIM, 1))
        painter.drawRect(r)

        f_hd  = QFont("Monospace", 8)
        f_msg = QFont("Monospace", 9, QFont.Weight.Bold)

        painter.setFont(f_hd)
        painter.setPen(QPen(_DIM))
        hdr_r = QRectF(r.left() + 8, r.top() + 2, r.width() - 16, 16)
        painter.drawText(hdr_r, Qt.AlignmentFlag.AlignVCenter,
                         "CREW ALERTING MESSAGES")

        line_h = max(14.0, (r.height() - 22) / max(1, len(self._alerts) + 1))
        y = r.top() + 20

        if not self._alerts:
            painter.setFont(f_msg)
            painter.setPen(QPen(_GREEN))
            nr = QRectF(r.left() + 8, y, r.width() - 16, line_h)
            painter.drawText(nr, Qt.AlignmentFlag.AlignVCenter,
                             "  NO ACTIVE ALERTS")
            return

        # Sort: warnings first, then cautions, then advisories
        _order = {_WARN: 0, _CAUT: 1, _ADV: 2}
        sorted_alerts = sorted(self._alerts,
                               key=lambda a: _order.get(a["severity"], 3))

        for alert in sorted_alerts:
            if y + line_h > r.bottom() - 4:
                break
            sev = alert["severity"]
            col = _RED if sev == _WARN else (_AMBER if sev == _CAUT else _CYAN)
            tag = f"[{sev[:4]:4s}]"

            msg_r = QRectF(r.left() + 8, y, r.width() - 16, line_h)
            painter.setFont(f_msg)
            painter.setPen(QPen(col))
            painter.drawText(msg_r, Qt.AlignmentFlag.AlignVCenter,
                             f"{tag}  {alert['text']}")
            y += line_h

    # ────────────────────────────────────────────── lifecycle ──────────────

    def stop(self):
        self._poll_timer.stop()
        super().stop()

    def cleanup(self):
        self._poll_timer.stop()
