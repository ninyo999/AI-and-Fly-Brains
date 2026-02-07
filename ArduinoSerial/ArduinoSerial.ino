const int ledopto = 5;      // PWM capable pin
const int leddarkfield = 7; // Digital pin (or PWM if supported)

void setup() {
  Serial.begin(9600);
  pinMode(ledopto, OUTPUT);
  pinMode(leddarkfield, OUTPUT);
}

void loop() {
  if (Serial.available() > 0) {
    // Read the incoming line from Python
    String data = Serial.readStringUntil('\n');
    
    // Parse the comma-separated values
    int d_duty  = getValue(data, ',', 0);
    int d_freq  = getValue(data, ',', 1);
    int d_time  = getValue(data, ',', 2);
    int o_duty  = getValue(data, ',', 3);
    int o_freq  = getValue(data, ',', 4);
    int o_len   = getValue(data, ',', 5);
    int o_delay = getValue(data, ',', 6);

    runExperiment(d_duty, d_time, o_duty, o_len, o_delay);
  }
}

void runExperiment(int d_duty, int d_time, int o_duty, int o_len, int o_delay) {
  // Start Darkfield (scaled 0-100 duty to 0-255 PWM)
  analogWrite(leddarkfield, map(d_duty, 0, 100, 0, 255));
  
  // Initial Delay for Opto
  delay(o_delay);
  
  // Start Opto
  analogWrite(ledopto, map(o_duty, 0, 100, 0, 255));
  delay(o_len);
  analogWrite(ledopto, 0); // Turn off Opto after flash length
  
  // Wait for the remainder of the darkfield active time
  if (d_time > (o_delay + o_len)) {
    delay(d_time - (o_delay + o_len));
  }
  
  analogWrite(leddarkfield, 0); // Turn off Darkfield
}

// Helper function to split the string
int getValue(String data, char separator, int index) {
  int found = 0;
  int strIndex[] = {0, -1};
  int maxIndex = data.length() - 1;
  for (int i = 0; i <= maxIndex && found <= index; i++) {
    if (data.charAt(i) == separator || i == maxIndex) {
      found++;
      strIndex[0] = strIndex[1] + 1;
      strIndex[1] = (i == maxIndex) ? i + 1 : i;
    }
  }
  return found > index ? data.substring(strIndex[0], strIndex[1]).toInt() : 0;
}