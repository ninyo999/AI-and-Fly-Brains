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
            # Protocol: D:duty,freq,time|O:duty,freq,len,delay
            msg = (f"D:{data['dark_duty']},{data['dark_freq']},{data['dark_time']}|"
                   f"O:{data['opto_duty']},{data['opto_freq']},{data['opto_len']},{data['opto_delay']}\n")
            self.ser.write(msg.encode())