# FMOFP B20SS — Planning & Progress Document

> **Last updated:** June 2026 (auto-generated from full codebase audit)

---

## 1. Project Overview

The **Flight Management Operating Flight Program (FMOFP)** is a Python-based avionics simulation system for the B20SS military aircraft. It integrates five radar types, three display families, a full MIL-STD-1553B bus simulation, flight management, flight control, and a suite of aircraft sub-systems through an event-driven, async/threading architecture.

**Runtime stack:** Python 3.9+, PyQt6, NumPy, SQLite (via internal `DBM`), `asyncio` + `qasync`
**Target OS:** Windows 10/11 64-bit (PyQt6 wheels bundled for AMD64 and ARM64)
**Entry point:** `B20SS/FMOFP/Main.py`

---

## 2. System Architecture

### 2.1 Layer Model

```
┌─────────────────────────────────────────────────────────────────────┐
│                        User Interface Layer                         │
│  PFD / Futuristic-PFD / Holographic-PFD                            │
│  MFD / Futuristic-MFD / Holographic-MFD                            │
│  Radar displays (Weather, Targeting, SAR, TFR, AEWC)               │
│  EICAS · TSD · SMS · HUD container                                  │
└─────────────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────────────┐
│                       Application Layer                             │
│  SystemManager · Initializer · EventBus                             │
│  RadarManagement · DisplayManagement · FlightManagementSys          │
│  FlightControlSys · NavigationSys · CommsSys · MissionPlanning      │
└─────────────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────────────┐
│                     Communication Layer                             │
│  MIL-STD-1553B (Bus Controller + Remote Terminals)                  │
│  LocalMessaging routing stack (unified router, response services)   │
│  Radar-to-Display Bridge (synchronous short-circuit path)           │
└─────────────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────────────┐
│                         Data Layer                                  │
│  DBM (SQLite wrapper) · 7 specialised databases · schema.xml        │
│  RadarDisplayDataCoordinator (TTL-backed in-memory store)           │
│  RadarDataFusion (cross-radar threat correlation, singleton)        │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Directory Structure

```
B20SS/
├── FMOFP/
│   ├── Main.py / SystemStart.py          Entry points
│   ├── core/                             SystemManager, EventBus, Initializer
│   ├── Systems/
│   │   ├── radarManagement/              5 radar types + fusion layer
│   │   ├── flightManagementSys/          FMS + FMS messaging
│   │   ├── flightControlSys/             FCC + GCAS + performance monitoring
│   │   ├── nav/                          GPS, INS, TACAN, data fusion
│   │   ├── comms/                        Radios, SatCom, data link
│   │   ├── missionPlanning/              Route mgmt, order of battle, targeting
│   │   ├── avionics/                     Hardware health monitoring
│   │   ├── defensiveSys/                 (stub — dsConfig.xml only)
│   │   ├── sensorManagement/             (stub)
│   │   └── [9 other subsystems]          airframe, electrical, engine, env, etc.
│   ├── Interfaces/
│   │   ├── userInterface/displays/       All Qt display classes + visual layer
│   │   ├── predefinedMessages/           Typed message classes for all 5 radars
│   │   └── scenarios/                   Training / failure XML scenarios
│   ├── MIL_STD_1553B/                    Full 1553B protocol implementation
│   ├── local_messaging/                  Routing, handlers, response services
│   ├── storage/                          DBM.py, schema.xml
│   ├── Utils/                            Logger, thread mgr, loop prevention, CLI
│   └── Tests/                           Integration + unit test suites
├── FMOFP_User_Manual/                   14-chapter markdown manual
├── __ABOUT__/                           Architecture diagrams, screenshots, demos
├── __Diagrams__/                        UML package/component/sequence/state PNGs
├── __TOOLS__/                           Dev utilities (cleanup, XML naming, struct)
├── PyQt6/                              Bundled wheels (AMD64 + ARM64)
├── python packages/                    Additional bundled packages
└── install.py                          6-step automated installer
```

### 2.3 MIL-STD-1553B Implementation

**Status: ✅ OPERATIONAL**

Full simulation of the military avionics data bus with:
- 16-bit Command / Status / Data word encoding and validation
- Bus Controller (BC) + Remote Terminal (RT) architecture
- Block transfer manager for large data sets
- Message loop prevention (UUID tracking + middleware decorators)
- Transaction tracking via `tracking_library.py`
- Metadata codec and message schema normalisation

**RT Address assignments (from `rtAddressConfig.xml`):**

| RT | System |
|----|--------|
| 5 | Flight Control System |
| 7 | Navigation Systems |
| 9 | Radar Systems |
| 11 | Display Systems |
| 12 | Flight Management System |

**Radar subaddresses (RT 9):**

| Sub | Radar |
|-----|-------|
| 1 | Weather |
| 2 | TFR |
| 3 | SAR |
| 4 | Targeting |
| 5 | AEWC |

**Display subaddresses (RT 11):** PFD (11), MFD (12), EICAS (13), Radar (14), TSD (15), SMS (16)

### 2.4 Local Messaging / Routing Stack

**Status: ✅ OPERATIONAL**

The `local_messaging/` layer is the internal pub-sub backbone that decouples radar data generation from display updates:

- `UnifiedRouter` → `MessageRoutingService` → `MessageDispatcher`
- `RouteResolver` + `RoutingRegistry` for type-based dispatch
- `MessageValidator` + `MessageTransformer` for normalisation
- Handler hierarchy: `BaseMessageHandler` → `RadarMessageHandler`, `FCSMessageHandler`, `FMSMessageHandler`, `DisplayMessageHandler`
- Response service hierarchy: `RadarResponseService`, `FMSResponseService`, `DisplayResponseService`
- Data response services: VIL, Precipitation, EchoTop, FMS attitude/nav/tactical/velocity
- `AsyncMessageHandler` (4-worker thread pool, UUID tracking, rate limiting 10 req/s)
- `DisplayOutgoingRouter` for display → radar direction

**Key resolved issue — Radar-to-Display Bridge:**

The original flow attempted to push data through the RT → BC direction of the 1553B bus, which created two problems:
1. Data was sent *toward* the Bus Controller, never reaching the display coordinator
2. VILResponseService → DisplayMessageHandler → MessageRoutingService → VILResponseService formed a message loop silently killed by loop-prevention decorators

**Resolution:** `radar_to_display_bridge.py` short-circuits this by importing `RadarDisplayDataCoordinator` directly. It is framework-agnostic (no asyncio, no Qt) and callable from any thread. All five radar types now push through this bridge.

### 2.5 Radar Display Data Coordinator

**Status: ✅ OPERATIONAL**

`RadarDisplayDataCoordinator` (singleton) provides TTL-backed in-memory storage between radar processing cycles and Qt paint events:

- Three data stores: `precipitation`, `vil`, `cells` — each with `current` + `backup` + 5s TTL
- `store_data(data_type, items, request_id)` / `get_data(data_type, use_backup=True)`
- Backup fallback: if `current` is expired, serves `backup` transparently
- `cleanup_expired()` runs on a 5s interval
- `_process_items()` normalises typed objects (VILData, PrecipitationData, dicts) to a uniform dict format
- Thread-safe with throttled logging (10s interval)

The bridge + coordinator combination is covered by 15 unit tests in `test_bridge_and_coordinator.py`.

### 2.6 Cross-Radar Data Fusion

**Status: ✅ OPERATIONAL**

`RadarDataFusion` (singleton, `radar_data_fusion.py`) correlates tracks from all five radar systems into a unified `FusedTrack` list:

- Ingests targeting, AEWC, SAR, TFR, weather data
- Computes range, bearing, altitude from position vectors
- Classifies tracks: HOSTILE / FRIENDLY / UNKNOWN based on identity/classification fields
- Exports `to_tsd_dict()` for direct TSD rendering
- Thread-safe with lock on `__new__`

---

## 3. Radar System Implementations

### 3.1 Weather Radar ✅ OPERATIONAL

**Files:** `Systems/radarManagement/weather/`

| Component | File | Status |
|-----------|------|--------|
| Core radar class | `weather_radar.py` | ✅ |
| VIL data generator | `vil_data_generator.py` / `_sync.py` | ✅ |
| Precipitation generator | `precipitation_data_generator_sync.py` | ✅ |
| Reflectivity simulator | `reflectivity_simulator.py` | ✅ |
| Storm cell tracker | `radar_messaging/stormCellTracking.py` | ✅ |
| Precipitation analyser | `radar_messaging/precipitation_analysis.py` | ✅ |
| Wind shear processor | `weather_processor.py → WindShearProcessor` | ✅ |
| Turbulence processor | `weather_processor.py → TurbulenceProcessor` | ✅ |
| Weather state manager | `weather_state_manager.py` | ✅ |
| Message type detector | `weather_message_type_detector.py` | ✅ |
| Simulated radar | `SimulatedWeatherRadar.py` | ✅ |

**Modes:** STANDBY · SURVEILLANCE · MAPPING · TURBULENCE · WINDSHEAR

**Capability detail:**
- `StormCellTracker`: linked-list of `StormCell` dataclasses (position, altitude, reflectivity, velocity, size, intensity, vertical development, timestamp)
- `PrecipitationAnalyzer`: dBZ thresholding (≥30 dBZ), Z-R relationship for rate, type classification (rain/snow/hail/mixed)
- `WindShearProcessor`: radial velocity divergence detection, microburst flagging, severity levels LOW/MODERATE/SEVERE
- `TurbulenceProcessor`: EDR proxy from spatial reflectivity variance, FAA AC 120-88A categories LIGHT/MODERATE/SEVERE/EXTREME
- VIL: layer integration of reflectivity, vertical profile, storm intensity
- Update rate 1 Hz min; range 50/100/200 nm; elevation −15° to +90°; azimuth resolution 0.5°

**Display path:** `weather_radar.py` → `radar_to_display_bridge.push_vil_data / push_precipitation_data` → `RadarDisplayDataCoordinator` → `WeatherRadarDisplay` / `HolographicWeatherRadarDisplay`

**Known issue:** Weather radar → display data flow via the 1553B chain is still not fully operational. The bridge path is the current working route.

---

### 3.2 Targeting Radar ✅ OPERATIONAL

**Files:** `Systems/radarManagement/targeting/`

| Component | File | Status |
|-----------|------|--------|
| Core radar class | `targeting_radar.py` | ✅ |
| Target processor | `target_processor.py` | ✅ |

**Modes:** STANDBY · SEARCH · TRACK · LOCK · GROUND_MAPPING · TERRAIN_AVOIDANCE

**Capabilities:** Multi-target tracking (100+ targets), track-while-scan, RCS signature analysis, ECM/ECCM, target classification

**Technical requirements:** 10 Hz update, 5 m range precision, 1 m/s velocity accuracy

**Display path:** `targeting_radar.py` → `radar_to_display_bridge.push_targeting_data` → coordinator → `TargetingRadarDisplay`

---

### 3.3 SAR Radar ✅ OPERATIONAL

**Files:** `Systems/radarManagement/syntheticAperture/`

| Component | File | Status |
|-----------|------|--------|
| Core radar class | `sar_radar.py` | ✅ |
| SAR processor | `sar_processor.py` | ✅ |

**Modes:** STANDBY · STRIPMAP · SPOTLIGHT · SCANSAR · INTERFEROMETRIC · DOPPLER_BEAM

**Capabilities:** 0.3 m resolution (spotlight), 10 km swath, <1 s processing latency, 3D terrain reconstruction via interferometry, change detection

**Display path:** `radar_to_display_bridge.push_sar_data` → coordinator → `SARRadarDisplay`

---

### 3.4 AEWC Radar ✅ OPERATIONAL

**Files:** `Systems/radarManagement/aewc/`

| Component | File | Status |
|-----------|------|--------|
| Core radar class | `aewc_radar.py` | ✅ |
| AEWC processor | `aewc_processor.py` | ✅ |

**Modes:** STANDBY · SEARCH · TRACK · SECTOR_SCAN · GROUND_MAPPING · STEALTH_DETECTION · ELECTRONIC_PROTECTION

**Capabilities:** 200+ nm range, 1000+ target capacity, stealth track detection, electronic protection (active/passive jamming mitigation), data fusion, formation analysis

**Technical requirements:** 6 rpm minimum rotation, false alarm rate <10⁻⁶

**Display path:** `radar_to_display_bridge.push_aewc_data` → coordinator → `AEWCRadarDisplay`

---

### 3.5 TFR Radar ✅ OPERATIONAL

**Files:** `Systems/radarManagement/terrainFollowing/`

| Component | File | Status |
|-----------|------|--------|
| Core radar class | `tfr_radar.py` | ✅ |
| TFR processor | `tfr_processor.py` | ✅ |
| Message type detector | `tfr_message_type_detector.py` | ✅ |

**Modes:** STANDBY · SEARCH · TRACK · TERRAIN_FOLLOWING · OBSTACLE_AVOIDANCE · GROUND_MAPPING

**Capabilities:** Terrain profile matching, obstacle detection (linked-list of obstacles with range/elevation/classification/threat), dynamic path optimisation, wire detection, ground mapping

**Technical requirements:** 20 Hz update, 1 m range resolution, 0.5 m height accuracy, 5 nm look-ahead minimum

**Display path:** `radar_to_display_bridge.push_tfr_data` → coordinator → `TFRRadarDisplay`

---

## 4. Display System

### 4.1 Display Class Hierarchy ✅ OPERATIONAL

```
BaseDisplay (base_display.py)
├── PFD (pfd.py)
│   ├── FuturisticPFD (futuristic_pfd.py)
│   └── HolographicPFD (holographic_pfd.py)
├── MFD (mfd.py)
│   ├── FuturisticMFD (futuristic_mfd.py)
│   └── HolographicMFD (holographic_mfd.py)
├── HolographicDisplay (holographic_display.py)
├── EICASDisplay (eicas.py)              — engine/system alerts
├── TacticalSituationDisplay (tsd.py)   — threat picture, fused tracks
└── StoresManagementDisplay (sms.py)    — weapon station monitoring

