#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

// Display setup - I2C on D1(SCL) and D2(SDA)
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_RESET -1
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

const int DIR = 12;   // D6
const int STEP = 14;  // D5
const int STEPS_PER_REV = 200;
const int NUM_ROTATIONS = 5;
const int TOTAL_STEPS = STEPS_PER_REV * NUM_ROTATIONS;  // 1000 steps

// Pre-computed ease-in-out delays in microseconds for 5 rotations
// Using 2 seconds total = 2,000,000us / 1000 steps = 2000us average
uint16_t easeDelays[TOTAL_STEPS];

// Progress bar dimensions
const int BAR_X = 4;
const int BAR_Y = 40;
const int BAR_WIDTH = 120;
const int BAR_HEIGHT = 16;

void drawProgressBar(int current, int total) {
  int fillWidth = (current * BAR_WIDTH) / total;
  
  // Draw border
  display.drawRect(BAR_X, BAR_Y, BAR_WIDTH, BAR_HEIGHT, SSD1306_WHITE);
  // Fill progress
  if (fillWidth > 4) {
    display.fillRect(BAR_X + 2, BAR_Y + 2, fillWidth - 4, BAR_HEIGHT - 4, SSD1306_WHITE);
  }
}

void updateDisplay(const char* direction, int currentRot, int totalRot, int percent) {
  display.clearDisplay();
  
  // Title
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.println("STEPPER CONTROL");
  
  // Direction with larger text
  display.setTextSize(2);
  display.setCursor(0, 14);
  display.println(direction);
  
  // Progress bar (based on percent 0-100)
  drawProgressBar(percent, 100);
  
  // Stats at bottom - rotation count
  display.setTextSize(1);
  display.setCursor(0, 58);
  display.print("Rotation ");
  display.print(currentRot);
  display.print("/");
  display.print(totalRot);
  display.print("  ");
  display.print(percent);
  display.print("%");
  
  display.display();
}

void computeEaseDelays() {
  // Pre-compute all 1000 delays for ultra-smooth motion
  // Using sine-based ease-in-out for smoothest acceleration
  // Target: 2 seconds total = 2,000,000us
  
  for (int i = 0; i < TOTAL_STEPS; i++) {
    float t = (float)i / (float)(TOTAL_STEPS - 1);  // 0.0 to 1.0
    
    // Sine-based ease-in-out: smoothest possible curve
    // speed = sin(pi * t) - peaks at 1.0 at t=0.5, zero at ends
    float speed = sin(PI * t);
    if (speed < 0.08f) speed = 0.08f;  // Clamp minimum to prevent stalling
    
    // Map speed to delay: slow=4000us at ends, fast=1200us in middle
    // Average ~2000us = 2ms per step, 1000 steps = 2 seconds
    int delayUs = (int)(1200.0f / speed);
    if (delayUs < 1200) delayUs = 1200;
    if (delayUs > 15000) delayUs = 15000;
    
    easeDelays[i] = delayUs;
  }
}

void stepMultipleRotations(bool clockwise, const char* label) {
  digitalWrite(DIR, clockwise ? HIGH : LOW);
  delay(50);  // Direction settle
  
  // Show initial display
  updateDisplay(label, 1, NUM_ROTATIONS, 0);
  
  int lastRotation = 0;
  int lastPercent = -1;
  
  for (int i = 0; i < TOTAL_STEPS; i++) {
    // Calculate current rotation and percentage
    int currentRotation = (i / STEPS_PER_REV) + 1;
    int percent = (i * 100) / TOTAL_STEPS;
    
    // Update display ONLY between rotations (when motor briefly pauses anyway)
    // This keeps the motion ultra-smooth
    if (currentRotation != lastRotation) {
      updateDisplay(label, currentRotation, NUM_ROTATIONS, percent);
      lastRotation = currentRotation;
    }
    
    // Step the motor - uninterrupted smooth motion
    digitalWrite(STEP, HIGH);
    delayMicroseconds(10);
    digitalWrite(STEP, LOW);
    delayMicroseconds(easeDelays[i]);
  }
  
  // Final update at 100%
  updateDisplay(label, NUM_ROTATIONS, NUM_ROTATIONS, 100);
}

void showPause(int seconds) {
  for (int i = seconds; i > 0; i--) {
    display.clearDisplay();
    display.setTextSize(1);
    display.setTextColor(SSD1306_WHITE);
    display.setCursor(0, 0);
    display.println("STEPPER CONTROL");
    display.setTextSize(2);
    display.setCursor(0, 20);
    display.println("PAUSE");
    display.setTextSize(3);
    display.setCursor(50, 40);
    display.print(i);
    display.display();
    delay(1000);
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(STEP, OUTPUT);
  pinMode(DIR, OUTPUT);
  
  // Initialize I2C for display
  Wire.begin();
  
  // Initialize display
  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println("SSD1306 allocation failed");
  }
  
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.println("STEPPER CONTROL");
  display.setTextSize(2);
  display.setCursor(0, 20);
  display.println("5 x ROT");
  display.setCursor(0, 40);
  display.println("2 sec ea");
  display.display();
  
  // Pre-compute smooth ease curve
  computeEaseDelays();
  delay(2000);
}

void loop() {
  Serial.println("Clockwise 5 rotations...");
  stepMultipleRotations(true, "CLOCKWISE");
  
  showPause(2);
  
  Serial.println("Counter-Clockwise 5 rotations...");
  stepMultipleRotations(false, "C-CLOCKWISE");
  
  showPause(2);
}
