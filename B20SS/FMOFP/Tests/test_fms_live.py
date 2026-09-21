"""Test suite — flight management system against a live system (C14.4).

Replaces fms_system_test.py (1,117 lines, 793 of live code, 4 test methods).

WHAT THE ORIGINAL DID
---------------------
It built three dictionaries of "verification points" and matched each one's regex
against captured log output:

    'bc_transmit': {'pattern': r"BC_sender sending.*message|BC_sender sending frame list"}
    'request_processing': {'pattern': r"Processing mode change to|_handle_mode_change.*request_id"}

A pass meant the phrases appeared somewhere in the log. It could not tell you whether
the FMS mode actually changed, whether the attitude it sent was the attitude that
landed, or whether an invalid input was rejected -- and `set_mode()` returns a real
boolean that nothing checked.

WHAT THIS ASSERTS INSTEAD
-------------------------
The contract in `flightManagementSystem.set_mode()`, which is more interesting than
the original suite's subject:

    valid_modes = ["NORMAL", "COMBAT", "STEALTH", "TRAINING", "EMERGENCY"]
    ...
    fcs_mode_map = {"NORMAL": "NORMAL", "COMBAT": "COMBAT", "STEALTH": "PRECISION",
                    "TRAINING": "NORMAL", "EMERGENCY": "EMERGENCY"}

Setting an FMS mode drives the flight control system to a *mapped* mode -- two of the
five map to a different name. That cross-system coupling is asserted here in both
directions, along with the rejection path and the attitude handler.

TIMING NOTE
-----------
Navigation and attitude are also driven by the running simulation (NavService GPS-INS
fusion, and the FDM). Assertions on values this suite writes are made immediately,
without an intervening await, so they test the write rather than racing the simulation
that will legitimately overwrite it a tick later.

Standalone-safe: run from B20SS/ as `python -m FMOFP.Tests.test_fms_live`.
"""
import asyncio
import os
import sys

_B20SS = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _B20SS not in sys.path:
    sys.path.insert(0, _B20SS)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from FMOFP.Tests.live_system import run_against_live_system  # noqa: E402

PASS = 0
FAIL = 0

VALID_MODES = ("NORMAL", "COMBAT", "STEALTH", "TRAINING", "EMERGENCY")
FCS_FOR_FMS = {"NORMAL": "NORMAL", "COMBAT": "COMBAT", "STEALTH": "PRECISION",
               "TRAINING": "NORMAL", "EMERGENCY": "EMERGENCY"}


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


