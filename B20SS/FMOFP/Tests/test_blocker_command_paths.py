"""Test suite — FCS command handling and radar mode-name lookup (B6, B7, B8).

Three blockers on the path between a command arriving and the system acting on
it. All three failed silently: the command was accepted, something went wrong
inside, and either nothing happened or the wrong thing did.

B6  FCSMessageHandler._handle_mode_change_request called self.fcs.change_mode().
    FlightControlSystem has no such method -- the name appeared exactly once in
    the repository, at that call site. Every mode change arriving over 1553B
    raised AttributeError, was swallowed, and returned ERROR; because the raise
    happened before send_response(), the requester got no response at all.

B7  _handle_control_input_request called .get('success') on the return of
    set_control_input(), which is declared `-> bool`. Same AttributeError, same
    missing response -- but the control surface had ALREADY moved by then. A
    stick or throttle input took effect on the aircraft while the console
    reported failure.

B8  The six mode-lookup dictionaries were declared inside the RadarDisplayMode
    Enum class body, which makes each one an enum MEMBER whose value is a dict
    rather than a dict. from_string() then raised TypeError on every call, and
    the caller that catches it returns STANDBY -- so a radar commanded to
    SURVEILLANCE or TURBULENCE by name quietly stayed in standby.

Standalone-safe: run from B20SS/ as
`python -m FMOFP.Tests.test_blocker_command_paths`.
"""
import asyncio
import os
import sys

_B20SS = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _B20SS not in sys.path:
    sys.path.insert(0, _B20SS)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

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


class _CapturingResponseService:
    """Stands in for the real response service and records what was sent.

    The point of B6/B7 is not only that the handler returned ERROR -- it is
    that it never got as far as sending a response, so the requester hung until
    its own timeout. Asserting on the returned dict alone would miss that.
    """

    def __init__(self):
        self.sent = []

    async def send_response(self, request_id, response):
        self.sent.append((request_id, response))
        return True


# ── B6: FCS mode change ──────────────────────────────────────────────────────

print("\nB6 — FCS mode change over 1553B")

from FMOFP.local_messaging.routing.handlers.system_message_handlers.FCSMessageHandler import (  # noqa: E402
    FCSMessageHandler,
)

# Imported defensively so that running this suite against a tree WITHOUT the
# B6 fix reports failing assertions rather than dying on ImportError: the wire
# encoding used to be a literal dict inside the handler function, with no
# module-level name to import.
try:
    from FMOFP.local_messaging.routing.handlers.system_message_handlers.FCSMessageHandler import (  # noqa: E402
        MODE_VALUE_TO_NAME, MODE_NAME_TO_VALUE,
    )
except ImportError:
    MODE_VALUE_TO_NAME = {0: "NORMAL", 1: "COMBAT", 2: "PRECISION",
                          3: "AUTOPILOT", 4: "TERRAIN", 5: "EMERGENCY"}
    MODE_NAME_TO_VALUE = dict({n: v for v, n in MODE_VALUE_TO_NAME.items()},
                              STANDBY=0)
from FMOFP.Systems.flightManagementSys.flightControlSys.flight_control_system import (  # noqa: E402
    FlightControlModes,
)

handler = FCSMessageHandler()
responses = _CapturingResponseService()
handler.response_service = responses

check("the handler has a live FCS", handler.fcs is not None)
check("FlightControlSystem still has no change_mode()",
      not hasattr(handler.fcs, 'change_mode'),
      "a change_mode() appeared; the B6 fix may be masking a rename")
check("every wire mode value maps to a real FlightControlModes constant",
      set(MODE_VALUE_TO_NAME.values()) <= set(FlightControlModes.get_all_modes()),
      str(sorted(set(MODE_VALUE_TO_NAME.values()))))
check("the name->value map round-trips through the value->name map",
      all(MODE_NAME_TO_VALUE[n] == v for v, n in MODE_VALUE_TO_NAME.items()))

for mode_value, expected_name in sorted(MODE_VALUE_TO_NAME.items()):
    responses.sent.clear()
    request_id = f"b6-{mode_value}"
    result = asyncio.run(handler._handle_mode_change_request({
        'parameters': {'mode_name': expected_name},
        'request_id': request_id,
    }))

    check(f"mode change to {expected_name} reports SUCCESS",
          result.get('status') == 'SUCCESS', str(result))
    check(f"mode change to {expected_name} actually changes the FCS mode",
          handler.fcs.mode == expected_name,
          f"fcs.mode={handler.fcs.mode!r}")
    check(f"mode change to {expected_name} sends a response to the requester",
          [r for r in responses.sent if r[0] == request_id] != [],
          "no response sent -- the requester waits out its timeout (B6)")
    check(f"the response for {expected_name} reports the new mode",
          responses.sent and responses.sent[-1][1].get('new_mode') == expected_name)

