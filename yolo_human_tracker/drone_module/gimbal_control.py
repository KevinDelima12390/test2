from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QGridLayout
from PyQt6.QtCore import pyqtSignal
import math

class GimbalControl(QWidget):
    gimbal_command = pyqtSignal(str, int)
    follow_gimbal_command = pyqtSignal(float, float) # pitch_rate, yaw_rate

    def __init__(self):
        super().__init__()

        self.pan = 0
        self.tilt = 0
        self.gimbal_pitch_rad_s = 0.0 # Current desired pitch angular rate
        self.gimbal_yaw_rad_s = 0.0   # Current desired yaw angular rate

        layout = QVBoxLayout()
        self.setLayout(layout)

        grid = QGridLayout()
        layout.addLayout(grid)

        up_button = QPushButton("↑")
        down_button = QPushButton("↓")
        left_button = QPushButton("←")
        right_button = QPushButton("→")

        grid.addWidget(up_button, 0, 1)
        grid.addWidget(down_button, 2, 1)
        grid.addWidget(left_button, 1, 0)
        grid.addWidget(right_button, 1, 2)

        up_button.clicked.connect(lambda: self.send_command('tilt', 1))
        down_button.clicked.connect(lambda: self.send_command('tilt', -1))
        left_button.clicked.connect(lambda: self.send_command('pan', -1))
        right_button.clicked.connect(lambda: self.send_command('pan', 1))

    def send_command(self, axis, direction):
        if axis == 'pan':
            self.pan += direction
        elif axis == 'tilt':
            self.tilt += direction
        self.gimbal_command.emit(axis, direction)

    def follow_target_in_frame(self, norm_center_x, norm_center_y):
        """
        Calculates angular rates to center a target in the frame
        and emits a signal to send the MAVLink command.
        :param norm_center_x: Normalized X coordinate of target center (-1 to 1, -1 is left, 1 is right)
        :param norm_center_y: Normalized Y coordinate of target center (-1 to 1, -1 is top, 1 is bottom)
        """
        # Proportional control for angular rates
        # These constants (Kp_yaw, Kp_pitch) would need tuning
        Kp_yaw = 0.5  # Proportional gain for yaw
        Kp_pitch = 0.5 # Proportional gain for pitch

        # Calculate desired angular rates
        # If norm_center_x is positive, target is to the right, need positive yaw rate
        # If norm_center_y is positive, target is down, need positive pitch rate (gimbal pitch down is positive)
        self.gimbal_yaw_rad_s = Kp_yaw * norm_center_x
        self.gimbal_pitch_rad_s = Kp_pitch * norm_center_y

        # Clamp rates to reasonable maximums (e.g., 5 rad/s ~ 286 deg/s)
        max_rate = math.radians(60) # Example: max 60 degrees/second
        self.gimbal_yaw_rad_s = max(-max_rate, min(max_rate, self.gimbal_yaw_rad_s))
        self.gimbal_pitch_rad_s = max(-max_rate, min(max_rate, self.gimbal_pitch_rad_s))

        self.follow_gimbal_command.emit(self.gimbal_pitch_rad_s, self.gimbal_yaw_rad_s)
