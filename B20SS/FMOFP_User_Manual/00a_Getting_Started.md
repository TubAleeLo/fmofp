# Getting Started Guide

**Navigation:** [← Table of Contents](00_Title_and_TOC.md) | [Legal Information →](00b_Legal_Information.md)

---

## Quick Start Guide for New Interns

### Welcome to FMOFP

The Flight Management Operating Flight Program (FMOFP) is a comprehensive avionics system designed for advanced military aircraft operations. This guide will help you get started with the system quickly and understand the essential operations needed for effective use.

**Before You Begin:**
- Ensure Python 3.9+ is installed
- Verify PyQt6 dependencies are available
- Have access to the FMOFP system files
- Review the system status indicators used throughout this manual

---

## Essential Interface Overview

### System Startup Visual Guide

[SCREENSHOT PLACEHOLDER: FMOFP Main.py startup screen showing console output]
**Figure 1:** FMOFP System Startup Screen
1. Python console initialization output
2. System component loading messages
3. Database initialization status
4. Component status indicators
5. Ready for operations message

**What to Look For:**
- All components should initialize without errors
- Database connections should establish successfully
- Radar systems should reach STANDBY mode
- Display systems should become responsive

### Main System Interface Components

[SCREENSHOT PLACEHOLDER: Main system interface with numbered callouts]
**Figure 2:** Main System Interface Layout
1. **Radar Control Panel** - Access to all radar systems
2. **Display Selection Area** - Choose between PFD, MFD, Holographic displays
3. **System Status Indicators** - Real-time system health monitoring
4. **Mode Change Controls** - Operational mode selection
5. **Flight Management Integration** - FMS data and controls
6. **Communication Status** - 1553B bus health and message flow
7. **Log Output Window** - Real-time system messages and diagnostics

### Key System Components for Interns

**Radar Systems (RT Address 9):**
- **Weather Radar** (Subaddress 1) - Meteorological detection ✅ **OPERATIONAL**
- **Targeting Radar** (Subaddress 4) - Target tracking ✅ **OPERATIONAL**
- **SAR Radar** (Subaddress 3) - Ground mapping ⚠️ **BASIC SIMULATION**
- **TFR Radar** (Subaddress 2) - Terrain following ⚠️ **BASIC SIMULATION**
- **AEWC Radar** (Subaddress 5) - Surveillance ⚠️ **BASIC SIMULATION**

**Display Systems (RT Address 11):**
- **Primary Flight Display** (Subaddress 11) - Flight instruments ✅ **OPERATIONAL**
- **Multi-Function Display** (Subaddress 12) - System integration ✅ **OPERATIONAL**
- **Radar Display** (Subaddress 14) - Radar data visualization ✅ **OPERATIONAL**

---

## First-Time User Checklist

### Pre-Startup Verification

**System Requirements Check:**
- [ ] **Python Version:** Verify Python 3.9 or later is installed
  ```
  python --version
  ```
- [ ] **PyQt6 Installation:** Confirm GUI framework is available
  ```
  python -c "import PyQt6; print('PyQt6 available')"
  ```
- [ ] **System Files:** Verify FMOFP directory structure is complete
- [ ] **Database Access:** Ensure database files are accessible
- [ ] **Configuration Files:** Check XML configuration files are present

### Initial System Startup

**Step 1: Launch FMOFP System**
```
cd FMOFP
python Main.py
```

**Step 2: Monitor Initialization Sequence**
Watch for these key messages in the startup output:
```
[SYSTEM] Initializing FMOFP System Manager...
[DATABASE] Loading database configurations...
[1553B] Initializing MIL-STD-1553B communication...
[RADAR] Initializing radar management system...
[DISPLAY] Initializing display management system...
[FMS] Initializing flight management system...
[SYSTEM] All systems operational - Ready for operations
```

**Step 3: Verify System Health**
- [ ] **No Critical Errors:** Check that no ERROR messages appear during startup
- [ ] **Radar Systems:** All radar systems should show STANDBY mode
- [ ] **Display Systems:** PFD should display flight parameters
- [ ] **Communication:** 1553B bus should show active status
- [ ] **Database:** All database connections should be established

### Post-Startup Verification

**Basic Functionality Test:**
1. **Test Radar Mode Change:**
   - Access Weather Radar controls
   - Change from STANDBY to SURVEILLANCE mode
   - Monitor logs for successful mode change
   - Verify data generation begins

2. **Test Display Responsiveness:**
   - Open Primary Flight Display (PFD)
   - Verify real-time flight data updates
   - Check attitude indicator movement
   - Confirm tactical indicators are active

3. **Test System Integration:**
   - Monitor FMS data flow to displays
   - Verify 1553B message traffic
   - Check system health indicators
   - Confirm no communication errors

---

## Basic Operation Tutorial

### Understanding System Status Indicators

Throughout the FMOFP system, you'll see these status indicators:

- ✅ **OPERATIONAL:** Feature is fully functional and ready for use
- ⚠️ **IN DEVELOPMENT:** Feature works but may have limitations
- ✅ **OPERATIONAL:** Feature is fully implemented and tested
- ❌ **NOT IMPLEMENTED:** Feature is planned but not yet available
- 🐛 **KNOWN ISSUES:** Feature works but has documented problems

### Essential Operations for Interns

#### 1. Radar System Operations

