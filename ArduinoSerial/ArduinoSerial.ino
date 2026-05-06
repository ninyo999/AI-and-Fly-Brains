const int ledopto      = 5;
const int leddarkfield = 7;

const int DARK_BRIGHTNESS = 153;  // 60% of 255
const int OPTO_BRIGHTNESS = 255;  // 100% of 255

void setup() {
  Serial.begin(9600);
  pinMode(ledopto,      OUTPUT);
  pinMode(leddarkfield, OUTPUT);
}

void loop() {
  if (Serial.available() > 0) {
    String data = Serial.readStringUntil('\n');

    // Message format from Python (3 comma-separated values):
    // baseline_duration, opto_duration, reaction_duration  (all in seconds)
    int baseline = getValue(data, ',', 0);
    int opto_dur = getValue(data, ',', 1);
    int reaction = getValue(data, ',', 2);

    runExperiment(baseline, opto_dur, reaction);
  }
}

void runExperiment(int baseline, int opto_dur, int reaction) {
  // 1. Baseline
  analogWrite(leddarkfield, DARK_BRIGHTNESS);
  delay(baseline * 1000);

  // 2. Optogenetics stimulus
  analogWrite(ledopto, OPTO_BRIGHTNESS);
  delay(opto_dur * 1000);

  // 3. Reaction window
  analogWrite(ledopto, 0);
  delay(reaction * 1000);

  // 4. End
  analogWrite(leddarkfield, 0);
}

int getValue(String data, char separator, int index) {
  int found      = 0;
  int strIndex[] = {0, -1};
  int maxIndex   = data.length() - 1;

  for (int i = 0; i <= maxIndex && found <= index; i++) {
    if (data.charAt(i) == separator || i == maxIndex) {
      found++;
      strIndex[0] = strIndex[1] + 1;
      strIndex[1] = (i == maxIndex) ? i + 1 : i;
    }
  }
  return found > index ? data.substring(strIndex[0], strIndex[1]).toInt() : 0;
}
