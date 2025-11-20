import logging
from pymavlink import mavutil

class MavlinkCommunicator:
    def __init__(self, device='udpout:192.168.100.221:14550'):
        self.master = None
        self.device = device
        try:
            self.master = mavutil.mavlink_connection(self.device)
            logging.info(f"MAVLink communicator initialized for device: {self.device}")
        except Exception as e:
            logging.error(f"Failed to initialize MAVLink communicator for device {self.device}: {e}")

    def arm_disarm(self, arm):
        if not self.master:
            logging.error("MAVLink master not connected. Cannot send arm/disarm command.")
            return

        try:
            self.master.mav.command_long_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
                0, # confirmation
                1 if arm else 0, # param1: 1 to arm, 0 to disarm
                0, 0, 0, 0, 0, 0
            )
            logging.info(f"Sent {'ARM' if arm else 'DISARM'} command.")
        except Exception as e:
            logging.error(f"Failed to send arm/disarm command: {e}")

    def takeoff(self, altitude):
        if not self.master:
            logging.error("MAVLink master not connected. Cannot send takeoff command.")
            return
        try:
            self.master.mav.command_long_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
                0, 0, 0, 0, 0, 0, 0,
                altitude
            )
            logging.info(f"Sent TAKEOFF command to altitude: {altitude}m.")
        except Exception as e:
            logging.error(f"Failed to send takeoff command: {e}")

    def land(self):
        if not self.master:
            logging.error("MAVLink master not connected. Cannot send land command.")
            return
        try:
            self.master.mav.command_long_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_CMD_NAV_LAND,
                0, 0, 0, 0, 0, 0, 0, 0
            )
            logging.info("Sent LAND command.")
        except Exception as e:
            logging.error(f"Failed to send land command: {e}")

    def set_flight_mode(self, mode):
        if not self.master:
            logging.error("MAVLink master not connected. Cannot set flight mode.")
            return

        mode = mode.upper()
        if mode not in self.master.mode_mapping():
            logging.error(f"Unknown flight mode: {mode}")
            return

        mode_id = self.master.mode_mapping()[mode]
        try:
            self.master.mav.command_long_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_CMD_DO_SET_MODE,
                0, # confirmation
                mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                mode_id, 0, 0, 0, 0, 0
            )
            logging.info(f"Sent command to set flight mode to {mode}")
        except Exception as e:
            logging.error(f"Failed to set flight mode: {e}")

    def run_diagnostics(self):
        if not self.master:
            logging.error("MAVLink master not connected. Cannot run diagnostics.")
            return False

        try:
            self.master.mav.param_request_read_send(
                self.master.target_system,
                self.master.target_component,
                b'SYSID_THISMAV',
                -1
            )

            # Wait for the response
            message = self.master.recv_match(type='PARAM_VALUE', blocking=True, timeout=3)

            if message:
                logging.info(f"Diagnostics check PASSED. Received param {message.param_id} with value {message.param_value}")
                return True
            else:
                logging.error("Diagnostics check FAILED. No PARAM_VALUE message received.")
                return False
        except Exception as e:
            logging.error(f"An error occurred during diagnostics: {e}")
            return False

    def send_gimbal_command(self, pitch, roll, yaw):
        if not self.master:
            logging.error("MAVLink master not connected. Cannot send gimbal command.")
            return

        try:
            # MAV_CMD_DO_MOUNT_CONTROL
            # param1: pitch (degrees)
            # param2: roll (degrees)
            # param3: yaw (degrees)
            # param7: mount mode (MAV_MOUNT_MODE_MAVLINK_TARGETING for example)
            self.master.mav.command_long_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_CMD_DO_MOUNT_CONTROL,
                0, # confirmation
                pitch,
                roll,
                yaw,
                0, 0, 0, # unused params
                mavutil.mavlink.MAV_MOUNT_MODE_MAVLINK_TARGETING # Mount mode
            )
            logging.info(f"Sent gimbal command: Pitch={pitch}, Roll={roll}, Yaw={yaw}")
        except Exception as e:
            logging.error(f"Failed to send gimbal command: {e}")