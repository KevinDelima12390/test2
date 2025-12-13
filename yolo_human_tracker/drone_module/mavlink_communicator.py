import logging
from pymavlink import mavutil
from pymavlink.dialects.v10 import common as mavlink_common

# No need to call mavutil.set_dialect("common") explicitly if importing from the dialect directly
# mavutil.set_dialect("common")

class MavlinkCommunicator:
    def __init__(self, device='udp:127.0.0.1:14551'):
        self.master = None
        self.device = device
        try:
            # When connecting, mavutil will typically load the dialect from the first XML it finds,
            # or from environment variables. By explicitly calling mavlink_common later, we ensure
            # those definitions are used.
            self.master = mavutil.mavlink_connection(self.device)
            if self.master is None:
                logging.error(f"Failed to establish MAVLink connection to {self.device}. `self.master` is None.")
                return

            # Wait for the first heartbeat to confirm the connection
            logging.info("Waiting for MAVLink heartbeat...")
            self.master.wait_heartbeat()
            logging.info("MAVLink heartbeat received!")
            
            # Set gimbal mode to MAVLink Targeting
            self.set_gimbal_mode()
            
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

    def set_gimbal_mode(self):
        if not self.master:
            logging.error("MAVLink master not connected. Cannot set gimbal mode.")
            return

        try:
            self.master.mav.command_long_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_CMD_DO_MOUNT_CONTROL,
                0,  # confirmation
                0.0,  # param1: Roll (ignored)
                0.0,  # param2: Pitch (ignored)
                0.0,  # param3: Yaw (ignored)
                0.0,  # param4: extra (ignored)
                0.0,  # param5: extra (ignored)
                0.0,  # param6: extra (ignored)
                2   # param7: Mount Mode (2 = MAVLink Targeting)
            )
            logging.info("Gimbal mode command sent: Switched to MAVLink Targeting (Mode 2)")
        except Exception as e:
            logging.error(f"Failed to send gimbal mode command: {e}")

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



    # def send_gimbal_manager_set_manual_control(self, pitch_rate, yaw_rate,
    #                                            target_system=255, target_component=190, # From upgrade_context
    #                                            flags=0, # Corrected: Set to 0 for no special flags
    #                                            gimbal_device_id=0): # Assuming gimbal ID 0

    #     if not self.master:
    #         logging.error("MAVLink master not connected. Cannot send GIMBAL_MANAGER_SET_MANUAL_CONTROL command.")
    #         return

    #     try:
    #         # According to upgrade_context, we need to use MAV_FRAME_BODY_YAW_TO_BASE_LINK for pitch/yaw.
    #         # MAV_FRAME_BODY_YAW implies relative to vehicle body, which aligns with 'FRAME_BODY_YAW'
    #         # in the context for rotation around the body axes.

    #         # GIMBAL_MANAGER_SET_MANUAL_CONTROL message parameters:
    #         # target_system (uint8_t): System ID
    #         # target_component (uint8_t): Component ID
    #         # flags (uint32_t): High level gimbal manager flags.
    #         # gimbal_device_id (uint8_t): Component ID of gimbal device to address (or 1-6 for typical gimbals, 0 for all)
    #         # pitch (float): Pitch angle (rad). Zero when pointing to the horizon.
    #         # yaw (float): Yaw angle (rad). Zero when pointing forward.
    #         # pitch_rate (float): Pitch rate (rad/s)
    #         # yaw_rate (float): Yaw rate (rad/s)
    #         # This command uses rates, so pitch and yaw angles themselves are not directly set here.
    #         # We are providing rates, so pitch and yaw should be 0.
            
    #         # The context implies pitch_yaw_frame: GIMBAL_MANAGER_FLAGS_FRAME_BODY_YAW.
    #         # This is not a direct field in the GIMBAL_MANAGER_SET_MANUAL_CONTROL message,
    #         # but rather a flag for the GIMBAL_MANAGER_SET_ATTITUDE message or implied by the control.
    #         # The GIMBAL_MANAGER_FLAGS_FRAME_BODY_YAW is part of the 'flags' field for SET_ATTITUDE,
    #         # but for SET_MANUAL_CONTROL, the rates are typically relative to the body frame.
    #         # Let's adjust flags based on context if necessary.
            
    #         # For GIMBAL_MANAGER_SET_MANUAL_CONTROL, rates are usually relative to the body frame.
    #         # The 'flags' field in SET_MANUAL_CONTROL is more about control options like "retract", "neutral", "sweep".
    #         # The upgrade_context says "pitch_yaw_frame": "GIMBAL_MANAGER_FLAGS_FRAME_BODY_YAW"
    #         # This flag value refers to the frame of reference for pitch and yaw angles in GIMBAL_MANAGER_SET_ATTITUDE.
    #         # For SET_MANUAL_CONTROL, the rates are inherently relative to the gimbal's current orientation/body frame.
    #         # So, for flags, we'll use a combination that makes sense for continuous control.
            
    #         # Let's use 0 for flags to signify direct rate control without special actions,
    #         # or a combination that aligns with continuous tracking if available.
    #         # The 'control_type': 'AngularRate' and 'angular_rate_units': 'rad/s' are implicitly handled by this message.

    #         # From the context, MAVLink message type is GIMBAL_MANAGER_SET_MANUAL_CONTROL
    #         # and control_type is AngularRate.
    #         # So we send the rates.
            
    #         # Note: mavutil.mavlink.GIMBAL_MANAGER_FLAGS_RETRACT | mavutil.mavlink.GIMBAL_MANAGER_FLAGS_NEUTRAL | mavutil.mavlink.GIMBAL_MANAGER_FLAGS_SWEEP | mavutil.mavlink.GIMBAL_MANAGER_FLAGS_CALIBRATION
    #         # These are typically not set for a continuous follow command.
    #         # A flag for "enable/disable continuous control" might be implied or a specific value.
    #         # For now, I will use flags=0 (no special actions), or if a direct rate control flag exists, use that.
    #         # Looking at MAVLink definition, GIMBAL_MANAGER_SET_MANUAL_CONTROL doesn't have a 'frame' field for rates,
    #         # as rates are inherently relative to the gimbal's current orientation.
    #         # The flags are usually for high-level commands, not for setting the reference frame of rates.
    #         # Let's use 0 for flags initially and revisit if behavior is not as expected.
            
    #         # However, the context specifically mentions 'pitch_yaw_frame': 'GIMBAL_MANAGER_FLAGS_FRAME_BODY_YAW'
    #         # which is confusing as it's a flag for SET_ATTITUDE, not SET_MANUAL_CONTROL.
    #         # Given the request, I will try to incorporate a flag if it fits, but the message itself for rates
    #         # does not usually have a frame.

    #         # Re-reading MAVLink common.xml for GIMBAL_MANAGER_SET_MANUAL_CONTROL:
    #         # target_system, target_component, flags, gimbal_device_id, pitch_rate_rad, yaw_rate_rad, roll_rate_rad
    #         # The flags are: GIMBAL_MANAGER_FLAGS_RETRACT, GIMBAL_MANAGER_FLAGS_NEUTRAL, GIMBAL_MANAGER_FLAGS_SWEEP, GIMBAL_MANAGER_FLAGS_CALIBRATION
    #         # So the 'pitch_yaw_frame' in context might be a misinterpretation or implies a custom usage.
    #         # For now, I will use flags=0 to avoid conflicting actions.

    #         # The upgrade_context specifies system_id=255 and component_id=190 for the drone.
    #         # Let's use those for target_system and target_component.

    #         message = mavutil.mavlink.MAVLink_gimbal_manager_set_manual_control_message(
    #             target_system=target_system,
    #             target_component=target_component,
    #             flags=flags,
    #             gimbal_device_id=gimbal_device_id,
    #             pitch=0.0,
    #             yaw=0.0,
    #             pitch_rate=pitch_rate,
    #             yaw_rate=yaw_rate
    #         )
    #         self.master.mav.send(message)
    #         logging.info(f"Sent GIMBAL_MANAGER_SET_MANUAL_CONTROL: Pitch Rate={pitch_rate:.2f} rad/s, Yaw Rate={yaw_rate:.2f} rad/s")
    #     except Exception as e:
    #         logging.error(f"Failed to send GIMBAL_MANAGER_SET_MANUAL_CONTROL command: {e}")