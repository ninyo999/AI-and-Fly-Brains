import serial
import serial.tools.list_ports

# Fixed PWM settings — not exposed to the user
_PWM_DARK_DUTY  = 60
_PWM_DARK_FREQ  = 500
_PWM_OPTO_DUTY  = 100
_PWM_OPTO_FREQ  = 500

_DURATION_DEFAULTS = {
    'baseline_duration': 10,
    'opto_duration':     10,
    'reaction_duration': 15,
}

_DURATION_RANGES = {
    'baseline_duration': (0, 86400),
    'opto_duration':     (0, 86400),
    'reaction_duration': (0, 86400),
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

    def _parse_duration(self, value, key):
        default = _DURATION_DEFAULTS[key]
        lo, hi = _DURATION_RANGES[key]
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

        baseline = self._parse_duration(
            data.get('baseline_duration', _DURATION_DEFAULTS['baseline_duration']),
            'baseline_duration')
        opto_dur = self._parse_duration(
            data.get('opto_duration', _DURATION_DEFAULTS['opto_duration']),
            'opto_duration')
        reaction = self._parse_duration(
            data.get('reaction_duration', _DURATION_DEFAULTS['reaction_duration']),
            'reaction_duration')

        # Message format: dark_duty,dark_freq,baseline,opto_duty,opto_freq,opto_duration,reaction
        fields = [
            _PWM_DARK_DUTY, _PWM_DARK_FREQ, baseline,
            _PWM_OPTO_DUTY, _PWM_OPTO_FREQ, opto_dur, reaction,
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
