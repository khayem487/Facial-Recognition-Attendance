import base64
import os
from datetime import datetime

import cv2
import numpy as np
from flask import Flask, jsonify, render_template, request

# Optional dependency: full recognition mode
try:
    import face_recognition  # type: ignore
except Exception:
    face_recognition = None

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGE_DIR = os.path.join(BASE_DIR, "imageAttendance")
ATTENDANCE_FILE = os.path.join(BASE_DIR, "attendance.csv")
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp")


def load_known_images(path: str):
    images = []
    names = []

    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)

    for filename in os.listdir(path):
        if not filename.lower().endswith(IMAGE_EXTENSIONS):
            continue

        image_path = os.path.join(path, filename)
        image = cv2.imread(image_path)
        if image is None:
            print(f"[WARN] Could not load image: {filename}")
            continue

        images.append(image)
        names.append(os.path.splitext(filename)[0])

    return images, names


def find_encodings(images):
    encodings = []

    if face_recognition is None:
        return encodings

    for img in images:
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        encoded = face_recognition.face_encodings(rgb)
        if not encoded:
            continue
        encodings.append(encoded[0])

    return encodings


def mark_attendance(name: str):
    file_exists = os.path.exists(ATTENDANCE_FILE)

    with open(ATTENDANCE_FILE, "a+", encoding="utf-8") as f:
        if not file_exists:
            f.write("Name;Time\n")

        now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        f.write(f"{name};{now}\n")


KNOWN_IMAGES, KNOWN_NAMES = load_known_images(IMAGE_DIR)
KNOWN_ENCODINGS = find_encodings(KNOWN_IMAGES)

CASCADE_PATH = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
FACE_CASCADE = cv2.CascadeClassifier(CASCADE_PATH)

FULL_MODE = face_recognition is not None and len(KNOWN_ENCODINGS) > 0
print(f"[INFO] Facial app started in {'recognition' if FULL_MODE else 'fallback'} mode")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/mark_attendance_page")
def mark_attendance_page():
    return render_template("mark_attendance_page.html")


@app.route("/create_user")
def create_user():
    return render_template("create_user.html")


@app.route("/health")
def health():
    return jsonify(
        {
            "status": "ok",
            "mode": "recognition" if FULL_MODE else "fallback",
            "known_faces": len(KNOWN_NAMES),
        }
    )


@app.route("/process_frame", methods=["POST"])
def process_frame():
    data = request.get_json(silent=True) or {}
    frame_data = data.get("frame")

    if not frame_data or "," not in frame_data:
        return jsonify(success=False, error="invalid_frame"), 400

    try:
        encoded_part = frame_data.split(",", 1)[1]
        frame_bytes = base64.b64decode(encoded_part)
        np_frame = np.frombuffer(frame_bytes, np.uint8)
        frame = cv2.imdecode(np_frame, cv2.IMREAD_COLOR)
    except Exception:
        return jsonify(success=False, error="decode_failed"), 400

    if frame is None:
        return jsonify(success=False, error="empty_frame"), 400

    # Full recognition path (if face_recognition is available and encodings exist)
    if FULL_MODE:
        small = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
        rgb_small = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)

        face_locations = face_recognition.face_locations(rgb_small)
        face_encodings = face_recognition.face_encodings(rgb_small, face_locations)

        for face_encoding in face_encodings:
            matches = face_recognition.compare_faces(KNOWN_ENCODINGS, face_encoding)
            face_distances = face_recognition.face_distance(KNOWN_ENCODINGS, face_encoding)

            if len(face_distances) == 0:
                continue

            best_match_index = int(np.argmin(face_distances))
            if matches[best_match_index]:
                name = KNOWN_NAMES[best_match_index].upper()
                mark_attendance(name)
                return jsonify(success=True, name=name, mode="recognition")

    # Fallback path: detect face(s) using Haar cascade
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    detected = FACE_CASCADE.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))

    if len(detected) > 0:
        name = KNOWN_NAMES[0].upper() if KNOWN_NAMES else "VISITOR"
        mark_attendance(name)
        return jsonify(success=True, name=name, mode="fallback")

    return jsonify(success=False, mode="none")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
