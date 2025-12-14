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

// Pre-computed ease-in-out delays in microseconds for 5 rotations
uint16_t easeDelays[TOTAL_STEPS];

// Simple status display - NO progress bar, minimal updates
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
  // Pre-compute all 1200 delays (6 rotations x 200 steps)
  // Symmetric steep easing: quick ramp-up AND quick ramp-down
  // Peak speed maintained at 1500us minimum delay
  
  for (int i = 0; i < TOTAL_STEPS; i++) {
    float t = (float)i / (float)(TOTAL_STEPS - 1);  // 0.0 to 1.0
    
    // Symmetric steep ease: quick acceleration AND deceleration
    // Both halves use quadratic curve with floor for abrupt transitions
    float speed;
    if (t < 0.5f) {
      // Ease-in: quadratic for steep acceleration (matches ease-out)
      float t2 = t * 2.0f;  // 0 to 1 for first half
      speed = t2 * t2 * 0.7f + 0.3f;  // Quadratic rise with floor
    } else {
      // Ease-out: quadratic for steep deceleration
      float t2 = (t - 0.5f) * 2.0f;  // 0 to 1 for second half
      speed = 1.0f - (t2 * t2 * 0.7f);  // Quadratic falloff with floor
    }
    
    // Minimum speed floor to prevent vibration at ends
    if (speed < 0.30f) speed = 0.30f;
    
    // Map speed to delay - peak speed at 1500us (unchanged)
    int delayUs = (int)(1500.0f / speed);
    if (delayUs < 1500) delayUs = 1500;  // Peak speed maintained
    if (delayUs > 5000) delayUs = 5000;  // Steeper = lower max delay
    
    easeDelays[i] = delayUs;
  }
}

void stepMultipleRotations(bool clockwise, const char* dirLabel) {
  digitalWrite(DIR, clockwise ? HIGH : LOW);
  delay(50);  // Direction settle
  
  // Show status ONCE before motion - no updates during motion!
  showStatus(dirLabel, "6 rotations");
  
  // Pure uninterrupted motion - NO display updates during stepping
  for (int i = 0; i < TOTAL_STEPS; i++) {
    digitalWrite(STEP, HIGH);
    delayMicroseconds(10);
    digitalWrite(STEP, LOW);
    delayMicroseconds(easeDelays[i]);
  }
  
  // Show completion after motion
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
  
  showStatus("STARTING", "Please wait");
  
  // Pre-compute smooth ease curve
  computeEaseDelays();
  delay(1000);
  
  showStatus("READY", "");
  delay(1000);
}

void loop() {
  Serial.println("Clockwise 6 rotations...");
  stepMultipleRotations(true, "CLOCKWISE");
  
  showPause(2);
  
  Serial.println("Counter-Clockwise 6 rotations...");
  stepMultipleRotations(false, "C-CLOCKWSE");
  
  showPause(2);
}
