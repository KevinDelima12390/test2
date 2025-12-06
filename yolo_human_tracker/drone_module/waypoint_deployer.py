from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget, QInputDialog, QMessageBox
from PyQt6.QtCore import pyqtSignal
from pymavlink import mavutil
import logging

class WaypointDeployer(QWidget):
    start_mission = pyqtSignal(list)

    def __init__(self, mavlink_communicator=None):
        super().__init__()
        self.mavlink_communicator = mavlink_communicator

        self.waypoints = [] # Stores waypoints as [{'id': 'user_id', 'lat': float, 'lon': float}]

        layout = QVBoxLayout()
        self.setLayout(layout)

        self.waypoint_list = QListWidget()
        layout.addWidget(self.waypoint_list)

        button_layout = QHBoxLayout()
        layout.addLayout(button_layout)

        # Disable Add and Edit buttons as waypoints come from emergency events
        # add_button = QPushButton("Add")
        # edit_button = QPushButton("Edit")
        delete_button = QPushButton("Delete Selected")
        start_mission_button = QPushButton("Start Mission with Selected")

        # button_layout.addWidget(add_button)
        # button_layout.addWidget(edit_button)
        button_layout.addWidget(delete_button)
        button_layout.addWidget(start_mission_button)

        # add_button.clicked.connect(self.add_waypoint_dialog)
        # edit_button.clicked.connect(self.edit_waypoint)
        delete_button.clicked.connect(self.delete_waypoint)
        start_mission_button.clicked.connect(self.start_mission_clicked)

    def add_waypoint(self, waypoint_str_with_id):
        try:
            lat_str, lon_str, user_id = waypoint_str_with_id.split(',')
            lat = float(lat_str)
            lon = float(lon_str)
            self.waypoints.append({'id': user_id, 'lat': lat, 'lon': lon})
            self.update_waypoint_list()
        except ValueError:
            QMessageBox.warning(self, "Waypoint Error", f"Invalid waypoint format: {waypoint_str_with_id}")

    def delete_waypoint(self):
        current_item = self.waypoint_list.currentItem()
        if current_item:
            row = self.waypoint_list.row(current_item)
            del self.waypoints[row]
            self.update_waypoint_list()

    def update_waypoint_list(self):
        self.waypoint_list.clear()
        for wp in self.waypoints:
            self.waypoint_list.addItem(f"ID: {wp['id']} - Lat: {wp['lat']:.6f}, Lon: {wp['lon']:.6f}")

    def start_mission_clicked(self):
        current_item = self.waypoint_list.currentItem()
        if current_item:
            row = self.waypoint_list.row(current_item)
            selected_wp = self.waypoints[row]
            # Emit a list of waypoints, even if it's just one for the mission animation
            self.start_mission.emit([f"{selected_wp['lat']},{selected_wp['lon']}"])
        else:
            QMessageBox.warning(self, "Mission Start", "Please select a waypoint to start the mission.")

    def send_follow_command(self, target_lat, target_lon, target_alt, follow_distance, follow_altitude):
        """
        Sends a MAVLink SET_POSITION_TARGET_GLOBAL_INT command to the drone
        to initiate following a target.

        :param target_lat: Latitude of the target (degrees)
        :param target_lon: Longitude of the target (degrees)
        :param target_alt: Altitude of the target (meters, relative to home)
        :param follow_distance: Desired horizontal distance to maintain from target (meters)
        :param follow_altitude: Desired altitude to maintain above target (meters)
        """
        if not self.mavlink_communicator or not self.mavlink_communicator.master:
            logging.error("MAVLink communicator not initialized or connected. Cannot send follow command.")
            return

        # Target altitude for drone is target_alt + follow_altitude
        # The target_alt from position_tracker is relative to drone's launch.
        # We want the drone to be `follow_altitude` above the target's estimated position.
        # So, new_target_alt = target_alt + follow_altitude

        # The SET_POSITION_TARGET_GLOBAL_INT message expects altitude in meters above home (AMSL or AGL depending on frame)
        # MAV_FRAME_GLOBAL_RELATIVE_ALT_INT means relative to home altitude.
        # So, the target_alt here needs to be calculated in that frame.
        # For simplicity, we will assume target_alt already aligns with this or is close enough for a relative follow.
        # The `target_alt` from `position_tracker` is `target_alt_relative` to the drone's launch point.
        # Let's use this as the base for the drone's target altitude.
        
        # Calculate the actual target coordinates for the drone to go to.
        # The drone should follow *behind* the target, or at a certain offset.
        # For now, let's just make the drone go to the target's estimated location
        # but at `follow_altitude` above it.
        
        # If a `follow_distance` is given, it implies an offset from the target.
        # Without knowing the target's movement direction, placing the drone
        # `follow_distance` behind it is difficult.
        # For a basic follow, let's make the drone fly to the target's estimated horizontal position
        # and maintain `follow_altitude` above the target.

        # Mask for SET_POSITION_TARGET_GLOBAL_INT
        # "Position Only (Ignore Velocity, Acceleration, Yaw)"
        # bits: x, y, z, vx, vy, vz, afx, afy, afz, yaw, yaw_rate
        # 0b000_000_000_000_000_000_000_000_000_000
        # Ignore velocity (bits 4,5,6), acceleration (bits 7,8,9), yaw (bits 10), yaw_rate (bit 11)
        # Bit values (LSB to MSB):
        # 0-2: position (x, y, z)
        # 3-5: velocity (vx, vy, vz)
        # 6-8: acceleration (afx, afy, afz)
        # 9: yaw
        # 10: yaw_rate

        # So to ignore velocity, acceleration, yaw, and yaw_rate:
        # 0b110111111000 = 0xDF8 (Incorrect interpretation from Ardupilot docs)
        # Mask bits are 1 if *ignored*.
        # MAVLINK_POSITION_TARGET_TYPEMASK_X_IGNORE (1), MAVLINK_POSITION_TARGET_TYPEMASK_Y_IGNORE (2), MAVLINK_POSITION_TARGET_TYPEMASK_Z_IGNORE (4)
        # MAVLINK_POSITION_TARGET_TYPEMASK_VX_IGNORE (8), MAVLINK_POSITION_TARGET_TYPEMASK_VY_IGNORE (16), MAVLINK_POSITION_TARGET_TYPEMASK_VZ_IGNORE (32)
        # MAVLINK_POSITION_TARGET_TYPEMASK_AX_IGNORE (64), MAVLINK_POSITION_TARGET_TYPEMASK_AY_IGNORE (128), MAVLINK_POSITION_TARGET_TYPEMASK_AZ_IGNORE (256)
        # MAVLINK_POSITION_TARGET_TYPEMASK_YAW_IGNORE (512), MAVLINK_POSITION_TARGET_TYPEMASK_YAW_RATE_IGNORE (1024)

        # "Position Only (Ignore Velocity, Acceleration, Yaw)"
        type_mask = (
            mavutil.mavlink.MAVLINK_POSITION_TARGET_TYPEMASK_VX_IGNORE |
            mavutil.mavlink.MAVLINK_POSITION_TARGET_TYPEMASK_VY_IGNORE |
            mavutil.mavlink.MAVLINK_POSITION_TARGET_TYPEMASK_VZ_IGNORE |
            mavutil.mavlink.MAVLINK_POSITION_TARGET_TYPEMASK_AX_IGNORE |
            mavutil.mavlink.MAVLINK_POSITION_TARGET_TYPEMASK_AY_IGNORE |
            mavutil.mavlink.MAVLINK_POSITION_TARGET_TYPEMASK_AZ_IGNORE |
            mavutil.mavlink.MAVLINK_POSITION_TARGET_TYPEMASK_YAW_IGNORE |
            mavutil.mavlink.MAVLINK_POSITION_TARGET_TYPEMASK_YAW_RATE_IGNORE
        )

        # MAV_FRAME_GLOBAL_RELATIVE_ALT_INT: Altitude is relative to home altitude.
        frame = mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT

        # Target altitude: Estimated target altitude + desired follow altitude
        drone_target_alt = target_alt + follow_altitude

        try:
            # Need to get current time_boot_ms from system if available, or just use 0.
            # Using 0 for now for time_boot_ms
            self.mavlink_communicator.master.mav.set_position_target_global_int_send(
                0, # time_boot_ms (not used if type_mask ignores velocity/acceleration)
                self.mavlink_communicator.master.target_system,
                self.mavlink_communicator.master.target_component,
                frame,
                type_mask,
                int(target_lat * 1e7), # lat_int
                int(target_lon * 1e7), # lon_int
                drone_target_alt,      # alt (meters)
                0, 0, 0, # vx, vy, vz (ignored by mask)
                0, 0, 0, # afx, afy, afz (ignored by mask)
                0, 0     # yaw, yaw_rate (ignored by mask)
            )
            logging.info(f"Sent SET_POSITION_TARGET_GLOBAL_INT: Lat={target_lat:.6f}, Lon={target_lon:.6f}, Alt={drone_target_alt:.2f}")
        except Exception as e:
            logging.error(f"Failed to send SET_POSITION_TARGET_GLOBAL_INT command: {e}")
