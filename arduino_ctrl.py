import serial
import serial.tools.list_ports
import time

class ArduinoHandler:
    def __init__(self, port=None, baudrate=9600):
        self.ser = None
        if not port:
            # Auto-detect first available port
            ports = list(serial.tools.list_ports.comports())
            if ports: port = ports[0].device
        
        if port:
            try:
                self.ser = serial.Serial(port, baudrate, timeout=1)
                print(f"Connected to Arduino on {port}")
            except Exception as e:
                print(f"Arduino Connection Error: {e}")

    def send_led_data(self, data):
        if self.ser and self.ser.is_open:
            try:
                msg = ",".join([
                    str(int(data.get('dark_duty', 60))),
                    str(int(data.get('dark_freq', 500))), 
                    str(int(data.get('dark_time', 40))),
                    str(int(data.get('opto_duty', 100))),
                    str(int(data.get('opto_freq', 500))),
                    str(int(data.get('opto_len', 5))),
                    str(int(data.get('opto_delay', 8)))
                ]) + "\n"
                
                self.ser.write(msg.encode())
                print(f"Sent Experiment Data to Arduino: {msg.strip()}")
                
            except Exception as e:
                print(f"Error sending to Arduino: {e}")