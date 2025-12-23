# Wiring Guide

Complete wiring instructions for the Auto SLUCSE stepper motor controller.

## 📋 Components

| Component | Model/Specs |
|-----------|-------------|
| Microcontroller | NodeMCU v2 (ESP8266) |
| Stepper Driver | A4988 (HiLetgo or similar) |
| Stepper Motor | NEMA 17 (42HS40-005B or similar, 200 steps/rev) |
| Display | SSD1306 128x64 OLED (I2C) |
| Power Supply | 12V DC, 2A+ recommended |

---

## 🔌 Connection Tables

### NodeMCU → A4988 Stepper Driver

| NodeMCU Pin | GPIO | A4988 Pin | Notes |
|-------------|------|-----------|-------|
| D5 | GPIO14 | STEP | Step pulse input |
| D6 | GPIO12 | DIR | Direction control |
| 3.3V | - | VDD | Logic power (3.3-5V) |
| GND | - | GND | Common ground |

### A4988 Internal Connections

| A4988 Pin | Connect To | Notes |
|-----------|------------|-------|
| RST | SLP | Jumper these together |
| SLP | RST + VDD | Keeps driver enabled |
| MS1 | (floating) | Full-step mode |
| MS2 | (floating) | Full-step mode |
| MS3 | (floating) | Full-step mode |

### A4988 → Motor & Power

| A4988 Pin | Connect To | Notes |
|-----------|------------|-------|
| VMOT | +12V | Motor power (8-35V) |
| GND | -12V (GND) | Motor power ground |
| 1A | Motor Coil A+ | Black wire (typically) |
| 1B | Motor Coil A- | Green wire (typically) |
| 2A | Motor Coil B+ | Red wire (typically) |
| 2B | Motor Coil B- | Blue wire (typically) |

> ⚠️ **Motor wire colors vary by manufacturer!** If motor vibrates but doesn't rotate, swap one coil pair (e.g., swap 1A and 1B).

### NodeMCU → SSD1306 Display

| NodeMCU Pin | GPIO | SSD1306 Pin | Notes |
|-------------|------|-------------|-------|
| D1 | GPIO5 | SCL | I2C Clock |
| D2 | GPIO4 | SDA | I2C Data |
| 3.3V | - | VCC | Display power |
| GND | - | GND | Common ground |

---

## 🔘 Speed Button (Momentary)

The firmware supports a **momentary pushbutton** that cycles motor speed:
`1 → 2 → 3 → 4 → 5 → 1 ...` revolutions per second (RPS).

Wire it like this (no extra resistors needed):

| NodeMCU Pin | GPIO | Button Pin | Notes |
|-------------|------|------------|-------|
| D7 | GPIO13 | One side | Configured as `INPUT_PULLUP` |
| GND | - | Other side | Button shorts D7 to GND when pressed |

---

## ⚡ Power Options

### Option 1: Single 12V Supply (Recommended)

Use one 12V power supply for everything (recommended wiring):

```
┌─────────────────┐
│   12V SUPPLY    │
├─────────────────┤
│                 │
│  +12V ──────────┼──────┬──────────► A4988 VMOT
│                 │      │
│                 │      └──────────► 7805 IN
│                 │
│  GND ───────────┼──────┬──────────► A4988 GND
│                 │      │
│                 │      ├──────────► 7805 GND
│                 │      ├──────────► NodeMCU GND
│                 │      │
│                 │      └──────────► SSD1306 GND
└─────────────────┘

7805 OUT (+5V) ─────────────────────► NodeMCU VIN (5V input)

NodeMCU 3.3V ───────────────────────► A4988 VDD (logic)
NodeMCU 3.3V ───────────────────────► SSD1306 VCC
```

Notes:
- This setup avoids feeding 12V directly into the NodeMCU.
- **Common ground is mandatory:** 12V GND, 7805 GND, NodeMCU GND, and A4988 GND/VMOT GND must all be tied together.
- Add a **100–470µF (25V+) electrolytic** across **A4988 VMOT↔GND** close to the driver to reduce spikes/resets.

### Option 2: Dual Power Supplies

If you have separate 5V and 12V supplies:

```
┌─────────────────┐
│   12V SUPPLY    │
├─────────────────┤
│  +12V ──────────┼──────────────────► A4988 VMOT
│  GND ───────────┼──────┬───────────► A4988 GND
└─────────────────┘      │
                         │ (COMMON GROUND - CRITICAL!)
┌─────────────────┐      │
│    5V SUPPLY    │      │
├─────────────────┤      │
│  +5V ───────────┼──────────────────► NodeMCU VIN (or USB)
│  GND ───────────┼──────┴───────────► NodeMCU GND
└─────────────────┘
```

> ⚠️ **CRITICAL:** The grounds MUST be connected together! Without common ground, the STEP/DIR signals won't work.

---

## 📊 Complete Wiring Diagram