BaseRadarDisplay (radar/base_radar_display.py)
├── FuturisticRadarDisplay (futuristic_radar_display.py)
│   └── HolographicRadarDisplay (holographic_radar_display.py)
├── WeatherRadarDisplay (weather_radar_display.py)
│   └── HolographicWeatherRadarDisplay (weather_radar_holographic_display.py)
├── TargetingRadarDisplay (targeting_radar_display.py)
├── SARRadarDisplay (sar_radar_display.py)
├── TFRRadarDisplay (tfr_radar_display.py)
└── AEWCRadarDisplay (aewc_radar_display.py)

Containers:
├── HUDContainer (hud_container.py)
├── PFDContainer (pfd_container.py)
└── MFDContainer (mfd_container.py)
```

### 4.2 Visual / Theme Layer ✅ OPERATIONAL

```
Interfaces/userInterface/displays/visual/
├── theme_manager.py           — DisplayTheme enum (CLASSIC, MODERN, MINIMAL)
├── enhanced_theme_manager.py  — EnhancedDisplayTheme (STANDARD, HOLOGRAPHIC, FUTURISTIC)
├── effects.py                 — VisualEffects base class
├── enhanced_effects.py        — EnhancedVisualEffects (parallax, depth, glow)
├── animation_controller.py    — AnimationController + TransitionGroup (QObject-based)
├── settings_panel.py          — SettingsPanel + SettingsOption
├── holographic_settings_panel.py — Extended holographic controls
└── theme_config.json          — Persisted theme preferences
```

### 4.3 Display Node System ✅ OPERATIONAL

A state-tree system for managing display modes:

```
display_nodes/
├── display_node_base.py   — DisplayNode + NodeMetadata base
├── visual_node.py         — VisualNode (rendering state)
├── orientation_node.py    — OrientationNode (attitude / heading)
├── mode_node.py           — ModeNode (radar mode → display state mapping)
└── display_tree_manager.py — DisplayTreeManager + FallbackMode enum
```

`DisplayTreeManager` dynamically loads radar enums from module introspection and maps them to display state nodes with fallback handling.

### 4.4 Enhanced Radar Rendering System ✅ OPERATIONAL

```
Interfaces/userInterface/displays/radar/rendering/
├── radar_rendering_engine.py     — Core rendering with Gaussian kernel blobs
├── particle_system.py            — Particle-based weather visualisation
├── particle_renderer.py          — Integrates particle system with rendering engine
├── animation_controller.py       — Wind vectors, temporal effects, frame timing
├── spatial_partitioning.py       — Cell-based culling for performance
├── weather_data_buffer_manager.py — Multi-layer buffer management
├── enhanced_radar_display.py     — Drop-in wrapper: EnhancedRadarDisplay(existing_display)
└── USAGE_GUIDE.md                — Integration guide with code examples
```

**Key features:**
- Gaussian kernel rendering: smooth blob-like weather returns replacing simple geometry
- Particle renderer: wind-driven particle clusters with lifetimes, clustering algorithm (main + satellite clusters with normal-distribution spread)
- Quality levels 1–5: controls kernel size, particle count, noise, animation complexity
- `EnhancedRadarDisplay(display)` wraps any existing display instance with automatic legacy fallback
- Wind parameters: `set_wind_parameters(direction_deg, speed_px_s)` + `set_turbulence(0.0–1.0)`
- Animation via `@keyframes`-equivalent using `AnimationController` + `QTimer`

### 4.5 Radar Event System ✅ OPERATIONAL

```
radar/radar_event_system/
├── radar_event_manager.py   — Publish/subscribe for radar state changes
├── radar_topic_registry.py  — Topic name → handler registry
└── display_cache.py         — Short-lived display-side data cache
```

### 4.6 Display Factory Pattern ✅ OPERATIONAL

| Factory | File |
|---------|------|
| `HUDDisplayFactory` | `hud_display_factory.py` |
| `MFDDisplayFactory` | `mfd_display_factory.py` |
| `PFDDisplayFactory` | `pfd_display_factory.py` |
| `RadarDisplayFactory` | `radar/radar_display_factory.py` |

---

## 5. Flight Management System (FMS) ✅ OPERATIONAL

```
Systems/flightManagementSys/
├── flightManagementSystem.py   — Core FMS
├── fmsControl.py               — Control interface
├── fmsMessenger.py             — 1553B messaging
├── fms_message_processor.py    — Incoming message handling
├── fms_message_type_detector.py
└── fms_messaging/              — Response services (attitude, nav, velocity, tactical)
```

FMS provides real-time flight data to the PFD/MFD:
- Attitude (pitch, roll, yaw, G-force, AoA)
- Navigation (position, waypoints, flight plan)
- Velocity (airspeed, groundspeed, vertical speed)
- Tactical (energy state, threat awareness)

Response services: `FMSAttitudeResponseService`, `FMSNavigationResponseService`, `FMSVelocityResponseService`, `FMSTacticalResponseService`

---

## 6. Flight Control System (FCS) ✅ OPERATIONAL

```
Systems/flightControlSys/
├── flightControlComputer/      — FCC implementation
├── groundCollisionAvoidanceSys/ — GCAS
└── performaneMonitoring/       — Performance envelope monitoring
```

FCS messages covered by `predefinedMessages/fcs_messages.py` and handled by `FCSMessageHandler` / `FCSResponseService`.

---

## 7. Navigation System ✅ OPERATIONAL (partial)

```
Systems/nav/
├── gps/           — GPS receiver simulation
├── ins/           — Inertial navigation system
├── TACAN/         — TACAN navigation aid
└── dataFusion/    — GPS + INS fusion
```

---

## 8. Communications System ✅ OPERATIONAL (framework)

```
Systems/comms/
├── radios/           — Radio communication simulation
├── satcom/           — Satellite communications
├── dataLink/         — Data link systems
└── messaging_service.py
```

---

## 9. Mission Planning ✅ OPERATIONAL (framework)

```
Systems/missionPlanning/
├── missionControl.py
├── missionData/        — Mission data storage
├── orderOfBattle/      — OOB management
├── routeManagement/    — Waypoint / route handling
└── targeting/          — Target designation
```

---

## 10. Predefined Message Library ✅ OPERATIONAL

```
Interfaces/predefinedMessages/
├── Messages.py                    — Registry / dispatcher
├── message_base.py               — Base message class
├── radar_enums.py                 — Shared radar enumerations
├── weather_radar_messages.py      — Typed weather message classes
├── targeting_radar_messages.py    — Targeting message classes
├── sar_radar_messages.py          — SAR message classes
├── tfr_radar_messages.py          — TFR message classes
├── aewc_radar_messages.py         — AEWC message classes
├── fms_messages.py                — FMS message classes
├── fcs_messages.py                — FCS message classes
└── usage_example.py               — Integration examples
```

---

## 11. Installer ✅ OPERATIONAL

`B20SS/install.py` — 6-step automated installer:

1. **Python version check** — requires 3.9+
2. **Directory structure** — validates all required subdirectories
3. **Dependencies** — installs PyQt6, NumPy, qasync from bundled wheels or PyPI; supports `--offline`, `--force-reinstall`
4. **Config validation** — parses and validates all four XML config files
5. **Database initialisation** — creates all SQLite tables from `schema.xml`
6. **Startup verification** — dry-runs all subsystem imports and confirms STANDBY state

Supports `--offline`, `--no-verify`, `--force-reinstall` flags. Exit codes: 0 = success, 1 = failure.

---

## 12. Test Coverage

| Test file | What it covers |
|-----------|----------------|
| `test_bridge_and_coordinator.py` | 15 tests: coordinator store/get/TTL/backup/reset + bridge push for all 5 radars |
| `radar_tests/weather_radar_test.py` | Weather radar mode transitions, VIL, precipitation |
| `radar_tests/targeting_radar_test.py` | Targeting modes, track lifecycle |
| `radar_tests/sar_radar_test.py` | SAR mode transitions |
| `radar_tests/tfr_radar_test.py` | TFR terrain following modes |
| `radar_tests/aewc_radar_test.py` | AEWC surveillance modes |
| `combined_precipitation_vil_flow_test.py` | End-to-end precipitation + VIL data flow |
| `weather_radar_surveillance_mode_test.py` | Surveillance mode data pipeline |
| `fms_system_test.py` | FMS message processing and response services |
| `flight_control_system_test.py` | FCS mode and message handling |
| `predefined_messages_test.py` | Message class construction and serialisation |
| `test_displays_headless.py` | EICAS, TSD, SMS display logic (headless Qt) |
| `test_weather_radar_holographic_display.py` | Holographic weather display rendering |
| `test_bridge_and_coordinator.py` | Bridge + coordinator (15 cases) |
| `test_install_script.py` | Installer step validation |
| `test_precipitation_data_transfer.py` | Precipitation data transfer pipeline |

**Test runner:** `Tests/setup_env.py` configures `sys.path`; all tests are standalone scripts using a lightweight `_Results` harness (no pytest dependency).

---

## 13. Configuration Files

| File | Purpose |
|------|---------|
| `rtAddressConfig.xml` | RT address → system name mapping |
| `messageRateConfig.xml` | Per-message-type transmission rates and priorities |
| `queryRateConfig.xml` | Database query rate limits per system |
| `dbConfig.xml` | Database assignments, pool sizes, retry policies |
| `startupConfiguration.xml` | Component init order and verification steps |
| `storage/databases/schema.xml` | SQLite table definitions for all 7 databases |
| `Systems/radarManagement/rmConfig.xml` | Radar management configuration |
| `Systems/radarManagement/radar_messaging/radar_address_book.xml` | Radar RT/subaddress lookups |

---

## 14. Current Status Summary

### ✅ Fully Operational

- All five radar processors (Weather, Targeting, SAR, TFR, AEWC)
- Weather radar advanced capabilities: VIL, precipitation, storm cell tracking, wind shear detection, turbulence mapping
- MIL-STD-1553B bus simulation (BC + RT + all word types)
- Radar-to-Display bridge (direct sync path for all 5 radars)
- RadarDisplayDataCoordinator (TTL store + backup fallback)
- Cross-radar data fusion (`RadarDataFusion` singleton)
- Display class hierarchy (PFD, MFD, Holographic, EICAS, TSD, SMS)
- Enhanced rendering engine (Gaussian kernel + particle system)
- Display node state-tree system
- Visual / theme layer (Standard, Futuristic, Holographic themes)
- FMS integration: attitude, navigation, velocity, tactical data to PFD/MFD
- FCS integration
- Local messaging routing stack (unified router + handlers + response services)
- Predefined message library for all subsystems
- Automated 6-step installer
- Test suite (15+ test files)

### 🐛 Known Issues

| Issue | Location | Notes |
|-------|----------|-------|
| Weather radar → display via 1553B chain | `local_messaging/routing/handlers/precipitation_data_handler.py` | Bridge path works; 1553B chain does not deliver to coordinator. Debug `[PRECIPITATION_FLOW_DEBUG]` logging left at ERROR level — should be cleaned up. |
| Debug logging at ERROR level | `vil_data_handler.py`, `precipitation_data_handler.py` | Multiple `logger.error(f"[*_FLOW_DEBUG] ...")` lines should be downgraded to `logger.debug()` or removed. |
| CLI status request not implemented | `Utils/debug/userCLI.py:142` | `# TODO: Implement status request` |

