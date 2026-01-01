
import socket

class GimbalUDPSender:
    """
    A class to send gimbal control commands via UDP to a remote device.
    """
    def __init__(self, ip, port):
        """
        Initializes the UDP sender.

        Args:
            ip (str): The IP address of the target device (e.g., Raspberry Pi).
            port (int): The port on the target device to send to.
        """
        self.target_ip = ip
        self.target_port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        print(f"Gimbal UDP Sender initialized for {self.target_ip}:{self.target_port}")

    def send_error_vector(self, error_x, error_y):
        """
        Formats and sends the error vector as a UDP message.

        Args:
            error_x (float): The normalized horizontal error (-1.0 to 1.0).
            error_y (float): The normalized vertical error (-1.0 to 1.0).
        """
        try:
            # Format: ERR:x_error,y_error
            message = f"ERR:{error_x:.4f},{error_y:.4f}"
            self.sock.sendto(message.encode('utf-8'), (self.target_ip, self.target_port))
        except Exception as e:
            # This might print too frequently, but is useful for debugging initial setup
            # print(f"Error sending UDP command: {e}")
            pass

    def send_manual_command(self, axis, direction):
        """
        Formats and sends a manual gimbal control command.

        Args:
            axis (str): The axis to control ('pan' or 'tilt').
            direction (int): The direction of movement (e.g., 1 for right/up, -1 for left/down).
        """
        try:
            # Format: MAN:axis,direction
            message = f"MAN:{axis},{direction}"
            self.sock.sendto(message.encode('utf-8'), (self.target_ip, self.target_port))
        except Exception as e:
            # print(f"Error sending manual UDP command: {e}")
            pass

    def close(self):
        """Closes the socket."""
        self.sock.close()
        print("Gimbal UDP Sender socket closed.")
