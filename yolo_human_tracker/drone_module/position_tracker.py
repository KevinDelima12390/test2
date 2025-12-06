import math
import numpy as np
from pymavlink import mavutil
import logging

class PositionTracker:
    def __init__(self, mavlink_communicator=None):
        self.mavlink_communicator = mavlink_communicator
        # Hardcoded camera FOV for now (example values)
        self.camera_fov_h_deg = 60 # Horizontal FOV in degrees
        self.camera_fov_v_deg = 45 # Vertical FOV in degrees

    def get_target_gnss(self, screen_x, screen_y, frame_width, frame_height,
                        drone_lat, drone_lon, drone_alt, # drone_alt is relative altitude in meters
                        drone_heading, drone_pitch, drone_roll): # drone attitude in radians
        """
        Converts screen coordinates of a target to approximate GNSS coordinates (Lat, Lon, Alt).
        This uses a simplified camera-to-world projection with a flat earth approximation.

        :param screen_x: X coordinate of target center in pixels (0 to frame_width-1)
        :param screen_y: Y coordinate of target center in pixels (0 to frame_height-1)
        :param frame_width: Width of the video frame in pixels
        :param frame_height: Height of the video frame in pixels
        :param drone_lat: Drone's current latitude (degrees)
        :param drone_lon: Drone's current longitude (degrees)
        :param drone_alt: Drone's current relative altitude (meters)
        :param drone_heading: Drone's yaw/heading (radians, 0 = North, positive clockwise)
        :param drone_pitch: Drone's pitch (radians, positive nose up)
        :param drone_roll: Drone's roll (radians, positive right wing down)
        :return: (target_lat, target_lon, target_alt) in degrees and meters, or (None, None, None) if calculation fails
        """
        if any(v is None for v in [drone_lat, drone_lon, drone_alt, drone_heading, drone_pitch, drone_roll]):
            logging.warning("Missing drone telemetry for target GNSS calculation.")
            return None, None, None

        # 1. Calculate angles to target from camera center
        # Normalized coordinates from -1 to 1, where (0,0) is center of frame
        norm_x = (screen_x - frame_width / 2) / (frame_width / 2)
        norm_y = (screen_y - frame_height / 2) / (frame_height / 2)

        # Convert FOV from degrees to radians
        fov_h_rad = math.radians(self.camera_fov_h_deg)
        fov_v_rad = math.radians(self.camera_fov_v_deg)

        # Angular displacement from camera's optical axis
        angle_x = norm_x * (fov_h_rad / 2) # Angle left/right from center
        angle_y = norm_y * (fov_v_rad / 2) # Angle up/down from center

        # 2. Correct for gimbal/camera orientation relative to drone body (assuming fixed camera)
        # Assuming camera is fixed pointing forward on drone body.
        # drone_pitch (nose up is positive, camera looks down when pitch is negative)
        # drone_roll (right wing down is positive)
        # drone_heading (yaw, 0=North, positive clockwise)

        # These are angles relative to camera's optical axis. We need to convert them to
        # angles in the drone's body frame, then to the NED/ENU frame.

        # For simplicity, let's assume camera's optical axis is perfectly aligned with drone body
        # and we directly apply drone's attitude to the target angles.
        # This is a simplification and would need a proper rotation matrix for more accuracy.

        # Yaw, Pitch, Roll from drone's attitude (radians)
        # Yaw is heading, Pitch is rotation around Y-axis, Roll is rotation around X-axis
        
        # Angle from drone's forward direction to target in horizontal plane
        # And angle down from drone's horizon to target in vertical plane

        # Combined pitch and yaw relative to drone's body frame
        # If drone pitches down, target moves up in frame (negative angle_y)
        # If drone yaws right, target moves left in frame (negative angle_x)

        # Assuming camera is looking forward.
        # pitch_from_drone_horizontal = angle_y - drone_pitch # Corrected vertical angle
        # yaw_from_drone_forward = angle_x - drone_roll # Corrected horizontal angle

        # More robust approach: Convert to vector in camera frame, then rotate to body, then to NED/ENU.
        # Simplified vector in camera frame (z-axis is forward, x-right, y-down)
        # This is a unit vector for simplicity, magnitude doesn't matter for direction
        target_cam_x = math.tan(angle_x)
        target_cam_y = math.tan(angle_y)
        target_cam_z = 1 # Assuming looking forward

        # Apply inverse of drone's attitude (roll, pitch, yaw) to rotate target vector
        # from camera frame to NED (North-East-Down) frame.
        # MAVLink attitude gives roll, pitch, yaw, which is rotation from NED to body frame.
        # We need to rotate from camera frame to body frame, then body to NED frame.
        # Assuming camera frame == body frame for now. So we need inverse rotation (NED to body).

        # Rotation matrix from body to NED (from drone's attitude)
        R_body_to_ned = self._rotation_matrix_from_euler(drone_roll, drone_pitch, drone_heading)

        # Target vector in body frame (assuming camera aligned with body)
        target_body_vec = np.array([target_cam_z, -target_cam_x, -target_cam_y]) # x-forward, y-left, z-up

        # Rotate target vector from body frame to NED frame
        target_ned_vec = R_body_to_ned @ target_body_vec
        
        # Horizontal distance and bearing
        horizontal_distance_m = drone_alt / target_ned_vec[2] # target_ned_vec[2] is down component
                                                             # Assuming target is at ground level or drone_alt is height *above target*.
                                                             # This is the biggest simplification.
                                                             # If target is at drone_alt, this won't work well.
                                                             # Let's assume target_alt is 0 (ground) for now, relative to drone's launch point.
                                                             # This means target_ned_vec[2] should be positive for target to be below drone.

        # If target_ned_vec[2] is very small or negative (target above or near horizon), cannot calculate.
        if target_ned_vec[2] <= 0.01: # Avoid division by zero and handle target above horizon
            logging.warning("Target is above or at drone's horizon. Cannot calculate ground position.")
            return None, None, None

        # Re-evaluating target altitude:
        # For drone follow, we ideally want to follow a person on the ground.
        # So, the target's relative altitude (target_alt_relative_to_sea)
        # is usually much less than the drone's relative altitude.
        # Let's assume the target is at altitude 0 relative to the ground for now,
        # which means the altitude difference is simply drone_alt.
        
        # If we need target altitude, it means the drone is trying to estimate the
        # target's absolute altitude from the image. This is not VIO but rather
        # structure from motion or stereo vision.
        # Given we only have 2D screen coords and drone attitude, we must assume
        # target_alt relative to drone's frame or ground.
        # The simplest is to assume target is on the ground plane below the drone.
        # In this case, the distance to target (hypotenuse) is distance from drone to target on ground
        # divided by cos(angle_down).
        # We need the vertical angle below the horizontal plane of the drone.
        
        # Angle from drone's horizontal plane to the target (positive downwards)
        # This would be `math.atan2(target_ned_vec[2], math.sqrt(target_ned_vec[0]**2 + target_ned_vec[1]**2))`
        # This is essentially the depression angle of the target from the drone's horizontal.
        
        # A simpler approach: calculate target position in local ENU, then convert to GPS.
        # Local coordinates (East, North, Up) from drone
        # This vector is relative to drone's position, in NED frame.
        # North (x), East (y), Down (z)

        # Target is at depth 'D' from camera.
        # screen_x, screen_y -> pixel offsets.
        # FOV -> angle per pixel.

        # Target's direction in camera frame (e.g., OpenCV, x-right, y-down, z-forward)
        theta_yaw_rel_cam = math.atan2(norm_x * math.tan(fov_h_rad / 2), 1)
        theta_pitch_rel_cam = math.atan2(norm_y * math.tan(fov_v_rad / 2), 1)

        # Now, incorporate drone's attitude.
        # Angles from drone's forward direction in NED frame
        # Total yaw: drone_heading + theta_yaw_rel_cam
        # Total pitch: drone_pitch + theta_pitch_rel_cam

        # For a target on the ground (altitude 0 relative to ground plane),
        # the angle of depression `alpha` from the drone's horizontal.
        # `drone_alt = horizontal_distance * tan(alpha)`
        # `horizontal_distance = drone_alt / tan(alpha)`
        
        # The angle `alpha` can be calculated from drone_pitch and theta_pitch_rel_cam.
        # Vertical angle of optical axis below horizontal = -drone_pitch (if drone_pitch is positive nose up)
        # So, depression_angle_of_target = -drone_pitch + theta_pitch_rel_cam
        # However, theta_pitch_rel_cam is relative to camera's axis, not drone's horizontal.
        # Let's consider `drone_pitch` and `drone_roll` directly to find horizon.

        # Let's use the vector rotation approach again, but assuming target_alt is same as drone_alt for now.
        # This will mean the drone will try to position itself above the target at a certain height.
        
        # Determine the target's relative position (North, East, Down) from the drone
        # based on drone's altitude and the angles to the target from the drone.
        
        # Angle of the target in the horizontal plane relative to drone's heading (East of North)
        relative_yaw_angle = drone_heading + angle_x # Simplified: assuming camera's optical axis is perfectly aligned with drone's forward direction for yaw.
        
        # Angle of the target in the vertical plane relative to drone's horizontal (Down from Horizontal)
        # For a downward looking camera (pitch is usually negative or 0 for level flight)
        # A positive angle_y means target is lower in image (more down).
        # A positive drone_pitch means nose up.
        # So, actual_pitch_angle_to_target = -drone_pitch + angle_y (if drone_pitch is positive nose up, target moves down)
        
        # This approach is too simplistic. Let's use standard transformations.
        
        # Coordinate Systems:
        # Camera Frame (Xc, Yc, Zc): Zc-forward, Xc-right, Yc-down
        # Body Frame (Xb, Yb, Zb): Xb-forward, Yb-right, Zb-down
        # NED Frame (Xn, Ye, Zd): Xn-North, Ye-East, Zd-Down
        # ECEF Frame
        # WGS84 (Lat, Lon, Alt)

        # Step 1: Target vector in Camera Frame (P_c)
        # Assuming focal length f = 1 for simplicity of angular calculations
        P_c = np.array([
            math.tan(angle_x),
            math.tan(angle_y),
            1.0 # This is Z_c, target is "in front" of camera
        ])

        # Step 2: Rotate P_c to Body Frame (P_b)
        # Assuming camera is perfectly aligned with body, so P_b = P_c

        # Step 3: Rotate P_b to NED Frame (P_n)
        # Euler angles from MAVLink: roll, pitch, yaw (drone_roll, drone_pitch, drone_heading) are rotations from NED to Body.
        # We need the inverse rotation: Body to NED.
        R_ned_to_body = self._rotation_matrix_from_euler(drone_roll, drone_pitch, drone_heading)
        R_body_to_ned = R_ned_to_body.T # Transpose is inverse for rotation matrices

        P_n = R_body_to_ned @ P_c
        P_n = P_n / np.linalg.norm(P_n) # Normalize to unit vector

        # P_n is a unit vector pointing from drone to target in NED frame.
        # P_n = [North, East, Down]

        # Step 4: Calculate distance to target. This is the hardest part without depth.
        # The upgrade context does not specify how target altitude should be estimated.
        # Let's assume the target is on the ground, so target_alt_relative_to_sea = 0 (or a fixed value).
        # And drone_alt is relative to ground.
        
        # If target is on the ground (target_alt_relative_to_ground = 0),
        # then the vertical distance from drone to target_ground_plane is drone_alt.
        # The 'Down' component of P_n (P_n[2]) gives the cosine of the angle of depression
        # if the vector was normalized by depth.
        
        # vertical_distance = drone_alt
        # P_n[2] is positive when target is below.
        
        # Let's use the simplest and most common assumption for "person on ground":
        # The target is on the ground (altitude 0 relative to where the drone considers its 'ground').
        # The drone's altitude (`drone_alt`) is relative to this ground.
        # So, `target_down_component_relative_to_drone = drone_alt`.
        # The vector P_n is a unit vector. To scale it to real-world distances:
        
        if P_n[2] <= 0.01: # Target is above or at horizon
            logging.warning("Target is above or at drone's horizon. Cannot calculate ground position.")
            return None, None, None

        # Scale factor (distance to target along the P_n vector)
        distance_scale = drone_alt / P_n[2]
        
        # Relative position in NED (North, East, Down) from drone
        delta_north = P_n[0] * distance_scale
        delta_east = P_n[1] * distance_scale
        delta_down = P_n[2] * distance_scale # This should be approximately drone_alt

        target_alt_relative = drone_alt - delta_down # Should be ~0 if target is on ground.
                                                      # This would be target's altitude relative to drone's launch point.
        
        # Step 5: Convert relative NED to Lat/Lon
        target_lat, target_lon = self._add_vectors_to_gps(drone_lat, drone_lon, delta_north, delta_east)
        
        return target_lat, target_lon, target_alt_relative # target_alt_relative is relative to drone's start altitude

    def _rotation_matrix_from_euler(self, roll, pitch, yaw):
        """
        Generates a 3x3 rotation matrix from Euler angles (roll, pitch, yaw).
        Rotations are typically applied in yaw, then pitch, then roll order.
        This matrix transforms vectors from body frame to NED frame.
        """
        cr = math.cos(roll)
        sr = math.sin(roll)
        cp = math.cos(pitch)
        sp = math.sin(pitch)
        cy = math.cos(yaw)
        sy = math.sin(yaw)

        R = np.array([
            [cy*cp, cy*sp*sr - sy*cr, cy*sp*cr + sy*sr],
            [sy*cp, sy*sp*sr + cy*cr, sy*sp*cr - cy*sr],
            [-sp, cp*sr, cp*cr]
        ])
        return R

    def _add_vectors_to_gps(self, lat, lon, delta_north, delta_east):
        """
        Adds a North and East vector (in meters) to a given GPS coordinate
        using a flat-earth approximation.

        :param lat: Reference latitude in degrees
        :param lon: Reference longitude in degrees
        :param delta_north: Distance to add in North direction (meters)
        :param delta_east: Distance to add in East direction (meters)
        :return: (new_lat, new_lon) in degrees
        """
        # Earth's radius in meters (mean radius)
        R_earth = 6371000.0

        # Convert latitude to radians
        lat_rad = math.radians(lat)

        # Calculate new latitude
        new_lat_rad = lat_rad + (delta_north / R_earth)
        new_lat = math.degrees(new_lat_rad)

        # Calculate new longitude
        # The circumference of the Earth at a given latitude is R_earth * cos(lat_rad)
        new_lon_rad = math.radians(lon) + (delta_east / (R_earth * math.cos(lat_rad)))
        new_lon = math.degrees(new_lon_rad)

        return new_lat, new_lon