```
                                    ┌─────────────────────────────────────┐
                                    │            A4988 DRIVER             │
                                    │                                     │
     ┌──────────────────────────────┤ VMOT                                │
     │                              │                                     │
     │   ┌──────────────────────────┤ GND                            1A ├───► Motor Coil A+
     │   │                          │                                     │
     │   │   ┌──────────────────────┤ VDD                            1B ├───► Motor Coil A-
     │   │   │                      │                                     │
     │   │   │                      │ RST ◄────┐                     2A ├───► Motor Coil B+
     │   │   │                      │          │ (jumper)                 │
     │   │   │                      │ SLP ◄────┴──► 3.3V             2B ├───► Motor Coil B-
     │   │   │                      │                                     │
     │   │   │   ┌──────────────────┤ STEP                               │
     │   │   │   │                  │                                     │
     │   │   │   │   ┌──────────────┤ DIR                                │
     │   │   │   │   │              │                                     │
     │   │   │   │   │              │ MS1  (floating = full step)        │
     │   │   │   │   │              │ MS2  (floating = full step)        │
     │   │   │   │   │              │ MS3  (floating = full step)        │
     │   │   │   │   │              │                                     │
     │   │   │   │   │              │ EN   (floating = enabled)          │
     │   │   │   │   │              └─────────────────────────────────────┘
     │   │   │   │   │
     │   │   │   │   │              ┌─────────────────────────────────────┐
     │   │   │   │   │              │            NodeMCU v2               │
     │   │   │   │   │              │                                     │
     │   │   │   │   └──────────────┤ D6 (GPIO12)                        │
     │   │   │   │                  │                                     │
     │   │   │   └──────────────────┤ D5 (GPIO14)                        │
     │   │   │                      │                                     │
     │   │   └──────────────────────┤ 3.3V ──────────┬───────────────────┼───► SSD1306 VCC
     │   │                          │                │                   │
     │   └──────────────────────────┤ GND ───────────┼───────────────────┼───► SSD1306 GND
     │                              │                │                   │
     └──────────────────────────────┤ VIN            │                   │
                                    │                │                   │
                                    │ D1 (GPIO5) ────┼───────────────────┼───► SSD1306 SCL
                                    │                │                   │
                                    │ D2 (GPIO4) ────┼───────────────────┼───► SSD1306 SDA
                                    │                │                   │
                                    └────────────────┼───────────────────┘
                                                     │
                                    ┌─────────────────────────────────────┐
                                    │         7805 REGULATOR MODULE       │
                                    │                                     │
                                    │ IN  ◄────────── +12V                │
                                    │ GND ◄────────── 12V GND (common)    │
                                    │ OUT ───────────► +5V to NodeMCU VIN │
                                    └─────────────────────────────────────┘

┌─────────────────┐
│   12V SUPPLY    │
├─────────────────┤
│  +12V ──────────┼──► A4988 VMOT and 7805 IN
│  GND ───────────┼──► all GND points (common ground)
└─────────────────┘

Add near A4988: 100–470uF electrolytic across VMOT↔GND (25V+)
```

---

## 🔍 Motor Coil Identification

### Finding Coil Pairs

Use a multimeter in continuity/resistance mode:
1. Touch two wires together
2. If you get ~5Ω (low resistance), they're a coil pair
3. The other two wires are the second coil pair

### Typical NEMA 17 Wire Colors

| Coil | Wire 1 | Wire 2 |
|------|--------|--------|
| A | Black | Green |
| B | Red | Blue |

> **Note:** Colors vary! Always verify with a multimeter.

### If Motor Vibrates But Doesn't Rotate

The coil pairs are probably wired incorrectly. Try:
1. Swap wires on 1A and 1B, OR
2. Swap wires on 2A and 2B

---

## ✅ Verification Checklist

Before powering on:

- [ ] 12V connected to VMOT (not VDD!)
- [ ] NodeMCU powered from +5V into VIN (e.g., via 7805/buck), not directly from 12V
- [ ] VDD connected to 3.3V (not 12V!)
- [ ] All GND points connected together
- [ ] VMOT electrolytic capacitor installed near the A4988 (100–470µF, 25V+)
- [ ] RST and SLP jumpered together
- [ ] RST/SLP jumper connected to 3.3V
- [ ] Motor coils verified with multimeter
- [ ] Display I2C connections (D1=SCL, D2=SDA)

---

## 🐛 Troubleshooting

| Symptom | Likely Cause | Solution |
|---------|--------------|----------|
| Motor doesn't move | No common ground | Connect all GNDs together |
| Motor vibrates chaotically | Wrong coil wiring | Swap one coil pair |
| Motor very weak | Low VMOT voltage | Ensure 12V at VMOT |
| Motor gets very hot | Current limit too high | Adjust A4988 potentiometer |
| Display blank | Wrong I2C address | Try 0x3D instead of 0x3C |
| Display shows garbage | SDA/SCL swapped | Swap D1 and D2 connections |
| A4988 gets hot | No heatsink | Add heatsink to A4988 |

---

## 📏 A4988 Current Limiting

The A4988 has a small potentiometer for current limiting. To set it:

1. Measure voltage at the potentiometer center (Vref)
2. Calculate: `I_max = Vref / (8 × Rs)` where Rs is the sense resistor (usually 0.1Ω)
3. For Rs = 0.1Ω: `I_max = Vref × 1.25`

For NEMA 17 motors, Vref of ~0.4-0.8V is typical (0.5-1A per phase).

> ⚠️ Start LOW and increase gradually. Too much current = overheating!
