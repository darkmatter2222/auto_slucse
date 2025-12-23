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
const int SPEED_BTN = 13;  // D7 - momentary button to GND (INPUT_PULLUP)
const int STEPS_PER_REV = 200;
static constexpr uint8_t RPS_MIN = 1;
static constexpr uint8_t RPS_MAX = 5;
static constexpr uint16_t STEP_PULSE_US = 10;
static constexpr uint16_t BUTTON_DEBOUNCE_MS = 35;

uint8_t currentRps = RPS_MAX;  // Boot at 5 revolutions per second
bool uiUpdatePending = true;

struct DebouncedButton {
  bool lastReading = false;
  bool stableState = false;
  uint32_t lastChangeMs = 0;
};

DebouncedButton speedButton;

void showRps(uint8_t rps) {
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.println("STEPPER CONTROL");

  display.setTextSize(2);
  display.setCursor(0, 18);
  display.println("SPEED");

  display.setTextSize(2);
  display.setCursor(0, 42);
  display.print(rps);
  display.println(" RPS");

  display.display();
}

bool isSpeedButtonPressedEvent() {
  const uint32_t nowMs = millis();
  const bool readingPressed = (digitalRead(SPEED_BTN) == LOW);

  if (readingPressed != speedButton.lastReading) {
    speedButton.lastReading = readingPressed;
    speedButton.lastChangeMs = nowMs;
  }

  if ((nowMs - speedButton.lastChangeMs) < BUTTON_DEBOUNCE_MS) {
    return false;
  }

  if (speedButton.stableState != readingPressed) {
    speedButton.stableState = readingPressed;
    if (speedButton.stableState) {
      return true;  // pressed (stable) edge
    }
  }

  return false;
}

uint32_t stepIntervalUsForRps(uint8_t rps) {
  if (rps < RPS_MIN) rps = RPS_MIN;
  if (rps > RPS_MAX) rps = RPS_MAX;
  const uint32_t stepsPerSecond = (uint32_t)rps * (uint32_t)STEPS_PER_REV;
  if (stepsPerSecond == 0) {
    return 1000000UL;
  }
  const uint32_t intervalUs = 1000000UL / stepsPerSecond;
  return (intervalUs < (uint32_t)STEP_PULSE_US) ? (uint32_t)STEP_PULSE_US : intervalUs;
}

void setup() {
  Serial.begin(115200);
  pinMode(STEP, OUTPUT);
  pinMode(DIR, OUTPUT);
  pinMode(SPEED_BTN, INPUT_PULLUP);
  
  // Initialize I2C for display
  Wire.begin();
  
  // Initialize display
  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println("SSD1306 allocation failed");
  }

  // Set direction once at startup (continuous clockwise motion).
  // ⚠️ CRITICAL: Do not change this expression.
  const bool clockwise = true;
  digitalWrite(DIR, clockwise ? HIGH : LOW);
  delay(50);  // Direction settle

  showRps(currentRps);
  delay(500);
}

void loop() {
  if (isSpeedButtonPressedEvent()) {
    currentRps = (currentRps >= RPS_MAX) ? RPS_MIN : (uint8_t)(currentRps + 1);
    uiUpdatePending = true;
    Serial.printf("Speed changed: %u RPS\n", currentRps);
  }

  // Only update OLED when NOT actively stepping.
  if (uiUpdatePending) {
    showRps(currentRps);
    uiUpdatePending = false;
  }

  const uint32_t stepIntervalUs = stepIntervalUsForRps(currentRps);
  const uint32_t lowDelayUs = (stepIntervalUs > (uint32_t)STEP_PULSE_US)
                                ? (stepIntervalUs - (uint32_t)STEP_PULSE_US)
                                : 0;

  digitalWrite(STEP, HIGH);
  delayMicroseconds(STEP_PULSE_US);
  digitalWrite(STEP, LOW);
  if (lowDelayUs > 0) {
    delayMicroseconds(lowDelayUs);
  }

  // Keep ESP8266 background tasks serviced to avoid WDT resets.
  static uint16_t stepCounter = 0;
  stepCounter++;
  if ((stepCounter & 0x3F) == 0) {
    yield();
  }
}
