# AI Agent Instructions for Auto SLUCSE

This document provides context and guidelines for AI agents working on this project.

## Project Overview

**Auto SLUCSE** is a stepper motor controller for NodeMCU v2 (ESP8266) with:
- A4988 stepper driver
- NEMA 17 motor (42HS40-005B, 200 steps/rev)
- SSD1306 OLED display (128x64, I2C)

## Current Behavior

The motor runs **continuously clockwise** with:
- **Constant speed**: No acceleration/deceleration
- **Selectable speed**: 1–5 revolutions per second (RPS)
- **Button-controlled**: a momentary button cycles speed `1 → 2 → 3 → 4 → 5 → 1 ...`
- **OLED display** shows the current RPS (and must not be updated inside the stepping loop)

## Critical Technical Details

### ⚠️ CRITICAL: Direction Control - DO NOT CHANGE
The bidirectional motion is controlled by this exact logic:
```cpp
digitalWrite(DIR, clockwise ? HIGH : LOW);
```
- `HIGH` = Clockwise
- `LOW` = Counter-clockwise

**NEVER modify this logic.** This is the *entire* mechanism that makes reverse work.

Why reverse is so important (and how it works here):
- The firmware intentionally runs two phases forever: clockwise (7.5 rotations) then counter-clockwise (7.5 rotations).
- Each phase calls `stepMultipleRotations(true/false, ...)`.
- Inside `stepMultipleRotations()`, direction is set exactly once per phase via `digitalWrite(DIR, clockwise ? HIGH : LOW);`, then a 50ms settle delay is applied.

If it ever “looks like it only goes one direction”, do **not** change the DIR line. Common real causes:
- ESP8266 watchdog resets during a long tight stepping loop (restarts the program so it keeps re-entering the same phase)
- Wiring/coil pairing or driver wiring issues
- Power/VMOT issues or driver current limit

### GPIO Mapping (NodeMCU v2)
| Label | GPIO | Function |
|-------|------|----------|
| D5 | GPIO14 | STEP signal |
| D6 | GPIO12 | DIR signal |
| D1 | GPIO5 | I2C SCL |
| D2 | GPIO4 | I2C SDA |
| D7 | GPIO13 | Speed button (momentary to GND, INPUT_PULLUP) |

### Timing Requirements
- **Pulse width**: 10µs HIGH minimum for A4988
- **Direction settle**: 50ms after changing DIR pin
- **Speed control**: Achieved by changing the time between step pulses (1–5 RPS)

### ⚠️ CRITICAL: Display Constraints
- **NEVER update display during motor stepping** - I2C communication causes motor jitter/stutter
- Update display ONLY at: startup, BEFORE motion starts, AFTER motion ends, during pause
- The stepping loop must NOT call any OLED/I2C code.
- On ESP8266, a long tight stepping loop may require an occasional `yield()`/`delay(0)` to avoid watchdog resets (which can look like it "never reverses").

What we changed (the fix):
- Removed all OLED/progress updates from inside the stepping loop.
- Added a lightweight periodic `yield()` inside the stepping loop to keep ESP8266 background/WDT serviced.
- OLED now only shows simple status when not actively stepping (boot, and after a speed change).

## Common Issues & Solutions

| Issue | Cause | Fix |
|-------|-------|-----|
| Motor vibrates, won't turn | Wrong coil pairing | Swap one coil pair (A+/A- or B+/B-) |
| Motor only goes ONE direction | **DO NOT change direction logic** | Check wiring, timing, power - direction code is correct |
| Jerky/stuttering motion | Display updates during stepping | **NEVER** update display in stepping loop |
| Motor stalls at low speed | Delay too long | Decrease max delay or increase speed floor |

## Build Commands

```powershell
pio run              # Build
pio run -t upload    # Upload to NodeMCU
pio device monitor   # Serial monitor (115200 baud)
```

## File Structure

```
src/main.cpp      - Main application (all logic in one file)
platformio.ini    - PlatformIO config (ESP8266, Adafruit libs)
README.md         - User documentation
WIRING.md         - Detailed wiring guide
agents.md         - This file (AI agent context)
```

## Change Guidelines

1. **Motor timing is sensitive** - Test any delay changes carefully
2. **Keep display simple** - Complex animations cause motor issues
3. **Avoid extra work during stepping** - Keep the stepping loop lean (no I2C)
4. **Speed is sensitive** - Don’t reduce `STEP_DELAY_US` too far; tune carefully
5. **NEVER change direction logic** - `digitalWrite(DIR, clockwise ? HIGH : LOW)` is correct
6. **NEVER update display during stepping** - Causes motor jitter

## Workflow Rules (No Exceptions)

These are process requirements for this repo:

### DO
1. Update `agents.md` and `README.md` for *every* behavioral change (even “small” changes).
2. Keep docs aligned with the actual firmware behavior (especially display timing and reverse behavior).
3. Always attempt a firmware upload when finished (`pio run -t upload`) so changes are validated on the microcontroller.
4. Commit changes on the existing branch and push to `origin/main` (this repo uses `main` as the working branch).

### DON'T
1. Don’t change the DIR control line or swap HIGH/LOW meanings.
2. Don’t add OLED/I2C calls inside the stepping loop.
3. Don’t “fix” one-direction symptoms by changing direction logic—find the real cause (WDT, wiring, power, timing).
