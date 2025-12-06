from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen
from PyQt6.QtCore import Qt, QSize, QPoint
import math

class AttitudeIndicatorWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pitch = 0.0 # degrees
        self.roll = 0.0 # degrees
        self.setMinimumSize(QSize(150, 150))
        self.setMaximumSize(QSize(300, 300))

    def update_attitude(self, pitch, roll):
        """
        Updates the pitch and roll for the indicator.
        Args:
            pitch (float): Pitch in degrees. Positive for nose up.
            roll (float): Roll in degrees. Positive for roll right.
        """
        self.pitch = pitch
        self.roll = roll
        self.update() # Trigger repaint

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        side = min(self.width(), self.height())
        # Ensure the indicator is centered and square
        x_offset = (self.width() - side) // 2
        y_offset = (self.height() - side) // 2
        painter.translate(x_offset, y_offset)
        
        # Scale everything to fit the square side
        scale = side / 200.0 # Base everything on a 200x200 canvas
        painter.scale(scale, scale)
        painter.translate(100, 100) # Translate to center of our 200x200 canvas

        # Save painter state for full transformations
        painter.save()

        # Apply roll rotation
        painter.rotate(-self.roll)

        # Calculate vertical shift for pitch
        # 1 degree of pitch = 2 pixels shift for a 200 unit height indicator (arbitrary scaling)
        pitch_shift = self.pitch * 2 

        # Draw sky (blue) and ground (brown)
        sky_color = QColor(0, 150, 255)
        ground_color = QColor(139, 69, 19)
        horizon_line_color = QColor(255, 255, 255) # White horizon

        painter.setBrush(QBrush(sky_color))
        painter.drawRect(-200, int(-200 + pitch_shift), 400, int(200 - pitch_shift)) # Sky portion, dynamically shifted

        painter.setBrush(QBrush(ground_color))
        painter.drawRect(-200, int(pitch_shift), 400, 200) # Ground portion, dynamically shifted

        # Draw pitch lines
        painter.setPen(QPen(horizon_line_color, 2))
        painter.drawLine(-100, int(pitch_shift), 100, int(pitch_shift)) # Horizon line

        pitch_line_color = QColor(255, 255, 255, 150) # Semi-transparent white
        painter.setPen(QPen(pitch_line_color, 1))

        # Example pitch lines (every 10 degrees)
        for i in range(-60, 61, 10): # Limit pitch lines to a reasonable range
            if i == 0: continue # Skip horizon, already drawn
            y_pos_relative_to_center = -i * 2 # 2 pixels per degree from center (0 pitch)
            y_pos = pitch_shift + y_pos_relative_to_center

            line_length = 20 if i % 30 == 0 else 10 # Longer for 30 deg marks

            painter.drawLine(-line_length, int(y_pos), line_length, int(y_pos))
            if i % 30 == 0:
                painter.drawText(-line_length - 20, int(y_pos) + 5, str(abs(i)))
                painter.drawText(line_length + 5, int(y_pos) + 5, str(abs(i)))

        # Restore painter state (undo pitch and roll transformations for fixed elements)
        painter.restore()

        # Draw fixed aircraft symbol (centered)
        aircraft_color = QColor(255, 255, 0) # Yellow
        painter.setPen(QPen(aircraft_color, 2))

        # Center dot
        painter.drawEllipse(-3, -3, 6, 6)
        # Horizontal wings
        painter.drawLine(-40, 0, -10, 0)
        painter.drawLine(10, 0, 40, 0)
        # Vertical stabilizer
        painter.drawLine(0, 10, 0, 0)
        
        # Draw roll scale (fixed arc at the top)
        roll_scale_radius = 80
        painter.setPen(QPen(QColor(200, 200, 200), 1))
        painter.drawArc(-roll_scale_radius, -roll_scale_radius, roll_scale_radius * 2, roll_scale_radius * 2, 30 * 16, 120 * 16) # Arc from -60 to +60 degrees
        
        # Roll markings on the fixed arc
        for i in range(-60, 61, 15):
            painter.save()
            painter.rotate(i)
            # Draw lines from inner to outer arc
            painter.drawLine(0, -roll_scale_radius + 5, 0, -roll_scale_radius + 15)
            # Draw text
            if i % 30 == 0 and i != 0:
                painter.drawText(-10, -roll_scale_radius + 25, str(abs(i)))
            painter.restore()

        # Draw roll indicator (triangle that rotates with roll)
        painter.save()
        painter.rotate(-self.roll) # Rotate the indicator itself
        painter.setPen(QPen(horizon_line_color, 2))
        painter.setBrush(QBrush(horizon_line_color))
        painter.drawPolygon([
            QPoint(0, -roll_scale_radius + 5), # Point up
            QPoint(-5, -roll_scale_radius - 5), # Base left
            QPoint(5, -roll_scale_radius - 5)  # Base right
        ])
        painter.restore()
        
        painter.end()