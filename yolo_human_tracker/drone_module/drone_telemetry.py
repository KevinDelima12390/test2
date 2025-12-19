import logging
import threading
import time
from pymavlink import mavutil

class DroneTelemetryListener(threading.Thread):
    def __init__(self, telemetry_callback=None):
        super().__init__()
        self.daemon = True  # Daemonize thread to exit when main program exits
        self.telemetry_callback = telemetry_callback
        self._stop_event = threading.Event()
        self.latest_telemetry = {}
        self.mav_conn = None

    def stop(self):
        self._stop_event.set()

    def get_latest_telemetry(self):
        return self.latest_telemetry.copy()

    def run(self):
        logging.info("Starting MAVLink telemetry listener...")
        
        while not self._stop_event.is_set():
            if self.mav_conn is None:
                try:
                    logging.info("Attempting to connect to MAVLink on udp:127.0.0.1:14552")
                    self.mav_conn = mavutil.mavlink_connection('udp:127.0.0.1:14552')
                    logging.info("MAVLink connection established.")
                except Exception as e:
                    logging.error(f"Failed to start MAVLink listener: {e}")
                    self.mav_conn = None
                    time.sleep(5) # Wait before retrying
                    continue

            # Wait for a new message
            msg = self.mav_conn.recv_match(type=['GLOBAL_POSITION_INT', 'SYS_STATUS', 'RC_CHANNELS', 'HEARTBEAT', 'ATTITUDE'], blocking=True, timeout=1.0)
            if msg is None:
                continue

            processed_data = {"type": "telemetry"}
            msg_type = msg.get_type()

            if msg_type == 'HEARTBEAT':
                processed_data.update({"status": "drone_connected"})

            elif msg_type == 'GLOBAL_POSITION_INT':
                # Process the message
                lat = msg.lat / 1e7
                lon = msg.lon / 1e7
                alt = msg.relative_alt / 1000  # Relative altitude in meters
                ground_speed = msg.vx / 100.0 # Ground speed in m/s

                processed_data.update({
                    "latitude": lat,
                    "longitude": lon,
                    "altitude": alt,
                    "ground_speed": ground_speed,
                })

            elif msg_type == 'ATTITUDE':
                processed_data.update({
                    "heading": msg.yaw, # Yaw in radians
                    "pitch": msg.pitch, # Pitch in radians
                    "roll": msg.roll # Roll in radians
                })

            elif msg_type == "SYS_STATUS":
                armed = bool(msg.onboard_control_sensors_present & mavutil.mavlink.MAV_SYS_STATUS_SENSOR_MOTOR_OUTPUTS)
                processed_data.update({
                    "battery_voltage": msg.voltage_battery / 1000.0,
                    "battery_current": msg.current_battery / 100.0,
                    "battery_remaining": msg.battery_remaining,
                    "armed": armed,
                })

            elif msg_type == "RC_CHANNELS":
                processed_data.update({
                    "signal_strength": msg.rssi
                })

            if self.telemetry_callback:
                self.telemetry_callback(processed_data)
            
            # Update the latest telemetry data
            self.latest_telemetry.update(processed_data)
            
        logging.info("MAVLink telemetry listener stopped.")

if __name__ == '__main__':
    import time

    logging.basicConfig(level=logging.INFO)

    def my_telemetry_handler(data):
        print(f"Received processed telemetry: {data}")

    # Create and start the listener
    listener = DroneTelemetryListener(telemetry_callback=my_telemetry_handler)
    listener.start()

    try:
        # Keep the main thread alive to see the output
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping listener...")
        listener.stop()
        listener.join() # Wait for the thread to finish
        print("Listener stopped.")