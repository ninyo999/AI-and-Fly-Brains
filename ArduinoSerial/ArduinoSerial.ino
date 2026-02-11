const int ledopto = 5;      
const int leddarkfield = 7; 

void setup() {
  Serial.begin(9600);
  pinMode(ledopto, OUTPUT);
  pinMode(leddarkfield, OUTPUT);
}

void loop() {
  if (Serial.available() > 0) {
    String data = Serial.readStringUntil('\n');
    
    // Parse the 7 values sent from Python
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
  // Start Darkfield (scaled 0-100 to 0-255)
  analogWrite(leddarkfield, map(d_duty, 0, 100, 0, 255));
  
  // Initial Delay before Optogenetic starts
  delay(o_delay * 1000); // Converting seconds to milliseconds
  
  // Start Optogenetics
  analogWrite(ledopto, map(o_duty, 0, 100, 0, 255));
  delay(o_len * 1000);
  analogWrite(ledopto, 0); 
  
  // Stay on for remainder of active time
  int remaining = d_time - o_delay - o_len;
  if (remaining > 0) {
    delay(remaining * 1000);
  }
  
  analogWrite(leddarkfield, 0); 
}

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