### 🚧 Stub / Incomplete Subsystems

| System | Location | Status |
|--------|----------|--------|
| Defensive Systems | `Systems/defensiveSys/` | Config file only (`dsConfig.xml`) — no implementation |
| Sensor Management | `Systems/sensorManagement/` | Stub |
| Avionics hardware health | `Systems/avionics/hardwareHealth/` | Framework only |
| Mission Planning (full) | `Systems/missionPlanning/` | Framework + stubs; `missionControl.py` exists but subsystems (targeting, OOB) are minimal |

---

## 15. Next Steps (Recommended Priority Order)

### Immediate (Bug fixes)

1. **Clean up debug logging** — downgrade `[VIL_FLOW_DEBUG]` and `[PRECIPITATION_FLOW_DEBUG]` `logger.error()` calls to `logger.debug()` in `vil_data_handler.py` and `precipitation_data_handler.py`
2. **Weather radar 1553B data path** — resolve the remaining 1553B comms issue so VIL/precipitation data flows through the full protocol chain (bridge is workaround, not final solution)
3. **CLI status request** — implement the `TODO` in `userCLI.py:142`

### Short-term (Feature completion)

4. **Storm cell display integration** — wire `StormCellTracker` output through `radar_to_display_bridge.push_cells_data` → coordinator `cells` store → weather display overlay
5. **Wind shear + turbulence display overlays** — `WindShearProcessor` and `TurbulenceProcessor` are implemented but not yet connected to any display layer
6. **Defensive systems implementation** — flesh out `Systems/defensiveSys/` (RWR, countermeasures, jamming)
7. **Sensor management** — implement `Systems/sensorManagement/`