# The binary-data form is the one the bus actually uses.
responses.sent.clear()
result = asyncio.run(handler._handle_mode_change_request({
    'data': format(MODE_NAME_TO_VALUE['COMBAT'], '016b'),
    'request_id': 'b6-binary',
}))
check("a mode change carried as a binary data word works",
      result.get('status') == 'SUCCESS' and handler.fcs.mode == 'COMBAT', str(result))

# An out-of-range value must be refused cleanly AND answered, not crash.
responses.sent.clear()
mode_before = handler.fcs.mode
result = asyncio.run(handler._handle_mode_change_request({
    'data': format(9, '016b'),
    'request_id': 'b6-bogus',
}))
check("an undefined mode value is refused", result.get('status') == 'ERROR', str(result))
check("an undefined mode value leaves the FCS mode alone", handler.fcs.mode == mode_before)
check("an undefined mode value still gets a response",
      [r for r in responses.sent if r[0] == 'b6-bogus'] != [])


# ── B7: FCS control input ────────────────────────────────────────────────────

print("\nB7 — FCS control input over 1553B")

for surface, value in (('elevator', 0.5), ('aileron', -0.25), ('throttle', 0.75)):
    responses.sent.clear()
    request_id = f"b7-{surface}"
    result = asyncio.run(handler._handle_control_input_request({
        'parameters': {'control_type': surface, 'value': value},
        'request_id': request_id,
    }))

    check(f"{surface} input reports SUCCESS",
          result.get('status') == 'SUCCESS', str(result))
    check(f"{surface} input is actually applied",
          abs(handler.fcs.control_inputs[surface] - value) < 1e-9,
          f"control_inputs[{surface}]={handler.fcs.control_inputs.get(surface)}")
    check(f"{surface} input sends a response",
          [r for r in responses.sent if r[0] == request_id] != [],
          "the surface moved but the requester was never told (B7)")
    check(f"{surface} response reports the value the FCS actually holds",
          responses.sent and
          abs(responses.sent[-1][1].get('actual_value') -
              handler.fcs.control_inputs[surface]) < 1e-9)

# The saturation contract: the response must report what the FCS holds, not
# echo back the requested value.
responses.sent.clear()
result = asyncio.run(handler._handle_control_input_request({
    'parameters': {'control_type': 'throttle', 'value': 4.0},
    'request_id': 'b7-clamp',
}))
check("an over-range throttle is clamped by the FCS",
      handler.fcs.control_inputs['throttle'] == 1.0,
      str(handler.fcs.control_inputs['throttle']))
check("the response reports the clamped value, not the requested one",
      result.get('actual_value') == 1.0 and result.get('control_value') == 4.0,
      str(result))

# A surface the FCS does not model must be refused cleanly and answered.
responses.sent.clear()
result = asyncio.run(handler._handle_control_input_request({
    'parameters': {'control_type': 'gear', 'value': 1.0},
    'request_id': 'b7-gear',
}))
check("an unmodelled control surface is refused, not crashed on",
      result.get('status') == 'ERROR', str(result))
check("an unmodelled control surface still gets a response",
      [r for r in responses.sent if r[0] == 'b7-gear'] != [])


# ── B8: radar display mode lookup ────────────────────────────────────────────

print("\nB8 — RadarDisplayMode name lookup")

from FMOFP.local_messaging.radar_display_modes import RadarDisplayMode  # noqa: E402

dict_members = [m.name for m in RadarDisplayMode if isinstance(m.value, dict)]
check("no enum member carries a dict as its value",
      dict_members == [],
      f"lookup tables are enum members again: {dict_members} (B8)")
check("every member value is an int",
      all(isinstance(m.value, int) for m in RadarDisplayMode),
      str([(m.name, type(m.value).__name__) for m in RadarDisplayMode
           if not isinstance(m.value, int)]))
check("len() counts only real modes",
      len(RadarDisplayMode) == 36, str(len(RadarDisplayMode)))

for name in ('SURVEILLANCE', 'TURBULENCE', 'WINDSHEAR', 'MAPPING',
             'TERRAIN_FOLLOWING', 'SPOTLIGHT', 'TARGET_TRACK', 'SECTOR_SCAN'):
    mode = RadarDisplayMode.from_string(name)
    check(f"from_string({name!r}) returns {name}, not STANDBY",
          mode is getattr(RadarDisplayMode, name),
          f"got {mode}")

