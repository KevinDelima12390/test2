from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget, QInputDialog, QMessageBox
from PyQt6.QtCore import pyqtSignal

class WaypointDeployer(QWidget):
    start_mission = pyqtSignal(list)

    def __init__(self):
        super().__init__()

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
