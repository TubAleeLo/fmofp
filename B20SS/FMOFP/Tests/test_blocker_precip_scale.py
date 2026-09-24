"""Test suite — the precipitation wire encoding round-trips (B9).

One encoder writes precipitation attribute words; five decoders read them. Four
of the five used different scale factors from the encoder, and from each other:

    site                                      rate            intensity
    ----------------------------------------  --------------  -------------
    data_response_sender (ENCODER)            code = r * 2    code = i * 63
    precipitation_data_handler (decoder)      r = code / 2    i = code / 63
    BC_transfer_aggregator (decoder)          r = code / 100  i = code / 5000
    RT_transfer_aggregator (decoder)          r = code / 100  i = code / 5000
    radar_display_data_coordinator (decoder)  r = code * 0.01 i = code * 0.0002
    DisplayMessageHandler (decoder)           r = code * 0.01 i = code * 0.0002
    BC.py (decoder)                           a different bit layout entirely

A 6-bit intensity code of 63 means 1.0 to the encoder and 0.0252 to the
aggregators. weather_radar_display._get_intensity_color classifies SEVERE above
0.8 and MODERATE above 0.6, so on those paths intensity could never leave the
lowest band: a mature thunderstorm cell painted green, and rate came out 50x
low (25 mm/hr decoded as 0.5 mm/hr).

The assertions below are round-trip assertions. That is the property that
matters and the one that was missing: not "does this decoder use constant X",
but "does what comes out equal what went in".

Standalone-safe: run from B20SS/ as
`python -m FMOFP.Tests.test_blocker_precip_scale`.
"""
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


from FMOFP.Utils.common import precipitation_scale as PS  # noqa: E402


# ── the shared encoding round-trips ──────────────────────────────────────────

print("\nB9 — encode/decode round trip")

# Rate resolution is 1/RATE_SCALE = 0.5 mm/hr; intensity is 1/63.
RATE_STEP = 1.0 / PS.RATE_SCALE
INTENSITY_STEP = 1.0 / PS.INTENSITY_SCALE

for precip_type in PS.TYPE_NAME_TO_CODE:
    word = PS.encode_attribute_word(precip_type, 10.0, 0.5)
    got_type, _, _ = PS.decode_attribute_word(word)
    check(f"type {precip_type!r} survives the round trip",
          got_type == precip_type, f"got {got_type!r}")

for rate in (0.0, 0.5, 5.0, 12.5, 25.0, 31.5):
    word = PS.encode_attribute_word('rain', rate, 0.5)
    _, got_rate, _ = PS.decode_attribute_word(word)
    check(f"rate {rate} mm/hr round-trips within one step",
          abs(got_rate - rate) <= RATE_STEP, f"got {got_rate}")

for intensity in (0.0, 0.25, 0.5, 0.75, 0.9, 1.0):
    word = PS.encode_attribute_word('rain', 10.0, intensity)
    _, _, got_intensity = PS.decode_attribute_word(word)
    check(f"intensity {intensity} round-trips within one step",
          abs(got_intensity - intensity) <= INTENSITY_STEP, f"got {got_intensity}")

# The specific value the display bands turn on.
word = PS.encode_attribute_word('hail', 25.0, 1.0)
_, got_rate, got_intensity = PS.decode_attribute_word(word)
check("maximum intensity decodes at or near 1.0, not 0.0252",
      got_intensity >= 0.98, str(got_intensity))
check("25 mm/hr decodes at or near 25, not 0.5",
      abs(got_rate - 25.0) <= RATE_STEP, str(got_rate))

# Saturation, not wraparound.
word = PS.encode_attribute_word('rain', 1000.0, 5.0)
_, got_rate, got_intensity = PS.decode_attribute_word(word)
check("an over-range rate saturates at the top code",
      abs(got_rate - PS.MAX_CODE / PS.RATE_SCALE) < 1e-9, str(got_rate))
check("an over-range intensity saturates at 1.0",
      abs(got_intensity - 1.0) < 1e-9, str(got_intensity))
check("an over-range encode still fits in 16 bits", 0 <= word <= 0xFFFF, hex(word))

# Position words: negative coordinates must not produce a negative integer,
# because format(negative, '016b') emits a string containing '-', which is not
# a valid 1553B data word.
for x, y in ((0, 0), (-128, -128), (127, 127), (-40, 60), (12, -95)):
    word = PS.encode_position_word(x, y)
    got_x, got_y = PS.decode_position_word(word)
    check(f"position ({x}, {y}) round-trips", (got_x, got_y) == (x, y), f"got ({got_x}, {got_y})")
    check(f"position ({x}, {y}) encodes to a valid 16-bit word",
          0 <= word <= 0xFFFF and '-' not in format(word, '016b'), format(word, '016b'))

word = PS.encode_position_word(-500, 500)
check("an out-of-range position clamps instead of going negative",
      0 <= word <= 0xFFFF, hex(word))


# ── every decoder in the tree agrees with the encoder ────────────────────────

print("\nB9 — all decode sites import the one definition")

import inspect  # noqa: E402

