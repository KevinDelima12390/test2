#!/usr/bin/env python3
import socket
import time
import subprocess
import threading
import lgpio
import os

# --- Configuration ---
MACBOOK_IP = "192.168.1.18"
UDP_PORT_CMD = 5005
UDP_PORT_VIDEO = 5000

FRAME_WIDTH = 1280
FRAME_HEIGHT = 720
FPS = 30

PAN_SERVO_PIN = 12
TILT_SERVO_PIN = 13
SERVO_FREQ = 50

MIN_PULSE = 500
MAX_PULSE = 2500
CENTER_PULSE = 1500

# --- ANTI-JITTER SETTINGS ---
SERVO_DEADBAND = 3  
# How long to wait (in seconds) after moving before cutting motor power
DETACH_DELAY = 0.5  

KP = 0.08
KI = 0.02
DEADZONE = 0.08
MAX_INTEGRAL = 100

MANUAL_STEP_SIZE = 25

class Gimbal:
    def __init__(self):
        self.h = lgpio.gpiochip_open(0)
        self.pan_pin = PAN_SERVO_PIN
        self.tilt_pin = TILT_SERVO_PIN
        self.video_process = None

        self.current_pos = {'pan': CENTER_PULSE, 'tilt': CENTER_PULSE}
        self.last_written_pos = {'pan': -1, 'tilt': -1}
        
        self.error_vec = {'x': 0, 'y': 0}
        self.integral = {'x': 0, 'y': 0}

        # Track when we last needed to move
        self.last_move_time = time.time()
        self.is_detached = False

        self._setup_servos()
        # Move to center initially
        self.set_pan(CENTER_PULSE, force=True)
        self.set_tilt(CENTER_PULSE, force=True)

        self.last_command_time = time.time()
        self.command_timeout = 2.0

    def _setup_servos(self):
        try:
            lgpio.gpio_claim_output(self.h, self.pan_pin)
            lgpio.gpio_claim_output(self.h, self.tilt_pin)
            print("Servos initialized.")
        except lgpio.error as e:
            print(f"Error: {e}")
            self.cleanup()
            exit(1)

    def detach_servos(self):
        """Stops sending PWM signals. Motor goes limp, friction holds position."""
        if not self.is_detached:
            # Sending 0 pulse width stops the PWM generation in lgpio
            lgpio.tx_servo(self.h, self.pan_pin, 0, SERVO_FREQ)
            lgpio.tx_servo(self.h, self.tilt_pin, 0, SERVO_FREQ)
            self.is_detached = True
            # print("Stabilized: Motors Detached") # Uncomment for debug

    def set_pan(self, pulse_width, force=False):
        target = max(MIN_PULSE, min(MAX_PULSE, pulse_width))
        self.current_pos['pan'] = target
        int_target = int(target)

        # Only write if moving outside deadband OR if we need to wake up (force)
        if force or abs(int_target - self.last_written_pos['pan']) >= SERVO_DEADBAND:
            lgpio.tx_servo(self.h, self.pan_pin, int_target, SERVO_FREQ)
            self.last_written_pos['pan'] = int_target
            self.last_move_time = time.time() # Reset sleep timer
            self.is_detached = False

    def set_tilt(self, pulse_width, force=False):
        target = max(MIN_PULSE, min(MAX_PULSE, pulse_width))
        self.current_pos['tilt'] = target
        int_target = int(target)

        if force or abs(int_target - self.last_written_pos['tilt']) >= SERVO_DEADBAND:
            lgpio.tx_servo(self.h, self.tilt_pin, int_target, SERVO_FREQ)
            self.last_written_pos['tilt'] = int_target
            self.last_move_time = time.time() # Reset sleep timer
            self.is_detached = False

    def _start_stream(self):
        """Starts the video stream using rpicam-vid with low-latency settings over TCP."""
        print(f"Starting TCP video stream server on port {UDP_PORT_VIDEO}")
        command = [
            'rpicam-vid', '-t', '0', '--inline',
            '--width', str(FRAME_WIDTH), '--height', str(FRAME_HEIGHT),
            '--framerate', str(FPS),
            '--codec', 'h264',
            '--bitrate', '5000000',
            '-g', '15',
            '--listen', # Act as a TCP server
            '-o', f'tcp://0.0.0.0:{UDP_PORT_VIDEO}'
        ]
        try:
            self.video_process = subprocess.Popen(command, preexec_fn=os.setsid)
        except FileNotFoundError:
            print("Error: rpicam-vid not found.")
            self.cleanup()
            exit(1)

    def _pi_control_loop(self):
        while True:
            # Check for command timeout
            if time.time() - self.last_command_time > self.command_timeout:
                self.error_vec = {'x': 0, 'y': 0}
                self.integral = {'x': 0, 'y': 0}

            # Check if we are currently stable (Inside Deadzone)
            in_deadzone_x = abs(self.error_vec['x']) <= DEADZONE
            in_deadzone_y = abs(self.error_vec['y']) <= DEADZONE

            if in_deadzone_x and in_deadzone_y:
                # If stable for > 0.5 seconds, kill motors
                if (time.time() - self.last_move_time) > DETACH_DELAY:
                    self.detach_servos()
            else:
                # We need to move!
                
                # PAN Logic
                if not in_deadzone_x:
                    self.integral['x'] += self.error_vec['x']
                    self.integral['x'] = max(-MAX_INTEGRAL, min(MAX_INTEGRAL, self.integral['x']))
                    adjustment_x = (KP * self.error_vec['x']) + (KI * self.integral['x'])
                    self.set_pan(self.current_pos['pan'] - adjustment_x)

                # TILT Logic
                if not in_deadzone_y:
                    self.integral['y'] += self.error_vec['y']
                    self.integral['y'] = max(-MAX_INTEGRAL, min(MAX_INTEGRAL, self.integral['y']))
                    adjustment_y = (KP * self.error_vec['y']) + (KI * self.integral['y'])
                    self.set_tilt(self.current_pos['tilt'] - adjustment_y)

            time.sleep(0.02)

    def listen_for_commands(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.bind(("", UDP_PORT_CMD))
            print(f"Listening on port {UDP_PORT_CMD}")
            while True:
                data, _ = s.recvfrom(1024)
                self.last_command_time = time.time()
                try:
                    parts = data.decode('utf-8').strip().split(':')
                    if parts[0] == "ERR":
                        x, y = parts[1].split(',')
                        # Wake up servos immediately on new data
                        self.last_move_time = time.time() 
                        self.error_vec = {'x': float(x), 'y': float(y)}
                        
                    elif parts[0] == "MAN":
                        self.last_move_time = time.time() # Wake up
                        axis, d_str = parts[1].split(',')
                        direction = int(d_str)
                        if axis == 'pan':
                            self.set_pan(self.current_pos['pan'] + direction * MANUAL_STEP_SIZE, force=True)
                        elif axis == 'tilt':
                            self.set_tilt(self.current_pos['tilt'] - direction * MANUAL_STEP_SIZE, force=True)
                except Exception as e:
                    pass

    def run(self):
        self._start_stream()
        control_thread = threading.Thread(target=self._pi_control_loop, daemon=True)
        control_thread.start()
        self.listen_for_commands()

    def cleanup(self):
        if self.video_process:
            os.killpg(os.getpgid(self.video_process.pid), subprocess.signal.SIGTERM)
        if self.h:
            # Stop PWM before exit
            lgpio.tx_servo(self.h, self.pan_pin, 0, SERVO_FREQ)
            lgpio.tx_servo(self.h, self.tilt_pin, 0, SERVO_FREQ)
            lgpio.gpiochip_close(self.h)

if __name__ == "__main__":
    gimbal = Gimbal()
    try:
        gimbal.run()
    except KeyboardInterrupt:
        pass
    finally:
        gimbal.cleanup()