### Medium-term

8. **Cross-radar display integration** — connect `RadarDataFusion` output to TSD more completely; add fusion-level alerts to EICAS
9. **Mission planning completion** — route management UI in MFD, order of battle display, targeting integration
10. **Performance optimisation** — spatial partitioning is implemented in the rendering engine but not yet profiled at 60 Hz under full load; validate CPU targets (<40% per radar, <10 ms message latency)
11. **Linux / macOS support** — replace Windows-specific PyQt6 wheels with cross-platform pip install path in installer

### Long-term

12. **Hardware interface** — optional real MIL-STD-1553B hardware adapter integration (already architected in `MIL_STD_1553B/`)
13. **Automated CI** — wire test suite into a GitHub Actions workflow
14. **Scenario engine** — flesh out `Interfaces/scenarios/` (training and failure scenarios defined in XML but not yet executed by a runtime engine)

---

## 16. Performance Targets

| Metric | Target | Notes |
|--------|--------|-------|
| Display refresh | 60 Hz | PFD (20 Hz actual), MFD (10 Hz actual) — gap to close |
| Message latency | < 10 ms | Async handler with 4 workers |
| CPU per radar | < 40% | Not yet profiled at scale |
| Memory per radar | < 256 MB | Not yet profiled |
| Database workers | ≤ 20 total | Enforced by `dbConfig.xml` |
| Radar query rate | 200 / 120 s | High-performance config |
| Display query rate | 200 / 60 s | Real-time config |
| Rate limiting | 10 req/s | AsyncMessageHandler |

