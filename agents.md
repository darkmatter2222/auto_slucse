# AI Agent Instructions for Auto SLUCSE

This document provides context and guidelines for AI agents working on this project.

## Project Overview

**Auto SLUCSE** is a stepper motor controller for NodeMCU v2 (ESP8266) with:
- A4988 stepper driver
- NEMA 17 motor (42HS40-005B, 200 steps/rev)
- SSD1306 OLED display (128x64, I2C)

## Current Behavior

The motor performs **6 rotations** in each direction with:
- **Symmetric steep easing**: Quick ramp-up AND quick ramp-down (quadratic curve)
- **Peak speed**: 1500µs delay (unchanged, optimal for this motor)
- **Speed floor**: 30% minimum to prevent vibration at ends
- **2-second pause** between direction changes

## Critical Technical Details

### GPIO Mapping (NodeMCU v2)
| Label | GPIO | Function |
|-------|------|----------|
| D5 | GPIO14 | STEP signal |
| D6 | GPIO12 | DIR signal |
| D1 | GPIO5 | I2C SCL |
| D2 | GPIO4 | I2C SDA |

### Timing Requirements
- **Pulse width**: 10µs HIGH minimum for A4988
- **Step delays**: Pre-computed array of 1200 values (6 rot × 200 steps)
- **Min delay**: 1500µs (peak speed)
- **Max delay**: 5000µs (start/end speed)

### Display Constraints
- **NEVER update display during motor stepping** - I2C communication causes timing jitter
- Update display ONLY at: startup, before motion, after motion, during pause

## Easing Function

```cpp
// Symmetric quadratic ease with speed floor
if (t < 0.5f) {
  speed = t2 * t2 * 0.7f + 0.3f;  // Quick ramp-up
} else {
  speed = 1.0f - (t2 * t2 * 0.7f);  // Quick ramp-down
}
if (speed < 0.30f) speed = 0.30f;  // Floor prevents vibration
```

## Common Issues & Solutions

| Issue | Cause | Fix |
|-------|-------|-----|
| Motor vibrates, won't turn | Wrong coil pairing | Swap one coil pair (A+/A- or B+/B-) |
| Vibration at motion start/end | Easing too gradual | Use steeper quadratic curve with speed floor |
| Jerky motion during rotation | Display updates during stepping | Move display updates outside stepping loop |
| Motor stalls at low speed | Delay too long | Increase speed floor, decrease max delay |

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
4. **Peak speed is optimal** - 1500µs works well, don't reduce further