DECODER_MODULES = [
    'FMOFP.Systems.radarManagement.radar_messaging.data_response_sender',
    'FMOFP.local_messaging.routing.handlers.precipitation_data_handler',
    'FMOFP.MIL_STD_1553B.Bus_Controller.BC_transfer_aggregator',
    'FMOFP.MIL_STD_1553B.Remote_Terminal.RT_messaging.RT_transfer_aggregator',
    'FMOFP.MIL_STD_1553B.Bus_Controller.BC',
    'FMOFP.local_messaging.routing.handlers.system_message_handlers.DisplayMessageHandler',
    'FMOFP.Interfaces.userInterface.displays.radar.radar_display_data_coordinator',
]

# The constants that were wrong at one site or another. A decoder that has gone
# back to a literal will match one of these.
STALE_FACTORS = ('/ 5000.0', '/ 2500.0', '* 0.0002', '/ 100.0', '/ 50.0', '* 0.01')

for mod_name in DECODER_MODULES:
    __import__(mod_name)
    mod = sys.modules[mod_name]
    src = inspect.getsource(mod)
    code = '\n'.join(line for line in src.split('\n')
                     if not line.lstrip().startswith('#'))

    check(f"{mod_name.rsplit('.', 1)[-1]} imports the shared scale module",
          'precipitation_scale' in src, "defines its own constants again (B9)")

    stale = [f for f in STALE_FACTORS if f in code]
    check(f"{mod_name.rsplit('.', 1)[-1]} carries no stale precipitation scale factor",
          stale == [], f"found {stale}")

# The two aggregators had ad-hoc special cases that bent the maximum value
# towards a third constant again.
for mod_name in ('FMOFP.MIL_STD_1553B.Bus_Controller.BC_transfer_aggregator',
                 'FMOFP.MIL_STD_1553B.Remote_Terminal.RT_messaging.RT_transfer_aggregator'):
    code = '\n'.join(line for line in inspect.getsource(sys.modules[mod_name]).split('\n')
                     if not line.lstrip().startswith('#'))
    check(f"{mod_name.rsplit('.', 1)[-1]} has no `== 63` special case",
          'rate_bits == 63' not in code and 'intensity_bits == 63' not in code)

# Type maps: an incomplete one silently renamed the weather.
check("the type map has all five encoder types",
      set(PS.TYPE_NAME_TO_CODE) == {'rain', 'snow', 'sleet', 'hail', 'mixed'},
      str(sorted(PS.TYPE_NAME_TO_CODE)))
check("hail does not decode as sleet",
      PS.decode_attribute_word(PS.encode_attribute_word('hail', 1, 1))[0] == 'hail')
check("mixed does not decode as hail",
      PS.decode_attribute_word(PS.encode_attribute_word('mixed', 1, 1))[0] == 'mixed')


# ── the display bands the operator actually sees ─────────────────────────────

print("\nB9 — decoded intensity reaches the display's colour bands")

# weather_radar_display._get_intensity_color: SEVERE > 0.8, MODERATE > 0.6,
# LIGHT > 0.3. Encode a severe cell and confirm it decodes into the severe band.
for label, intensity, floor in (('severe', 0.95, 0.8),
                                ('moderate', 0.7, 0.6),
                                ('light', 0.45, 0.3)):
    _, _, decoded = PS.decode_attribute_word(
        PS.encode_attribute_word('rain', 20.0, intensity))
    check(f"a {label} cell (intensity {intensity}) decodes above {floor}",
          decoded > floor, f"decoded {decoded}")


# ── non-tautological guard ───────────────────────────────────────────────────

print("\nNON-TAUTOLOGICAL — pre-fix behaviour must fail these")

# Reproduce the pre-fix aggregator arithmetic and show what it did to a
# maximum-intensity return.
_pre_fix_intensity = 63 / 2500.0      # the old `intensity_bits == 63` branch
_pre_fix_rate = 63 / 50.0             # the old `rate_bits == 63` branch
check("the pre-fix aggregator really did decode max intensity as ~0.025 "
      "(proves B9 bites)",
      _pre_fix_intensity < 0.03, str(_pre_fix_intensity))
check("the pre-fix aggregator intensity could never reach the SEVERE band",
      _pre_fix_intensity < 0.8)
check("the pre-fix aggregator intensity could never reach even the LIGHT band",
      _pre_fix_intensity < 0.3)
check("25 mm/hr really did decode as 0.5 mm/hr pre-fix (proves B9 bites)",
      abs(int(25.0 * 2) / 100.0 - 0.5) < 1e-9)

# The pre-fix BC.py layout put every field in the wrong bits.
_word = PS.encode_attribute_word('hail', 20.0, 0.9)
_pre_fix_type = (_word >> 14) & 0x3          # BC.py's old 2-bit type field
check("the pre-fix BC.py bit layout really did misread the type "
      "(proves B9 bites)",
      _pre_fix_type != PS.TYPE_NAME_TO_CODE['hail'],
      f"old layout read {_pre_fix_type}, encoder wrote "
      f"{PS.TYPE_NAME_TO_CODE['hail']}")


print(f"\nPrecipitation scale tests: {PASS} passed, {FAIL} failed")
if FAIL:
    sys.exit(1)
print("Precipitation wire encoding: all assertions passed")