async def body(sm):
    """Assert FMS behaviour against an already-running system."""
    global PASS, FAIL
    PASS = FAIL = 0

    from FMOFP.Systems.flightManagementSys.flightManagementSystem import (
        get_flightManagementSystem,
    )

    fms = get_flightManagementSystem()
    fh = sm.components.get('fms_message_handler')
    check("the FMS is a registered component", sm.components.get('flightManagementSystem') is fms)
    check("the FMS message handler is a registered component", fh is not None)
    if fms is None or fh is None:
        return 1

    check("the FMS reports healthy", fms.check_health())

    # ── the shape other systems consume ──────────────────────────────────
    print("\nflight data surface")

    data = fms.get_flight_data()
    check("get_flight_data() returns a dict", isinstance(data, dict), type(data).__name__)
    for section in ('attitude', 'navigation', 'velocity', 'status', 'tactical', 'timestamp'):
        check(f"...with a {section!r} section", section in data, sorted(data))
    for field in ('roll', 'pitch', 'yaw', 'roll_rate', 'pitch_rate', 'yaw_rate'):
        check(f"attitude carries {field!r}", field in data['attitude'], sorted(data['attitude']))
    for field in ('airspeed', 'ground_speed', 'mach', 'vertical_speed'):
        check(f"velocity carries {field!r}", field in data['velocity'], sorted(data['velocity']))

    # ── mode: a real return value, and a real state change ───────────────
    print("\nset_mode is a checked operation, not a log line")

    original_mode = fms.get_flight_data()['status']['mode']
    try:
        for mode in VALID_MODES:
            accepted = fms.set_mode(mode)
            state = fms.get_flight_data()
            check(f"set_mode({mode!r}) returns True", accepted is True, repr(accepted))
            check(f"...and status.mode becomes {mode!r}",
                  state['status']['mode'] == mode, state['status']['mode'])
            check("...and tactical.mode agrees (the two are not allowed to diverge)",
                  state['tactical']['mode'] == mode, state['tactical']['mode'])

        # ── the cross-system contract the old suite never saw ────────────
        print("\nFMS mode drives the flight control system through a mapping")

        fcs = fms.flight_control_system
        check("the FMS holds a flight control system", fcs is not None)
        for fms_mode, fcs_mode in FCS_FOR_FMS.items():
            fms.set_mode(fms_mode)
            note = "" if fms_mode == fcs_mode else "  (deliberately different)"
            check(f"FMS {fms_mode} -> FCS {fcs_mode}{note}",
                  fcs.mode == fcs_mode, f"fcs.mode={fcs.mode!r}")

        # ── rejection ────────────────────────────────────────────────────
        print("\nan invalid mode is refused, and says so")

        fms.set_mode("COMBAT")
        before = fms.get_flight_data()['status']['mode']
        for bogus in ("HYPERSPACE", "normal", "", None, 3):
            refused = fms.set_mode(bogus)
            check(f"set_mode({bogus!r}) returns False", refused is False, repr(refused))
        check("...and the mode is unchanged after every refusal",
              fms.get_flight_data()['status']['mode'] == before,
              fms.get_flight_data()['status']['mode'])
    finally:
        fms.set_mode(original_mode if original_mode in VALID_MODES else "NORMAL")

    # ── attitude ─────────────────────────────────────────────────────────
    #
    # Attitude is NOT a value the test can write and then read back. The flight
    # dynamics model drives roll and pitch continuously on its own thread, so a
    # written value is overwritten within milliseconds -- measured: roll set to
    # 12.5 reads back as 0.003 with no await in between. Asserting persistence
    # here would produce a test that fails at the simulation's convenience.
    #
    # What IS stable, and is what a caller actually depends on, is the handler's
    # own report of what it applied. That is asserted; the volatility is asserted
    # too, so the next reader does not mistake it for a bug in the test.
    print("\nattitude updates are accepted, applied and reported")

    sent = {'roll': 12.5, 'pitch': -4.25, 'yaw': 271.0,
            'roll_rate': 1.5, 'pitch_rate': -0.75, 'yaw_rate': 0.25}
    result = await asyncio.wait_for(
        fh._handle_attitude_update({'parameters': dict(sent), 'request_id': 'c14-4-probe'}),
        timeout=30.0)

    check("the handler returns a result dict", isinstance(result, dict), repr(result)[:120])
    check("...reporting SUCCESS", isinstance(result, dict) and result.get('status') == 'SUCCESS',
          repr(result)[:160])

    applied = (result or {}).get('data', {}).get('applied_attitude', {})
    mismatched = {k: (v, applied.get(k)) for k, v in sent.items()
                  if abs(applied.get(k, 1e9) - v) > 0.001}
    check("every field sent is reported back as applied", not mismatched, str(mismatched))

    # NOTHING about fms.attitude is asserted after the write, deliberately.
    # The flight dynamics model owns that dict and rewrites all six fields on its
    # own thread. Measured across runs with identical code: roll read back as
    # 12.5 once and 0.003 the next time, and on later runs every field including
    # yaw and the body rates was back to 0.0. So the observable effect of an
    # attitude update on the FMS object is a race, and a suite that asserted
    # either outcome would fail at the simulation's convenience.
    #
    # That is itself the finding: the attitude-update path reports SUCCESS for
    # values the FDM discards milliseconds later. The handler's report is the
    # only stable contract, which is why it is what gets asserted above.
    held = dict(fms.attitude)
    print(f"    [note] fms.attitude after the update: "
          f"{ {k: round(v, 4) for k, v in held.items()} } "
          f"-- FDM-owned, intentionally unasserted")

    bad = await asyncio.wait_for(fh._handle_attitude_update("not a dict"), timeout=30.0)
    check("a malformed attitude message is rejected with an ERROR status, not an exception",
          isinstance(bad, dict) and bad.get('status') == 'ERROR', repr(bad))

    # ── KNOWN DEFECT, characterised (story C24.1) ────────────────────────
    # A message carrying no 'parameters' updates nothing -- and still reports
    # SUCCESS, with `applied_attitude` echoing the attitude that was already
    # there. A caller cannot distinguish "your values were applied" from
    # "nothing happened". When that is fixed this assertion must fail.
    empty = await asyncio.wait_for(
        fh._handle_attitude_update({'request_id': 'c14-4-empty'}), timeout=30.0)
    check("DEFECT: a parameter-less update still reports SUCCESS "
          "(status alone cannot tell a caller anything was applied)",
          isinstance(empty, dict) and empty.get('status') == 'SUCCESS', repr(empty)[:160])

    # ── navigation ───────────────────────────────────────────────────────
    print("\nnavigation writes are visible immediately")

    fms.update_navigation(latitude=51.4775, longitude=-0.0014, altitude=31000.0, heading=93.5)
    nav = fms.get_flight_data()['navigation']
    check("update_navigation writes latitude", abs(nav['latitude'] - 51.4775) < 1e-6, nav['latitude'])
    check("update_navigation writes longitude", abs(nav['longitude'] + 0.0014) < 1e-6, nav['longitude'])
    check("update_navigation writes altitude", abs(nav['altitude'] - 31000.0) < 1e-6, nav['altitude'])
    check("update_navigation writes heading", abs(nav['heading'] - 93.5) < 1e-6, nav['heading'])

    # ── request dispatch ─────────────────────────────────────────────────
    print("\nrequest dispatch correlates by request ID")

    rid = await asyncio.wait_for(
        fh.send_request('flightManagementSystem', 'status'), timeout=30.0)
    check("a status request returns a request ID",
          isinstance(rid, str) and len(rid) == 36, repr(rid))
    check("the handler registers it under that exact ID",
          isinstance(rid, str) and rid in fh.pending_requests)

    # ── non-tautological guards ──────────────────────────────────────────
    print("\nNON-TAUTOLOGICAL — these must not pass by accident")

    fms.set_mode("STEALTH")
    check("asserting the WRONG mode fails (mode comparison can detect a mismatch)",
          fms.get_flight_data()['status']['mode'] != "COMBAT",
          fms.get_flight_data()['status']['mode'])
    check("the FCS did NOT follow the FMS name verbatim for STEALTH "
          "(proves the mapping is exercised, not bypassed)",
          fms.flight_control_system.mode != "STEALTH", fms.flight_control_system.mode)

    check("the attitude report asserted above was not an empty dict "
          "(an empty `applied` would make the comparison vacuous)",
          len(applied) >= 6, str(sorted(applied)))
    check("a value never sent is absent from the applied report",
          'nonexistent_axis' not in applied, str(sorted(applied)))

    import uuid as _uuid
    check("an ID that was never issued is absent from the pending table",
          str(_uuid.uuid4()) not in fh.pending_requests)

    fms.set_mode("NORMAL")

    print(f"\nFMS (live): {PASS} passed, {FAIL} failed")
    return FAIL


if __name__ == '__main__':
    sys.exit(run_against_live_system(body, body_timeout=300))
