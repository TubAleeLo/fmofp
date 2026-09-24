"""Aggregating test runner — runs every standalone-safe test suite with one
real exit code.

Why this exists (August 2026 production-readiness follow-up): the repo had 23
test files but CI executed only 7 of them as individually-maintained workflow
steps, and PLANNING.md had already flagged that several test entry points
discard run_tests()'s result (false-positive risk). This runner is the single
source of truth for "the test suite": it subprocess-isolates each suite,
enforces a per-suite watchdog timeout (a hang is a failure, not a stall —
see ci_test_boot_smoke.py for why that matters here), aggregates results,
and exits nonzero if ANY suite fails, times out, or crashes.

Run from B20SS/:  python FMOFP/Tests/run_all_tests.py

Suites deliberately NOT run here, with reasons:
  - All ten CLI-harness-only suites are gone. They exited 1 by design when run
    standalone, printing "This test should be run via the user CLI 'test'
    command", which kept 6,991 lines -- two thirds of the project's test code --
    out of CI. Story C14.1 removed that blocker with Tests/live_system.py, and
    C14.2 - C14.7 replaced every one of them with state assertions:

      radar_tests/weather_radar_test.py          }
      weather_radar_surveillance_mode_test.py    }  test_weather_radar_live.py
      combined_precipitation_vil_flow_test.py    }

      radar_tests/targeting_radar_test.py        }
      radar_tests/tfr_radar_test.py              }  test_radar_modes_live.py
      radar_tests/aewc_radar_test.py             }
      radar_tests/sar_radar_test.py              }

      fms_system_test.py                         -> test_fms_live.py
      flight_control_system_test.py              -> test_flight_control_live.py
      predefined_messages_test.py                -> test_predefined_messages_live.py

    The radar_tests/ package went with them: it held nothing but those five
    files and a docstring promising "comprehensive tests for all radar systems".

  - test_weather_radar_holographic_display: interactive GUI test — enters
    QApplication.exec() and never exits; visual inspection only.
  - performance_profile: a profiler, not a pass/fail test.
  - setup_env: an import helper, not a test.
"""
import os
import subprocess
import sys
import time

# (module path run with -m?, name, timeout seconds)
SUITES = [
    (True,  "FMOFP.Tests.ci_test_boot_smoke", 300),
    (True,  "FMOFP.Tests.test_bridge_and_coordinator", 300),
    (True,  "FMOFP.Tests.test_displays_headless", 300),
    (False, "FMOFP/Tests/ci_test_weather_radar.py", 300),
    (False, "FMOFP/Tests/ci_test_scenario_engine.py", 300),
    (True,  "FMOFP.Tests.test_power_fuel_thrust", 300),
    (True,  "FMOFP.Tests.test_hydr_airframe_ecs_fdm_fitness_swcm", 300),
    (True,  "FMOFP.Tests.test_toctou_start_race_regression", 600),
    (True,  "FMOFP.Tests.test_precipitation_data_transfer", 300),
    (True,  "FMOFP.Tests.test_install_script", 300),
    (True,  "FMOFP.Tests.test_bus_adapter", 300),
    (True,  "FMOFP.Tests.test_scenario_failure_injection", 300),
    (True,  "FMOFP.Tests.test_db_connection_pool", 300),
    (True,  "FMOFP.Tests.test_thread_and_cli_resilience", 300),
    (True,  "FMOFP.Tests.test_radar_shutdown_health", 300),
    (True,  "FMOFP.Tests.test_health_and_readiness", 300),
    (True,  "FMOFP.Tests.test_listener_retry_and_ports", 300),
    (True,  "FMOFP.Tests.test_data_root", 300),
    (True,  "FMOFP.Tests.test_line_endings", 300),
    # Production blockers B5/B11/B12: singleton re-initialisation leaking a
    # thread pool per construction, run-once markers that outlived the process
    # (so every boot after the first skipped database init and never re-read
    # the message-rate config), and an import-time filesystem walk that indexed
    # site-packages on an installed deployment.
    (True,  "FMOFP.Tests.test_blocker_singleton_and_state", 300),
    # Production blockers B6/B7/B8: FCS mode change calling a method that does
    # not exist, FCS control input reading a bool as a dict (after the surface
    # had already moved), and the radar mode-lookup tables being enum members
    # rather than dicts, so every lookup by mode name fell back to STANDBY.
    (True,  "FMOFP.Tests.test_blocker_command_paths", 300),
    # Production blocker B9: one encoder, five decoders, four different sets of
    # precipitation scale factors -- severe weather decoded ~79x low and
    # rendered in the lightest colour band. Round-trip assertions.
    (True,  "FMOFP.Tests.test_blocker_precip_scale", 300),
    # Production blockers B1/B2/B3/B4: a boot failure that hung the process
    # forever and an error shutdown that exited 0; initialization failures
    # swallowed so boot continued on a half-built system; coroutine stops
    # discarded when the loop was halted straight after scheduling them; and an
    # unbounded EventBus join holding the shared lock.
    (True,  "FMOFP.Tests.test_blocker_lifecycle", 300),
    # Story C14.3: four radars swept across every commandable mode against a
    # live system, plus phase-policy and request-dispatch assertions.
    (True,  "FMOFP.Tests.test_radar_modes_live", 420),
    # Story C14.4: FMS mode contract, the FMS->FCS mode mapping, attitude
    # handling and request dispatch, against a live system.
    (True,  "FMOFP.Tests.test_fms_live", 420),
    # Story C14.5: FCS mode vocabulary, control-input saturation and the
    # one-way FMS -> FCS coupling, against a live system.
    (True,  "FMOFP.Tests.test_flight_control_live", 420),
    # Story C14.6: the predefined message facade -- initialisation, the three
    # accepted radar-mode input forms, rejection, and request-ID contracts.
    (True,  "FMOFP.Tests.test_predefined_messages_live", 420),
    # Story C14: runs against a REAL booted application via
    # Tests/live_system.py, so it needs a longer budget than the unit
    # suites -- boot plus supervisory-convergence polling.
    (True,  "FMOFP.Tests.test_weather_radar_live", 420),
]


