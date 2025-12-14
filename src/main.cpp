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
const int NUM_ROTATIONS = 6;
const int TOTAL_STEPS = STEPS_PER_REV * NUM_ROTATIONS;  // 1200 steps

// Pre-computed ease-in-out delays in microseconds for 6 rotations
uint16_t easeDelays[TOTAL_STEPS];

// Simple status display - NO updates during motor motion to prevent jitter
void showStatus(const char* line1, const char* line2) {
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.println("STEPPER CONTROL");
  
  display.setTextSize(2);
  display.setCursor(0, 20);
  display.println(line1);
  
  display.setCursor(0, 42);
  display.println(line2);
  
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

void stepMultipleRotations(bool clockwise, const char* dirLabel) {
  // CRITICAL: Set direction pin - HIGH=clockwise, LOW=counter-clockwise
  // DO NOT CHANGE THIS LOGIC - it controls bidirectional motion
  digitalWrite(DIR, clockwise ? HIGH : LOW);
  delay(50);  // Direction settle time
  
  // Show status ONCE before motion starts - NO updates during stepping!
  // Display updates during stepping cause motor jitter due to I2C timing
  showStatus(dirLabel, "6 rotations");
  
  // Pure uninterrupted stepping loop - absolutely NO display calls here
  for (int i = 0; i < TOTAL_STEPS; i++) {
    digitalWrite(STEP, HIGH);
    delayMicroseconds(10);  // Pulse width
    digitalWrite(STEP, LOW);
    delayMicroseconds(easeDelays[i]);
  }
  
  // Show completion AFTER motion ends
  showStatus(dirLabel, "COMPLETE");
}

void showPause(int seconds) {
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.println("STEPPER CONTROL");
  display.setTextSize(2);
  display.setCursor(0, 25);
  display.println("PAUSED");
  display.setTextSize(1);
  display.setCursor(0, 50);
  display.print(seconds);
  display.println(" seconds...");
  display.display();
  
  delay(seconds * 1000);
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
  display.println("6 x ROT");
  display.setCursor(0, 40);
  display.println("each dir");
  display.display();
  
  // Pre-compute smooth ease curve
  computeEaseDelays();
  delay(2000);
}

void loop() {
  Serial.println("Clockwise 6 rotations...");
  stepMultipleRotations(true, "CLOCKWISE");
  
  showPause(2);
  
  Serial.println("Counter-Clockwise 6 rotations...");
  stepMultipleRotations(false, "C-CLOCKWSE");
  
  showPause(2);
}
