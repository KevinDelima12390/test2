from flask import Flask, render_template, jsonify
import threading
import webbrowser
import time

app = Flask(__name__)

# default coordinates
coords = {"lat": 3.1275, "lon": 101.6579}
waypoints = [] # Store waypoints

@app.route("/")
def index():
    return render_template("map.html")

@app.route("/coords")
def get_coords():
    print(f"[MAP_SERVER] Returning coordinates: {coords}")
    return jsonify(coords=coords, waypoints=waypoints)

@app.route("/update/<float:lat>/<float:lon>")
def update_coords(lat, lon):
    coords["lat"], coords["lon"] = lat, lon
    print(f"[MAP_SERVER] Updated coordinates to: Lat={lat}, Lon={lon}")
    return jsonify(success=True)

@app.route("/add_waypoint/<float:lat>/<float:lon>")
def add_waypoint(lat, lon):
    waypoints.append({"lat": lat, "lon": lon})
    print(f"[MAP_SERVER] Added waypoint: Lat={lat}, Lon={lon}")
    return jsonify(success=True)

@app.route("/clear_waypoints")
def clear_waypoints():
    waypoints.clear()
    print("[MAP_SERVER] Cleared all waypoints.")
    return jsonify(success=True)

def run_flask_app():
    app.run(host="0.0.0.0", port=5050)

if __name__ == "__main__":
    # Start Flask in a separate thread
    flask_thread = threading.Thread(target=run_flask_app)
    flask_thread.daemon = True
    flask_thread.start()

    # Give the server a moment to start
    time.sleep(1)

    # Open the map in a web browser
    webbrowser.open("http://127.0.0.1:5050")