def run_suite(as_module: bool, name: str, timeout_s: int):
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    cwd = os.getcwd()
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in (cwd, env.get("PYTHONPATH", "")) if p
    )
    cmd = [sys.executable, "-m", name] if as_module else [sys.executable, name]
    start = time.monotonic()
    try:
        proc = subprocess.run(
            cmd, timeout=timeout_s, capture_output=True, text=True,
            env=env, cwd=cwd,
        )
        elapsed = time.monotonic() - start
        return proc.returncode, elapsed, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - start
        out = exc.stdout or b""
        err = exc.stderr or b""
        if isinstance(out, bytes):
            out = out.decode(errors="replace")
        if isinstance(err, bytes):
            err = err.decode(errors="replace")
        return "TIMEOUT", elapsed, out, err


# How many trailing lines of each stream to show for a failing suite. 20 was
# too few to reach the suite's own verdict past Qt's startup warnings.
TAIL_LINES = 60


def main() -> int:
    print(f"Running {len(SUITES)} test suites "
          "(subprocess-isolated, per-suite watchdog)\n" + "=" * 60)
    failures = []
    for as_module, name, timeout_s in SUITES:
        rc, elapsed, out, err = run_suite(as_module, name, timeout_s)
        label = name.rsplit("/", 1)[-1]
        if label.endswith(".py"):
            label = label[:-3]
        else:
            label = label.rsplit(".", 1)[-1]
        if rc == 0:
            print(f"  ✓  {label:<45s} {elapsed:6.1f}s")
        else:
            status = "TIMED OUT" if rc == "TIMEOUT" else f"exit {rc}"
            print(f"  ✗  {label:<45s} {elapsed:6.1f}s  ({status})")
            failures.append((name, rc))
            # Show BOTH streams. This used to be `(err or out)`, which threw
            # stdout away whenever stderr had any content at all -- and stderr
            # is never empty here, because Qt's offscreen plugin warns and the
            # shutdown path logs tracebacks. The result was that a failing
            # suite reported 20 lines of Qt noise while the suite's own "FAIL"
            # lines and verdict, which are on stdout, were discarded. That made
            # a CI failure of test_weather_radar_live undiagnosable from the
            # log (Sept 2026).
            print("     ┌─ last output " + "─" * 40)
            shown = False
            for stream_name, text in (("stdout", out), ("stderr", err)):
                if not (text or "").strip():
                    continue
                shown = True
                lines = text.splitlines()
                clipped = len(lines) - TAIL_LINES
                print(f"     │ ── {stream_name} "
                      + (f"(last {TAIL_LINES} of {len(lines)} lines) "
                         if clipped > 0 else "")
                      + "─" * 10)
                for line in lines[-TAIL_LINES:]:
                    print("     │ " + line)
            if not shown:
                print("     │ (the suite produced no output)")
            print("     └" + "─" * 54)
    print("=" * 60)
    if failures:
        print(f"FAILED: {len(failures)}/{len(SUITES)} suites: "
              + ", ".join(n for n, _ in failures))
        return 1
    print(f"All {len(SUITES)} suites passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
