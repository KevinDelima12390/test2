from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QGridLayout
from PyQt6.QtCore import pyqtSignal

class GimbalControl(QWidget):
    gimbal_command = pyqtSignal(str, int)

    def __init__(self):
        super().__init__()

        self.pan = 0
        self.tilt = 0

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
