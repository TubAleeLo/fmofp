"""The precipitation wire encoding, in one place (BLOCKER B9).

One encoder writes precipitation attribute words. Four decoders read them, and
before this module existed three of the four used different scale factors from
the encoder -- and from each other:

    site                                      rate            intensity
    ----------------------------------------  --------------  -------------
    data_response_sender (ENCODER)            code = r * 2    code = i * 63
    precipitation_data_handler (decoder)      r = code / 2    i = code / 63
    BC_transfer_aggregator (decoder)          r = code / 100  i = code / 5000
    RT_transfer_aggregator (decoder)          r = code / 100  i = code / 5000
    radar_display_data_coordinator (decoder)  r = code * 0.01 i = code * 0.0002
    DisplayMessageHandler (decoder)           r = code * 0.01 i = code * 0.0002

A 6-bit intensity code of 63 means 1.0 to the encoder and 0.0252 to the
aggregators -- a factor of about 79. Rate came out 50x low: 25 mm/hr decoded as
0.5 mm/hr. weather_radar_display._get_intensity_color classifies SEVERE above
0.8 and MODERATE above 0.6, so on those paths intensity could never leave the
lowest band and a mature thunderstorm cell painted green. The two aggregators
also carried ad-hoc `if code == 63` special cases that bent the maximum value
towards a different constant again, and read the precipitation type from a
single bit (snow vs rain) where the encoder writes a 4-bit type code.

Everything about the format now lives here, and every site imports it. The
constants are unchanged from the encoder's, so the wire format is the same --
what changes is that the decoders finally agree with it.

Attribute word layout (16 bits), as written by
DataResponseSender._encode_complex_objects:

    bits 15-12 (4)  type_code       see TYPE_CODE_TO_NAME
    bits 11-6  (6)  rate_code       min(63, int(rate_mm_per_hr * RATE_SCALE))
    bits  5-0  (6)  intensity_code  min(63, int(intensity * INTENSITY_SCALE))

Position word layout (16 bits):

    bits 15-8  (8)  x + POSITION_OFFSET
    bits  7-0  (8)  y + POSITION_OFFSET
"""

# Scaling factors for the 6-bit fields (codes 0-63).
#   RATE_SCALE = 2       -> 0-31.5 mm/hr in 0.5 mm/hr steps
#   INTENSITY_SCALE = 63 -> 0.0-1.0 exactly, in steps of 1/63
RATE_SCALE = 2.0
INTENSITY_SCALE = 63.0

# Field widths and positions.
TYPE_SHIFT = 12
TYPE_MASK = 0xF
RATE_SHIFT = 6
RATE_MASK = 0x3F
INTENSITY_SHIFT = 0
INTENSITY_MASK = 0x3F

MAX_CODE = 63

# Positions travel as unsigned bytes with a fixed offset, so the wire range is
# -128..127 in each axis.
POSITION_OFFSET = 128
POSITION_MIN = -128
POSITION_MAX = 127

# The 4-bit type code. Note that the encoder's map is the authority here:
# a decoder that used {0:'rain', 1:'snow', 2:'hail', 3:'mixed'} turned hail
# into sleet and mixed into hail.
TYPE_NAME_TO_CODE = {
    'rain': 0,
    'snow': 1,
    'sleet': 2,
    'hail': 3,
    'mixed': 4,
}
TYPE_CODE_TO_NAME = {code: name for name, code in TYPE_NAME_TO_CODE.items()}

DEFAULT_TYPE = 'rain'


def encode_attribute_word(precip_type: str, rate: float, intensity: float) -> int:
    """Pack a precipitation type, rate (mm/hr) and intensity (0-1) into a word."""
    type_code = TYPE_NAME_TO_CODE.get(precip_type, TYPE_NAME_TO_CODE[DEFAULT_TYPE])
    rate_code = max(0, min(MAX_CODE, int(rate * RATE_SCALE)))
    intensity_code = max(0, min(MAX_CODE, int(intensity * INTENSITY_SCALE)))
    return ((type_code & TYPE_MASK) << TYPE_SHIFT) | (rate_code << RATE_SHIFT) | intensity_code


def decode_attribute_word(attr_word: int):
    """Unpack an attribute word into (type_name, rate_mm_per_hr, intensity).

    The inverse of encode_attribute_word, and the only decode any consumer
    should use. Returns intensity in 0.0-1.0 and rate in mm/hr.
    """
    type_code = (attr_word >> TYPE_SHIFT) & TYPE_MASK
    rate_code = (attr_word >> RATE_SHIFT) & RATE_MASK
    intensity_code = (attr_word >> INTENSITY_SHIFT) & INTENSITY_MASK

    precip_type = TYPE_CODE_TO_NAME.get(type_code, DEFAULT_TYPE)
    rate = float(rate_code) / RATE_SCALE
    intensity = float(intensity_code) / INTENSITY_SCALE
    return precip_type, rate, intensity


def encode_position_word(x: float, y: float) -> int:
    """Pack a position into one word, clamped to the representable range.

    Clamping matters: an unclamped negative coordinate produced a negative
    integer, and `format(negative, '016b')` emits a string with a '-' in it,
    which is not a valid 1553B data word.
    """
    x_byte = max(0, min(255, int(round(x)) + POSITION_OFFSET))
    y_byte = max(0, min(255, int(round(y)) + POSITION_OFFSET))
    return (x_byte << 8) | y_byte


def decode_position_word(pos_word: int):
    """Unpack a position word into (x, y) floats."""
    x = float((pos_word >> 8) & 0xFF) - POSITION_OFFSET
    y = float(pos_word & 0xFF) - POSITION_OFFSET
    return x, y
