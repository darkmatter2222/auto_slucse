# Auto SLUCSE - Stepper Motor Controller

A smooth, precision stepper motor controller using **NodeMCU v2 (ESP8266)** with an **A4988 driver** and **SSD1306 OLED display**.

![Platform](https://img.shields.io/badge/Platform-ESP8266-blue)
![Framework](https://img.shields.io/badge/Framework-Arduino-green)
![License](https://img.shields.io/badge/License-MIT-yellow)

## ✨ Features

- **Ultra-smooth motion** with sine-based ease-in-out acceleration
- **6 continuous rotations** in each direction
- **Simple OLED display** showing direction and status
- **No display updates during motion** - prevents motor jitter
- **Pre-computed timing** for jitter-free operation
- **12V single power supply** option (NodeMCU can run from 12V via VIN)

## 🎬 Demo

The motor performs:
1. **6 rotations clockwise** with smooth ease-in-out (starts slow, speeds up, slows down)
2. **2 second pause**
3. **6 rotations counter-clockwise** with same smooth motion
4. **Repeat forever**

## 🔧 Hardware Required

| Component | Description |
|-----------|-------------|
| NodeMCU v2 | ESP8266-based microcontroller |
| A4988 | Stepper motor driver (or compatible) |
| NEMA 17 | Stepper motor (200 steps/rev, 1.8°) |
| SSD1306 | 128x64 OLED display (I2C, 0x3C address) |
| 12V PSU | Power supply (2A+ recommended) |

## 📌 Pin Configuration

| NodeMCU Pin | GPIO | Connected To |
|-------------|------|--------------|
| D5 | GPIO14 | A4988 STEP |
| D6 | GPIO12 | A4988 DIR |
| D1 | GPIO5 | SSD1306 SCL |
| D2 | GPIO4 | SSD1306 SDA |
| VIN | - | 12V Power (or 5V) |
| GND | - | Common Ground |

## 📐 Wiring

See **[WIRING.md](WIRING.md)** for complete wiring diagrams.

### Quick Reference
```
┌─────────────┐         ┌─────────────┐         ┌─────────────┐
│   12V PSU   │         │   NodeMCU   │         │    A4988    │
├─────────────┤         ├─────────────┤         ├─────────────┤
│ +12V ───────┼────┬────┼─► VIN       │         │             │
│             │    │    │             │         │             │
│             │    └────┼─────────────┼────────►│ VMOT        │
│             │         │             │         │             │
│ GND ────────┼────┬────┼─► GND       │         │             │
│             │    └────┼─────────────┼────────►│ GND         │
└─────────────┘         │             │         │             │
                        │ D5 (GPIO14) ┼────────►│ STEP        │
                        │ D6 (GPIO12) ┼────────►│ DIR         │
                        │ 3.3V ───────┼────────►│ VDD         │
                        │             │         │             │
                        │ D1 (SCL) ───┼──┐      │ RST ──┬── SLP│
                        │ D2 (SDA) ───┼──┤      │       └─► 3.3V│
                        └─────────────┘  │      └─────────────┘
                                         │
                        ┌─────────────┐  │
                        │   SSD1306   │  │
                        ├─────────────┤  │
                        │ SCL ◄───────┼──┤
                        │ SDA ◄───────┼──┘
                        │ VCC ◄─ 3.3V │
                        │ GND ◄─ GND  │
                        └─────────────┘
```

## 🚀 Build & Upload

### Prerequisites
- [PlatformIO](https://platformio.org/) (VS Code extension recommended)

### Commands
```powershell
# Build
pio run

# Upload to NodeMCU
pio run -t upload

# Monitor serial output
pio device monitor -b 115200
```

## ⚙️ Configuration

Edit `src/main.cpp` to customize:

```cpp
const int STEPS_PER_REV = 200;      // Motor steps per revolution
const int NUM_ROTATIONS = 6;        // Rotations per direction
```

### Timing Adjustment
The ease curve is computed in `computeEaseDelays()`. Modify these values:
- `1200` - Minimum delay (fastest speed in middle)
- `15000` - Maximum delay (slowest speed at ends)

## 🔬 Technical Details

### Ease Function
Uses **sine-based easing** for the smoothest possible acceleration:
```cpp
float speed = sin(PI * t);  // t from 0.0 to 1.0
```
This provides:
- Gradual acceleration from stop
- Peak velocity at midpoint
- Gradual deceleration to stop
- No jerky transitions

### Pre-computed Delays
All 1200 step delays (6 rotations × 200 steps) are calculated at startup and stored in an array. This eliminates floating-point math during motion for consistent timing.

### Display Updates
The display **ONLY updates before and after motion** - never during stepping. This is critical because I2C communication during stepping causes motor jitter.

## 📁 Project Structure

```
auto_slucse/
├── src/
│   └── main.cpp          # Main application code
├── platformio.ini        # PlatformIO configuration
├── README.md             # This file
├── WIRING.md             # Detailed wiring guide
└── .gitignore            # Git ignore rules
```

## 🐛 Troubleshooting

| Problem | Solution |
|---------|----------|
| Motor vibrates but doesn't rotate | Check coil wiring - swap one coil pair |
| Motor doesn't move at all | Verify common ground between PSU and NodeMCU |
| Display not found | Check I2C address (usually 0x3C or 0x3D) |
| Jerky motion | Ensure display updates are between rotations |
| Motor skips steps | Increase minimum delay or reduce speed |

## 📄 License

MIT License - feel free to use and modify!

## 🙏 Acknowledgments

- Adafruit for the excellent GFX and SSD1306 libraries
- The PlatformIO team for the build system
