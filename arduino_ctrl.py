import serial
import serial.tools.list_ports

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
                clean_msg = ",".join([
                    str(int(data.get('dark_duty', 0))),
                    str(int(data.get('dark_freq', 0))),
                    str(int(data.get('dark_time', 0))),
                    str(int(data.get('opto_duty', 0))),
                    str(int(data.get('opto_freq', 0))),
                    str(int(data.get('opto_len', 0))),
                    str(int(data.get('opto_delay', 0)))
                ]) + "\n"
                
                self.ser.write(clean_msg.encode())
                print(f"Sent to Arduino: {clean_msg.strip()}")
            except ValueError:
                print("Error: LED settings must be numbers.")