**Accessing Radar Controls:**
[SCREENSHOT PLACEHOLDER: Radar control interface]
**Figure 3:** Radar Control Interface
1. System selection dropdown
2. Current mode indicator
3. Available modes list
4. Mode change button
5. Status display area

**Basic Radar Mode Change Procedure:**
1. **Select Radar System**
   - Choose from Weather, Targeting, SAR, TFR, or AEWC
   - Verify system is in STANDBY mode

2. **Change Operational Mode**
   - Select desired mode from dropdown
   - Click "Change Mode" button
   - Monitor status messages

3. **Verify Mode Change**
   - Check mode indicator updates
   - Monitor log output for confirmation
   - Verify data generation begins

#### 2. Display System Operations

**Primary Flight Display (PFD) Basics:**
[SCREENSHOT PLACEHOLDER: PFD with labeled elements]
**Figure 4:** Primary Flight Display Elements
1. Attitude indicator (artificial horizon)
2. Airspeed tape (left side)
3. Altitude tape (right side)
4. Heading indicator (top)
5. Flight mode indicator (bottom)
6. G-force and AOA indicators

**Multi-Function Display (MFD) Basics:**
[SCREENSHOT PLACEHOLDER: MFD interface]
**Figure 5:** Multi-Function Display Interface
1. Radar data display area
2. System status monitoring
3. Navigation information
4. Control buttons and menus
5. Theme selection options

#### 3. System Monitoring

**Key Areas to Monitor:**
- **System Logs:** Real-time messages about system operations
- **Communication Status:** 1553B bus health and message flow
- **Radar Processing:** Data generation and mode changes
- **Display Updates:** Real-time flight data integration
- **Error Messages:** Any system warnings or failures

### Common Intern Tasks

#### Task 1: Verify Weather Radar Operation
1. Start FMOFP system
2. Access Weather Radar controls
3. Change from STANDBY to SURVEILLANCE mode
4. Monitor logs for data generation messages
5. Note: Data won't appear on displays due to known 1553B issue

#### Task 2: Test Display System Themes
1. Open Primary Flight Display
2. Access display configuration
3. Switch between Classic and Modern themes
4. Observe visual effect changes
5. Verify all elements remain functional

#### Task 3: Monitor System Health
1. Check system status indicators
2. Review log output for errors
3. Verify database connections
4. Monitor 1553B communication status
5. Report any anomalies to development team

---

## Understanding Current System Limitations

### Known Issues for Interns

**Weather Radar Display Integration 🐛 KNOWN ISSUES:**
- Weather radar processing works correctly
- VIL and precipitation data generation is operational
- **Issue:** 1553B communication prevents data from reaching displays
- **What You'll See:** Mode changes work, but no weather data on displays
- **Monitoring:** Use system logs to verify radar is processing data

**Other Radar Systems ✅ OPERATIONAL:**
- All radar systems (Targeting, SAR, TFR, AEWC) process data correctly
- **Issue:** Display integration not yet implemented
- **What You'll See:** Mode changes work, data processing occurs
- **Monitoring:** Check logs for data generation confirmation

**Display System Integration:**
- Display rendering works perfectly
- Flight Management System data integration is operational
- **Limitation:** Only FMS data appears on displays, not radar data
- **What You'll See:** PFD shows flight data, MFD shows system status

### Working Around Limitations

**For Radar Testing:**
1. Use system logs to verify radar operations
2. Monitor mode change confirmations
3. Check data generation messages
4. Verify system health indicators

**For Display Testing:**
1. Focus on FMS data integration
2. Test theme changes and visual effects
3. Verify display responsiveness
4. Check tactical indicators (G-force, AOA)

**For System Integration:**
1. Monitor 1553B communication status
2. Verify message routing (even if data doesn't display)
3. Test system startup and shutdown procedures
4. Check database operations

---

## Getting Help

### Documentation Resources
- **System Overview:** File 01 - Complete system architecture
- **Radar Systems:** Files 02-06 - Detailed radar documentation
- **Display Systems:** Files 07-09 - Display system operations
- **Troubleshooting:** File 13 - Problem resolution procedures

### Log Monitoring
**Essential Log Commands:**
```bash
# Monitor all system activity
tail -f FMOFP/logs/DEBUG_*.log

# Monitor weather radar specifically
tail -f FMOFP/logs/DEBUG_*.log | grep WEATHER

# Monitor communication messages
tail -f FMOFP/logs/DEBUG_*.log | grep 1553B
```

### Common Questions for Interns

**Q: Why don't I see radar data on displays?**
A: This is a known issue with 1553B communication. The radar systems are working correctly, but data isn't reaching the displays. Monitor the logs to verify radar operation.

**Q: How do I know if a mode change worked?**
A: Check the mode indicator in the interface and monitor the log output for confirmation messages. You should see processing begin even if data doesn't display.

**Q: What should I do if the system won't start?**
A: Check Python and PyQt6 installation, verify file permissions, and review the startup logs for specific error messages.

---

**Navigation:** [← Table of Contents](00_Title_and_TOC.md) | [Legal Information →](00b_Legal_Information.md)

**Related Files:**
- → [System Overview](01_System_Overview.md) - Complete system architecture
- → [Operational Procedures](12_Operational_Procedures.md) - Detailed operational guidance
- → [System Maintenance](13_System_Maintenance.md) - Troubleshooting and diagnostics

---

*File: 00a_Getting_Started.md*
*Last Updated: June 13 2025*
