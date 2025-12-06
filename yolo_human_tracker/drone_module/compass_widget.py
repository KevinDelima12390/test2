from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen
from PyQt6.QtCore import Qt, QSize, QPoint
import math

class CompassWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.heading = 0.0 # degrees
        self.setMinimumSize(QSize(150, 150))
        self.setMaximumSize(QSize(300, 300))

    def update_heading(self, heading):
        """
        Updates the heading for the compass.
        Args:
            heading (float): Heading in degrees (0-359.9). North is 0.
        """
        self.heading = heading
        self.update() # Trigger repaint

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        side = min(self.width(), self.height())
        x_offset = (self.width() - side) // 2
        y_offset = (self.height() - side) // 2
        painter.translate(x_offset, y_offset)
        
        scale = side / 200.0
        painter.scale(scale, scale)
        painter.translate(100, 100) # Center of our 200x200 canvas

        # Draw outer circle
        painter.setPen(QPen(QColor(100, 100, 100), 2))
        painter.setBrush(QBrush(QColor(50, 50, 50)))
        painter.drawEllipse(-90, -90, 180, 180)

        # Draw fixed markings (dial itself)
        painter.setPen(QPen(Qt.GlobalColor.white, 1))
        painter.setFont(painter.font())

        for i in range(0, 360, 5):
            painter.save()
            painter.rotate(i) # Rotate painter for each marking
            if i % 30 == 0: # Major markings
                painter.drawLine(0, -90, 0, -70)
                # Draw cardinal directions / degrees at their rotated position, then rotate back for text
                painter.save()
                painter.rotate(-i) # Rotate text back to horizontal
                if i == 0:
                    painter.drawText(-10, -75, "N")
                elif i == 90:
                    painter.drawText(75, 5, "E") # Adjusted position for E
                elif i == 180:
                    painter.drawText(-10, 80, "S")
                elif i == 270:
                    painter.drawText(-80, 5, "W") # Adjusted position for W
                else: # Intermediates like NE, SE, SW, NW
                    # Convert degrees to string, adjust position based on text width
                    text = str(i)
                    font_metrics = painter.fontMetrics()
                    text_width = font_metrics.horizontalAdvance(text)
                    painter.drawText(-text_width // 2, -75, text)
                painter.restore()
            elif i % 10 == 0: # Minor markings
                painter.drawLine(0, -90, 0, -80)
            else: # Smallest markings
                painter.drawLine(0, -90, 0, -85)
            painter.restore()

        # Draw heading indicator (triangle pointing North/0 degrees)
        painter.save()
        painter.rotate(self.heading) # Rotate the heading indicator itself

        painter.setPen(QPen(Qt.GlobalColor.red, 2))
        painter.setBrush(QBrush(Qt.GlobalColor.red))
        painter.drawPolygon([
            QPoint(0, -80),
            QPoint(-10, -60),
            QPoint(10, -60)
        ])
        painter.restore()

        painter.end()