---

## 17. Daily Progress Log

### 2025-02-03
- Created consolidated working notes
- Analysed existing implementations
- Designed integration strategy
- Planned implementation phases

### 2025-02-08
- VIL implementation: `vil_data_handler.py`, `vil_response_service.py`, `WeatherRadarVILData` class
- Identified VIL database transaction issues (raw SQL, double storage, improper queue completion)
- Designed fix plan: use DBM `create_table`, fix queue completion, add timeout handling

### 2025-02-08 → (subsequent commits, reconstructed from git log)

| Commit | Change |
|--------|--------|
| `7dc02ee` | Initial commit |
| `04a39c1` | Enhanced VILResponseService + Radar-to-Display Bridge introduced |
| `ec2b86f` | GPS and Storm Cell Tracking refactor |
| `79b4b99` | FMS and Radar completion message handler refactor |
| `62c26b3` | Cross-radar data fusion layer (`RadarDataFusion`) |
| `a089dcc` | SAR, Targeting, TFR, Weather radar processors implemented |
| `49d0f02` | Comprehensive test suites: bridge, display, installer |
| `6abf254` | Operational status enhancements, radar/FMS feature improvements |
| `c8dd198` | Stores Management System (SMS) display added |
| `c366b23` | EICAS and TSD display modules added |
| `67121d6` | Automated installer (`install.py`) |
| `93b0b8a` | Radar management refactor for data handling and display integration |
| `c23751c` | User manual updated to reflect operational radar status |

---

*Document generated by full codebase audit — June 2026*
