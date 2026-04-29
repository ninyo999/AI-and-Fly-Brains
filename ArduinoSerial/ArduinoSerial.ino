const int ledopto       = 5;
const int leddarkfield  = 7;

void setup() {
  Serial.begin(9600);
  pinMode(ledopto,      OUTPUT);
  pinMode(leddarkfield, OUTPUT);
}

void loop() {
  if (Serial.available() > 0) {
    String data = Serial.readStringUntil('\n');

    // Message format from Python (7 comma-separated values):
    // dark_duty, dark_freq, baseline_duration, opto_duty, opto_freq, opto_duration, reaction_duration
    int d_duty    = getValue(data, ',', 0);  // dark field duty cycle (0-100)
    int d_freq    = getValue(data, ',', 1);  // dark field frequency  (not used by analogWrite)
    int baseline  = getValue(data, ',', 2);  // baseline duration in seconds
    int o_duty    = getValue(data, ',', 3);  // opto duty cycle (0-100)
    int o_freq    = getValue(data, ',', 4);  // opto frequency  (not used by analogWrite)
    int opto_dur  = getValue(data, ',', 5);  // optogenetics duration in seconds
    int reaction  = getValue(data, ',', 6);  // reaction duration in seconds

    runExperiment(d_duty, baseline, o_duty, opto_dur, reaction);
  }
}

// Experiment sequence:
//  1. Turn ON dark field LED  →  wait baseline duration
//  2. Turn ON opto LED        →  wait opto duration
//  3. Turn OFF opto LED       →  wait reaction duration
//  4. Turn OFF dark field LED
void runExperiment(int d_duty, int baseline, int o_duty, int opto_dur, int reaction) {
  // 1. Baseline — dark field LED on, no optogenetics
  analogWrite(leddarkfield, map(d_duty, 0, 100, 0, 255));
  delay(baseline * 1000);

  // 2. Optogenetics — opto LED on for stimulus duration
  analogWrite(ledopto, map(o_duty, 0, 100, 0, 255));
  delay(opto_dur * 1000);

  // 3. Reaction window — opto LED off, observe fly response
  analogWrite(ledopto, 0);
  delay(reaction * 1000);

  // 4. End — dark field LED off
  analogWrite(leddarkfield, 0);
}

// Helper: extract the nth comma-separated value from a string
int getValue(String data, char separator, int index) {
  int found     = 0;
  int strIndex[] = {0, -1};
  int maxIndex  = data.length() - 1;

  for (int i = 0; i <= maxIndex && found <= index; i++) {
    if (data.charAt(i) == separator || i == maxIndex) {
      found++;
      strIndex[0] = strIndex[1] + 1;
      strIndex[1] = (i == maxIndex) ? i + 1 : i;
    }
  }
  return found > index ? data.substring(strIndex[0], strIndex[1]).toInt() : 0;
}
