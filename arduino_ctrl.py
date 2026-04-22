import serial
import serial.tools.list_ports

_PARAM_DEFAULTS = {
    'dark_duty': 60, 'dark_freq': 500, 'dark_time': 40,
    'opto_duty': 100, 'opto_freq': 500, 'opto_len': 5, 'opto_delay': 8,
}

_PARAM_RANGES = {
    'dark_duty':  (0,   100),
    'dark_freq':  (1,   100000),
    'dark_time':  (0,   86400),
    'opto_duty':  (0,   100),
    'opto_freq':  (1,   100000),
    'opto_len':   (0,   86400),
    'opto_delay': (0,   86400),
}

class ArduinoHandler:
    def __init__(self, port=None, baudrate=9600):
        self.ser = None
        if not port:
            try:
                ports = list(serial.tools.list_ports.comports())
            except Exception as e:
                print(f"Failed to enumerate serial ports: {e}")
                ports = []
            if ports:
                port = ports[0].device
            else:
                print("No serial ports detected; Arduino will be unavailable.")
                return

        try:
            self.ser = serial.Serial(port, baudrate, timeout=1)
            print(f"Connected to Arduino on {port}")
        except serial.SerialException as e:
            print(f"Arduino connection error: {e}")
        except ValueError as e:
            print(f"Invalid serial port parameters: {e}")

    def _parse_int(self, value, key):
        default = _PARAM_DEFAULTS[key]
        lo, hi = _PARAM_RANGES[key]
        try:
            result = int(str(value).strip())
        except (ValueError, TypeError):
            print(f"Invalid value '{value}' for '{key}'; using default {default}")
            return default
        if not lo <= result <= hi:
            clamped = max(lo, min(hi, result))
            print(f"Value {result} for '{key}' out of range [{lo}, {hi}]; clamping to {clamped}")
            return clamped
        return result

    def send_led_data(self, data):
        if not self.ser or not self.ser.is_open:
            print("Arduino not connected; skipping send.")
            return False

        fields = [
            self._parse_int(data.get('dark_duty',  _PARAM_DEFAULTS['dark_duty']),  'dark_duty'),
            self._parse_int(data.get('dark_freq',  _PARAM_DEFAULTS['dark_freq']),  'dark_freq'),
            self._parse_int(data.get('dark_time',  _PARAM_DEFAULTS['dark_time']),  'dark_time'),
            self._parse_int(data.get('opto_duty',  _PARAM_DEFAULTS['opto_duty']),  'opto_duty'),
            self._parse_int(data.get('opto_freq',  _PARAM_DEFAULTS['opto_freq']),  'opto_freq'),
            self._parse_int(data.get('opto_len',   _PARAM_DEFAULTS['opto_len']),   'opto_len'),
            self._parse_int(data.get('opto_delay', _PARAM_DEFAULTS['opto_delay']), 'opto_delay'),
        ]

        msg = ",".join(str(f) for f in fields) + "\n"
        encoded = msg.encode()
        try:
            written = self.ser.write(encoded)
            if written != len(encoded):
                print(f"Warning: only {written}/{len(encoded)} bytes sent to Arduino")
                return False
            print(f"Sent to Arduino: {msg.strip()}")
            return True
        except serial.SerialException as e:
            print(f"Serial write error: {e}")
            return False

    def close(self):
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
                print("Arduino serial port closed.")
            except serial.SerialException as e:
                print(f"Error closing serial port: {e}")
