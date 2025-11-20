
import cv2

pipeline = (
    "udpsrc port=5600 caps=application/x-rtp,media=(string)video,"
    "clock-rate=(int)90000,encoding-name=(string)H264 ! "
    "rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! appsink"
)

print("Opening video stream...")
cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)

if not cap.isOpened():
    print("❌ Failed to open stream. GStreamer not linked to OpenCV or port busy.")
    exit(1)

print("✅ Stream opened. Reading frames...")
while True:
    ret, frame = cap.read()
    if not ret:
        print("⚠️ No frame received. Retrying...")
        continue
    cv2.imshow("Video Stream Test", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
EOF
