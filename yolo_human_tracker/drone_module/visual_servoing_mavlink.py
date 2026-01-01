
import time
import numpy as np

# --- CONTROL LOOP CONFIGURATION ---
# These gains will likely need tuning for your specific drone and gimbal.
KP = 0.8  # Proportional gain: How aggressively it reacts to the current error.
KI = 0.4  # Integral gain: Corrects for steady-state error over time.

# Gimbal Control Limits & Behavior
DEADZONE_PERCENT = 0.05      # 5% of frame width/height, where no movement occurs.
MAX_INTEGRAL = 15.0          # Anti-windup: Prevents the integral term from growing too large.
MAX_TILT_RATE = 2.0          # Maximum degrees to move per update cycle for tilt.
MAX_PAN_RATE = 2.0           # Maximum degrees to move per update cycle for pan.
PAN_LIMIT = (-90, 90)        # Pan angle limits in degrees.
TILT_LIMIT = (-90, 0)        # Tilt angle limits in degrees (0 is forward, -90 is down).

class VisualServoingMAVLink:
    """
    Manages the PI control loop for visual servoing and sends MAVLink gimbal commands.
    """
    def __init__(self, mavlink_communicator):
        """
        Initializes the MAVLink-based visual servoing controller.

        Args:
            mavlink_communicator: An instance of the MavlinkCommunicator class.
        """
        self.mavlink_comm = mavlink_communicator
        
        # PI Controller State
        self.integral_error_pan = 0.0
        self.integral_error_tilt = 0.0
        self.last_time = time.time()
        
        # Current Gimbal State (in degrees)
        self.pan_angle = 0.0
        self.tilt_angle = 0.0
        
        print("MAVLink Visual Servoing Controller Initialized.")

    def reset(self):
        """Resets the integral errors to stop any drifting."""
        self.integral_error_pan = 0.0
        self.integral_error_tilt = 0.0
        self.last_time = time.time()

    def update_error(self, error_x, error_y):
        """
        Calculates the required gimbal movement from an error vector and sends
        the MAVLink command.

        Args:
            error_x (float): Normalized horizontal error (-1.0 to 1.0).
            error_y (float): Normalized vertical error (-1.0 to 1.0).
        """
        dt = time.time() - self.last_time
        if dt == 0:
            return

        # --- Pan (Yaw) Control ---
        if abs(error_x) > DEADZONE_PERCENT:
            self.integral_error_pan += error_x * dt
            self.integral_error_pan = np.clip(self.integral_error_pan, -MAX_INTEGRAL, MAX_INTEGRAL)
            
            p_term = KP * error_x
            i_term = KI * self.integral_error_pan
            
            # The control signal determines the rate of change
            pan_rate = -(p_term + i_term) # Negative sign to correct direction
            pan_rate = np.clip(pan_rate, -MAX_PAN_RATE, MAX_PAN_RATE)
            
            self.pan_angle += pan_rate
        else:
            self.integral_error_pan = 0 # Reset when in deadzone

        # --- Tilt (Pitch) Control ---
        if abs(error_y) > DEADZONE_PERCENT:
            self.integral_error_tilt += error_y * dt
            self.integral_error_tilt = np.clip(self.integral_error_tilt, -MAX_INTEGRAL, MAX_INTEGRAL)

            p_term = KP * error_y
            i_term = KI * self.integral_error_tilt
            
            # Control signal determines the rate of change
            tilt_rate = p_term + i_term # Positive sign for standard gimbal orientation
            tilt_rate = np.clip(tilt_rate, -MAX_TILT_RATE, MAX_TILT_RATE)

            self.tilt_angle += tilt_rate
        else:
            self.integral_error_tilt = 0 # Reset when in deadzone
            
        # Clamp angles to their limits
        self.pan_angle = np.clip(self.pan_angle, PAN_LIMIT[0], PAN_LIMIT[1])
        self.tilt_angle = np.clip(self.tilt_angle, TILT_LIMIT[0], TILT_LIMIT[1])

        # Send the command to the drone's gimbal
        # MAVLink requires angles in centi-degrees (degrees * 100)
        pitch_cdeg = int(self.tilt_angle * 100)
        yaw_cdeg = int(self.pan_angle * 100)
        
        self.mavlink_comm.send_gimbal_command(pitch=pitch_cdeg, yaw=yaw_cdeg)

        self.last_time = time.time()
