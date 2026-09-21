import inspect, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from FMOFP.Tests.live_system import run_against_live_system
OUT = "/tmp/claude-0/fms_probe.txt"
lines = []
def p(*a): lines.append(" ".join(str(x) for x in a))

async def body(sm):
    from FMOFP.Systems.flightManagementSys.flightManagementSystem import get_flightManagementSystem
    fms = get_flightManagementSystem()
    fh = sm.components['fms_message_handler']
    p("set_mode sig:", inspect.signature(fms.set_mode))
    p("mode-ish attrs:", [a for a in dir(fms) if 'mode' in a.lower() and not a.startswith('__')])
    p("attitude:", {k: round(v, 4) for k, v in fms.attitude.items()})
    fd = fms.get_flight_data()
    for k in ('status', 'navigation', 'velocity'):
        v = fd.get(k)
        p(f"flight_data[{k}]:", sorted(v) if isinstance(v, dict) else repr(v)[:100])
    p("check_health():", fms.check_health())
    fcs = fms.flight_control_system
    p("fcs mode-ish:", [a for a in dir(fcs) if 'mode' in a.lower() and not a.startswith('_')])
    p("fcs.mode:", repr(getattr(fcs, 'mode', 'ABSENT')))
    p("fcs surfaces:", [a for a in dir(fcs) if 'surface' in a.lower() and not a.startswith('_')])
    p("_handle_attitude_update:", hasattr(fh, '_handle_attitude_update'))
    open(OUT, "w").write("\n".join(lines))
    return 0
sys.exit(run_against_live_system(body, body_timeout=120))