check("from_string is case-insensitive",
      RadarDisplayMode.from_string('turbulence') is RadarDisplayMode.TURBULENCE)
check("from_string still defaults an unknown name to STANDBY",
      RadarDisplayMode.from_string('NOT_A_MODE') is RadarDisplayMode.STANDBY)
check("from_string still defaults empty input to STANDBY",
      RadarDisplayMode.from_string('') is RadarDisplayMode.STANDBY)

# The whole point of the radar-specific tables: one name, five answers.
for radar_type, expected in (('tfr_radar', RadarDisplayMode.TFR_SEARCH),
                             ('targeting_radar', RadarDisplayMode.TARGET_SEARCH),
                             ('aewc_radar', RadarDisplayMode.AEWC_SEARCH)):
    got = RadarDisplayMode.get_radar_specific_mode('SEARCH', radar_type)
    check(f"get_radar_specific_mode('SEARCH', {radar_type!r}) -> {expected.name}",
          got is expected, f"got {got}")

check("get_radar_specific_mode accepts an enum member",
      RadarDisplayMode.get_radar_specific_mode(
          RadarDisplayMode.TURBULENCE, 'weather_radar') is RadarDisplayMode.TURBULENCE)
check("get_radar_specific_mode accepts a numeric value",
      RadarDisplayMode.get_radar_specific_mode(12, 'weather_radar')
      is RadarDisplayMode.TURBULENCE)

# radar_mode_converter.py guards each table with isinstance(..., dict) -- a
# check that could never pass while they were enum members, so every branch
# fell through to the default.
for attr in ('mode_map', 'weather_radar_modes', 'tfr_radar_modes',
             'sar_radar_modes', 'targeting_radar_modes', 'aewc_radar_modes'):
    table = getattr(RadarDisplayMode, attr)
    check(f"RadarDisplayMode.{attr} is a dict (radar_mode_converter checks this)",
          isinstance(table, dict), type(table).__name__)
    check(f"RadarDisplayMode.{attr} maps to enum members, not bare ints",
          all(isinstance(v, RadarDisplayMode) for v in table.values()),
          str([v for v in table.values() if not isinstance(v, RadarDisplayMode)][:3]))

# The consumer contract that matters downstream: callers read .value off the
# result (display_radar_enums.py, display_outgoing_router.py).
check("from_string results expose .value for downstream mapping",
      RadarDisplayMode.from_string('SURVEILLANCE').value == 10)


# ── non-tautological guard ───────────────────────────────────────────────────

print("\nNON-TAUTOLOGICAL — pre-fix behaviour must fail these")

# B8: reproduce the pre-fix declaration and show it really did produce a member
# whose value is a dict, and really did raise on `in`.
from enum import Enum  # noqa: E402


class _PreFixEnum(Enum):
    STANDBY = 0
    SURVEILLANCE = 10
    mode_map = {'SURVEILLANCE': SURVEILLANCE}


check("a dict in an Enum body really becomes a member (proves B8 bites)",
      'mode_map' in _PreFixEnum.__members__)
try:
    'SURVEILLANCE' in _PreFixEnum.mode_map
    _raised = False
except TypeError:
    _raised = True
check("`name in cls.mode_map` really raised TypeError pre-fix (proves B8 bites)",
      _raised)

# B6/B7: the pre-fix calls must still be absent from the source. A regression
# here is a rename, not a fix.
import inspect  # noqa: E402
from FMOFP.local_messaging.routing.handlers.system_message_handlers import (  # noqa: E402
    FCSMessageHandler as _fcs_mod,
)

# Comment lines are stripped first: both pre-fix calls are quoted verbatim in
# the comments that explain them, and a guard that matched those would fail for
# the wrong reason.
_src = '\n'.join(line for line in inspect.getsource(_fcs_mod).split('\n')
                 if not line.lstrip().startswith('#'))
check("handler no longer calls fcs.change_mode()", 'self.fcs.change_mode(' not in _src)
check("handler no longer reads .get('success') off a bool return",
      "result.get('success'" not in _src)
check("no FCS call site passes unsupported kwargs to process_message",
      'transaction_id=transaction_id' not in _src,
      "the loop-prevention gate raises TypeError again")


print(f"\nFCS command and radar mode-lookup tests: {PASS} passed, {FAIL} failed")
if FAIL:
    sys.exit(1)
print("FCS command paths and radar mode lookup: all assertions passed")
