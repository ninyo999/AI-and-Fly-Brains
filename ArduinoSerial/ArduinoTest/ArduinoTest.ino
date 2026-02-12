const int ledopto = 5;
const int leddarkfield = 7;

void setup() {
  pinMode(ledopto, OUTPUT);
  pinMode(leddarkfield, OUTPUT);
}

void loop() {

  // Turn BOTH LEDs ON at the same time
  digitalWrite(ledopto, HIGH);
  digitalWrite(leddarkfield, HIGH);

  // ledopto stays ON for 2 seconds
  delay(2000);
  digitalWrite(ledopto, LOW);

  // leddarkfield stays ON for a total of 122000 ms
  delay(122000 - 2000);  
  digitalWrite(leddarkfield, LOW);

}