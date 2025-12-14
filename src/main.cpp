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

// Pre-computed ease-in-out delays in microseconds.
uint16_t easeDelays[TOTAL_STEPS];

void showStatus(const char* direction, const char* status) {
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

  display.setTextSize(2);
  display.setCursor(0, 40);
  display.println(status);
  
  display.display();
}

void computeEaseDelays() {
  // Pre-compute all delays for ultra-smooth motion.
  // Sine-based ease-in-out for smoothest acceleration.

  // Scale overall motion time (0.25 = 4x faster).
  // Note: minimum delay is still clamped to 1200us (peak speed limit).
  const float TIME_SCALE = 0.25f;
  
  for (int i = 0; i < TOTAL_STEPS; i++) {
    float t = (float)i / (float)(TOTAL_STEPS - 1);  // 0.0 to 1.0
    
    // Sine-based ease-in-out: smoothest possible curve
    // speed = sin(pi * t) - peaks at 1.0 at t=0.5, zero at ends
    float speed = sin(PI * t);
    if (speed < 0.08f) speed = 0.08f;  // Clamp minimum to prevent stalling
    
    // Map speed to delay: fast=1200us in the middle; slower at ends.
    int delayUs = (int)((1200.0f / speed) * TIME_SCALE);
    if (delayUs < 1200) delayUs = 1200;
    if (delayUs > 15000) delayUs = 15000;
    
    easeDelays[i] = delayUs;
  }
}

void stepMultipleRotations(bool clockwise, const char* label) {
  digitalWrite(DIR, clockwise ? HIGH : LOW);
  delay(50);  // Direction settle

  // Display updates must NOT happen during stepping.
  showStatus(label, "RUN");
  
  for (int i = 0; i < TOTAL_STEPS; i++) {
    // Step the motor - uninterrupted smooth motion
    digitalWrite(STEP, HIGH);
    delayMicroseconds(10);
    digitalWrite(STEP, LOW);
    delayMicroseconds(easeDelays[i]);

    // Keep ESP8266 background tasks serviced to avoid WDT resets.
    // This does not touch I2C and is far less disruptive than OLED updates.
    if ((i & 0x3F) == 0) {
      yield();
    }
  }

  showStatus(label, "DONE");
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
  display.println("6 x ROT");
  display.setCursor(0, 40);
  display.println("x4 SPEED");
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
  stepMultipleRotations(false, "C-CLOCKWISE");
  
  showPause(2);
}
