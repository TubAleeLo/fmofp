"""Test suite — weather radar against a live booted system (PI-1 story C14).

This is the reference conversion for the ten CLI-harness-only suites. It
replaces radar_tests/weather_radar_test.py's approach, not its subject.

WHAT WAS WRONG WITH THE ORIGINAL
--------------------------------
That suite verifies by regex-matching captured log prose:

    (f"mode change.*{mode.name}|{mode.name}.*mode change", "Mode change processing")
    (f"display.*weather radar.*{mode.name}",               "Display mode update")

Assertions coupled to log wording break whenever a message is reworded, pass by
coincidence when unrelated text happens to match, and -- most importantly --
cannot tell you what the system actually did. Run against a live system it
reports 17 tests, 3 passing and 14 failing, every failure a missing log phrase.

What that suite could never have told you is what a state assertion finds
immediately: setting `weather_radar.set_mode(SURVEILLANCE)` directly DOES work,
and is then deliberately reverted, because `RadarManagementSystem` is the mode
authority and reasserts a commanded mode derived from mission phase on every
tick of its update loop:

    if self.mission_phase in (TAKEOFF, APPROACH):  -> SURVEILLANCE
    else:                                          -> MAPPING

That supervisory relationship is the weather radar's most important behaviour
and the original suite does not test it at all. This one does.

Standalone-safe: run from B20SS/ as
`python -m FMOFP.Tests.test_weather_radar_live`.
"""
import os
import sys

_B20SS = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _B20SS not in sys.path:
    sys.path.insert(0, _B20SS)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from FMOFP.Tests.live_system import (  # noqa: E402
    await_condition,
    run_against_live_system,
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


def mode_name(radar):
    m = getattr(radar, 'mode', None)
    return getattr(m, 'name', str(m))


async def body(sm):
    from FMOFP.Systems.radarManagement.radar_enums import weather_radarMode
    from FMOFP.Systems.radarManagement.radarControl import MissionPhase

    # ── the radar is actually wired into the running system ──────────────
    print("\nregistration")

    rm = sm.components.get('radar_management')
    check("radar management is a registered component", rm is not None)
    if rm is None:
        return 1

    radars = getattr(rm, 'radars', {})
    check("all five radars are registered", len(radars) >= 5,
          f"{sorted(radars)}")

    radar = radars.get('weather_radar')
    check("the weather radar is present", radar is not None, sorted(radars))
    if radar is None:
        return 1

    check("it reports healthy", radar.is_healthy())
    check("its mode is a weather_radarMode, not a generic RadarMode",
          isinstance(radar.mode, weather_radarMode), repr(radar.mode))

    # ── set_mode is a real, immediate state change ───────────────────────
    print("\nset_mode changes state synchronously")

    original_phase = rm.mission_phase
    before = radar.mode
    target = (weather_radarMode.TURBULENCE if before is not weather_radarMode.TURBULENCE
              else weather_radarMode.WINDSHEAR)
    radar.set_mode(target, send_completion=False)
    check("set_mode takes effect immediately on the radar object",
          radar.mode is target, f"{getattr(before,'name',before)} -> {mode_name(radar)}")

    radar.set_mode(target, send_completion=False)
    check("setting the mode it is already in is a no-op, not an error",
          radar.mode is target, mode_name(radar))

    # ── the supervisor is the authority (what the log-scraping suite missed) ──
    print("\nRadarManagementSystem enforces mission-phase policy")

    try:
        rm.update_mission_phase(MissionPhase.TAKEOFF)
        converged = await await_condition(
            lambda: radar.mode is weather_radarMode.SURVEILLANCE, timeout=20.0)
        check("TAKEOFF drives the radar to SURVEILLANCE",
              converged, f"mode is {mode_name(radar)}")

        rm.update_mission_phase(MissionPhase.CRUISE)
        converged = await await_condition(
            lambda: radar.mode is weather_radarMode.MAPPING, timeout=20.0)
        check("CRUISE drives the radar to MAPPING",
              converged, f"mode is {mode_name(radar)}")

        rm.update_mission_phase(MissionPhase.APPROACH)
        converged = await await_condition(
            lambda: radar.mode is weather_radarMode.SURVEILLANCE, timeout=20.0)
        check("APPROACH drives it back to SURVEILLANCE",
              converged, f"mode is {mode_name(radar)}")

        # The behaviour that misled a direct reading of radar.mode: a mode set
        # against policy is reverted by the supervisor. Asserting it documents
        # the contract instead of leaving it as a trap.
        rm.update_mission_phase(MissionPhase.CRUISE)
        await await_condition(lambda: radar.mode is weather_radarMode.MAPPING, timeout=20.0)
        radar.set_mode(weather_radarMode.SURVEILLANCE, send_completion=False)
        check("a mode set against policy is applied first...",
              radar.mode is weather_radarMode.SURVEILLANCE, mode_name(radar))
        reverted = await await_condition(
            lambda: radar.mode is weather_radarMode.MAPPING, timeout=20.0)
        check("...then reverted by the supervisor (RMS is the mode authority)",
              reverted, f"mode is {mode_name(radar)}")
    finally:
        rm.update_mission_phase(original_phase)

    # ── the radar produces data, and it reaches the display coordinator ──
    print("\ndata reaches the display coordinator")

    from FMOFP.Interfaces.userInterface.displays.radar.radar_display_data_coordinator import (
        get_radar_display_data_coordinator,
    )
    coord = get_radar_display_data_coordinator()
    check("the display data coordinator is reachable", coord is not None)

    rm.update_mission_phase(MissionPhase.CRUISE)
    await await_condition(lambda: radar.mode is weather_radarMode.MAPPING, timeout=20.0)

    delivered = {}
    for store in ('precipitation', 'vil', 'cells'):
        got = await await_condition(
            lambda s=store: bool(coord.get_data(s, use_backup=True)), timeout=30.0)
        delivered[store] = got

    check("at least one weather product reaches the coordinator",
          any(delivered.values()), str(delivered))
    if delivered.get('precipitation'):
        items = coord.get_data('precipitation', use_backup=True)
        check("precipitation items are dicts with a position",
              all(isinstance(i, dict) for i in items) and
              all('position' in i or 'x' in i or 'lat' in i for i in items[:3]),
              str(items[:1])[:120])

    # ── status surface ───────────────────────────────────────────────────
    print("\nstatus surface")

    status = radar.get_status()
    check("get_status() returns a dict", isinstance(status, dict), type(status).__name__)
    check("status reports the current mode",
          any('mode' in str(k).lower() for k in status), sorted(status)[:6])

    # ── non-tautological guards ──────────────────────────────────────────
    print("\nNON-TAUTOLOGICAL — these must not pass by accident")

    never = await await_condition(lambda: False, timeout=0.5)
    check("await_condition reports failure when the predicate never holds", not never)

    bogus = weather_radarMode.STANDBY if radar.mode is not weather_radarMode.STANDBY \
        else weather_radarMode.MAPPING
    wrong = await await_condition(lambda: radar.mode is bogus, timeout=2.0)
    check("polling for a mode the radar is NOT in fails (assertions can detect wrong state)",
          not wrong, f"radar.mode={mode_name(radar)} bogus={bogus.name}")

    check("the coordinator reports empty for a store that was never written",
          not coord.get_data('a_store_that_does_not_exist', use_backup=True))

    print(f"\nWeather radar (live): {PASS} passed, {FAIL} failed")
    return FAIL


if __name__ == '__main__':
    sys.exit(run_against_live_system(body))
