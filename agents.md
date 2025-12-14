# AI Agent Instructions for Auto SLUCSE

This document provides context and guidelines for AI agents working on this project.

## Project Overview

**Auto SLUCSE** is a stepper motor controller for NodeMCU v2 (ESP8266) with:
- A4988 stepper driver
- NEMA 17 motor (42HS40-005B, 200 steps/rev)
- SSD1306 OLED display (128x64, I2C)

## Current Behavior

The motor performs **6 rotations** in each direction with:
- **Sine-based easing**: Smooth acceleration and deceleration
- **Peak speed**: 1200µs delay (optimal for this motor)
- **2-second pause** between direction changes
- **Bidirectional**: Clockwise then counter-clockwise, repeating

## Critical Technical Details

### ⚠️ CRITICAL: Direction Control - DO NOT CHANGE
The bidirectional motion is controlled by this exact logic:
```cpp
digitalWrite(DIR, clockwise ? HIGH : LOW);
```
- `HIGH` = Clockwise
- `LOW` = Counter-clockwise

**NEVER modify this logic.** If motor only goes one direction, the problem is elsewhere (wiring, timing, etc.), NOT the direction logic.

### GPIO Mapping (NodeMCU v2)
| Label | GPIO | Function |
|-------|------|----------|
| D5 | GPIO14 | STEP signal |
| D6 | GPIO12 | DIR signal |
| D1 | GPIO5 | I2C SCL |
| D2 | GPIO4 | I2C SDA |

### Timing Requirements
- **Pulse width**: 10µs HIGH minimum for A4988
- **Direction settle**: 50ms after changing DIR pin
- **Step delays**: Pre-computed array of 1200 values (6 rot × 200 steps)
- **Min delay**: 1200µs (peak speed)
- **Max delay**: 15000µs (start/end speed)

### ⚠️ CRITICAL: Display Constraints
- **NEVER update display during motor stepping** - I2C communication causes motor jitter/stutter
- Update display ONLY at: startup, BEFORE motion starts, AFTER motion ends, during pause
- The stepping loop must contain ONLY: digitalWrite and delayMicroseconds calls

## Easing Function

```cpp
// Sine-based ease-in-out for smoothest motion
float speed = sin(PI * t);  // t from 0.0 to 1.0
if (speed < 0.08f) speed = 0.08f;  // Prevent stalling at ends
```

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
3. **Pre-compute everything** - No floating-point math during stepping
4. **Peak speed is optimal** - 1200µs works well, don't reduce further
5. **NEVER change direction logic** - `digitalWrite(DIR, clockwise ? HIGH : LOW)` is correct
6. **NEVER update display during stepping** - Causes motor jitter
