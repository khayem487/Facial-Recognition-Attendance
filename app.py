import base64
import csv
import os
import re
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
USERS_FILE = os.path.join(BASE_DIR, "users.csv")
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp")
ATTENDANCE_COOLDOWN_SECONDS = 20

CASCADE_PATH = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
FACE_CASCADE = cv2.CascadeClassifier(CASCADE_PATH)

KNOWN_USERS = []
LAST_MARKS = {}
FULL_MODE = False


def ensure_storage():
    os.makedirs(IMAGE_DIR, exist_ok=True)

    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "key",
                    "name",
                    "user_id",
                    "mobile",
                    "designation",
                    "salary",
                    "image_file",
                    "created_at",
                ],
                delimiter=";",
            )
            writer.writeheader()


def safe_slug(value: str) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def decode_data_url(data_url: str):
    if not data_url or "," not in data_url:
        return None

    try:
        encoded = data_url.split(",", 1)[1]
        frame_bytes = base64.b64decode(encoded)
        np_frame = np.frombuffer(frame_bytes, dtype=np.uint8)
        frame = cv2.imdecode(np_frame, cv2.IMREAD_COLOR)
        return frame
    except Exception:
        return None


def detect_faces(frame_bgr):
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    faces = FACE_CASCADE.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(60, 60),
    )
    if len(faces) == 0:
        return []
    return sorted(faces, key=lambda box: box[2] * box[3], reverse=True)


def crop_face(frame_bgr, box, pad_ratio=0.2):
    x, y, w, h = [int(v) for v in box]
    pad_x = int(w * pad_ratio)
    pad_y = int(h * pad_ratio)

    x1 = max(0, x - pad_x)
    y1 = max(0, y - pad_y)
    x2 = min(frame_bgr.shape[1], x + w + pad_x)
    y2 = min(frame_bgr.shape[0], y + h + pad_y)

    if x2 <= x1 or y2 <= y1:
        return None

    return frame_bgr[y1:y2, x1:x2]


def extract_best_face(frame_bgr):
    faces = detect_faces(frame_bgr)
    if not faces:
        return None, None

    best = faces[0]
    face_crop = crop_face(frame_bgr, best)
    if face_crop is None:
        return None, None

    return face_crop, best


def compute_face_signature(face_bgr):
    gray = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, (128, 128))
    hist = cv2.calcHist([gray], [0], None, [64], [0, 256])
    hist = cv2.normalize(hist, hist).flatten()
    return hist


def load_users_metadata():
    if not os.path.exists(USERS_FILE):
        return {}

    data = {}
    with open(USERS_FILE, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            key = (row.get("key") or "").strip()
            if key:
                data[key] = row
    return data


def save_users_metadata(rows):
    with open(USERS_FILE, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "key",
                "name",
                "user_id",
                "mobile",
                "designation",
                "salary",
                "image_file",
                "created_at",
            ],
            delimiter=";",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def upsert_user_metadata(record):
    all_rows = load_users_metadata()
    all_rows[record["key"]] = record
    save_users_metadata(list(all_rows.values()))


def build_known_users():
    metadata = load_users_metadata()
    users = []

    for filename in os.listdir(IMAGE_DIR):
        if not filename.lower().endswith(IMAGE_EXTENSIONS):
            continue

        image_path = os.path.join(IMAGE_DIR, filename)
        image = cv2.imread(image_path)
        if image is None:
            print(f"[WARN] Could not load image: {filename}")
            continue

        key = os.path.splitext(filename)[0]
        face_crop, _ = extract_best_face(image)
        reference = face_crop if face_crop is not None else image

        signature = compute_face_signature(reference)
        encoding = None

        if face_recognition is not None:
            try:
                rgb = cv2.cvtColor(reference, cv2.COLOR_BGR2RGB)
                encoded = face_recognition.face_encodings(rgb)
                if encoded:
                    encoding = encoded[0]
            except Exception:
                encoding = None

        row = metadata.get(key, {})
        display_name = (row.get("name") or key).strip()

        users.append(
            {
                "key": key,
                "name": display_name,
                "user_id": (row.get("user_id") or "").strip(),
                "mobile": (row.get("mobile") or "").strip(),
                "designation": (row.get("designation") or "").strip(),
                "salary": (row.get("salary") or "").strip(),
                "image_file": filename,
                "created_at": (row.get("created_at") or "").strip(),
                "signature": signature,
                "encoding": encoding,
            }
        )

    return users


def refresh_known_users():
    global KNOWN_USERS, FULL_MODE
    KNOWN_USERS = build_known_users()
    FULL_MODE = face_recognition is not None and any(u.get("encoding") is not None for u in KNOWN_USERS)
    print(
        f"[INFO] Facial app ready: mode={'recognition' if FULL_MODE else 'fallback'}, "
        f"known_users={len(KNOWN_USERS)}"
    )


def match_user_by_encoding(face_crop):
    if not FULL_MODE or face_recognition is None:
        return None, None

    try:
        rgb = cv2.cvtColor(face_crop, cv2.COLOR_BGR2RGB)
        encodings = face_recognition.face_encodings(rgb)
    except Exception:
        return None, None

    if not encodings:
        return None, None

    query = encodings[0]

    users_with_enc = [u for u in KNOWN_USERS if u.get("encoding") is not None]
    if not users_with_enc:
        return None, None

    known_enc = [u["encoding"] for u in users_with_enc]
    distances = face_recognition.face_distance(known_enc, query)
    if len(distances) == 0:
        return None, None

    best_idx = int(np.argmin(distances))
    best_dist = float(distances[best_idx])

    # Typical strict threshold for face_recognition
    if best_dist > 0.50:
        return None, None

    confidence = max(0.0, min(1.0, 1.0 - best_dist))
    return users_with_enc[best_idx], confidence


def match_user_by_signature(face_crop):
    if not KNOWN_USERS:
        return None, None

    query_sig = compute_face_signature(face_crop)

    best_user = None
    best_dist = 1e9

    for user in KNOWN_USERS:
        ref_sig = user.get("signature")
        if ref_sig is None:
            continue

        dist = cv2.compareHist(query_sig.astype(np.float32), ref_sig.astype(np.float32), cv2.HISTCMP_BHATTACHARYYA)
        if dist < best_dist:
            best_dist = dist
            best_user = user

    if best_user is None:
        return None, None

    # For Bhattacharyya distance: lower is better. Conservative threshold.
    if best_dist > 0.42:
        return None, None

    confidence = max(0.0, min(1.0, 1.0 - float(best_dist)))
    return best_user, confidence


def mark_attendance(name: str, user_key: str, mode: str, confidence: float | None):
    now = datetime.now()

    last = LAST_MARKS.get(user_key)
    if last is not None and (now - last).total_seconds() < ATTENDANCE_COOLDOWN_SECONDS:
        return False

    LAST_MARKS[user_key] = now

    file_exists = os.path.exists(ATTENDANCE_FILE)

    with open(ATTENDANCE_FILE, "a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        if not file_exists:
            writer.writerow(["Name", "UserKey", "Time", "Mode", "Confidence"])

        writer.writerow(
            [
                name,
                user_key,
                now.strftime("%d/%m/%Y %H:%M:%S"),
                mode,
                f"{confidence:.3f}" if confidence is not None else "",
            ]
        )

    return True


def read_recent_attendance(limit=20):
    if not os.path.exists(ATTENDANCE_FILE):
        return []

    with open(ATTENDANCE_FILE, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        rows = list(reader)

    return list(reversed(rows[-limit:]))


ensure_storage()
refresh_known_users()


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
            "known_users": len(KNOWN_USERS),
            "full_recognition_available": bool(face_recognition is not None),
        }
    )


@app.route("/api/users")
def api_users():
    return jsonify(
        {
            "users": [
                {
                    "key": u["key"],
                    "name": u["name"],
                    "user_id": u["user_id"],
                    "designation": u["designation"],
                }
                for u in KNOWN_USERS
            ]
        }
    )


@app.route("/api/attendance/recent")
def api_recent_attendance():
    return jsonify({"rows": read_recent_attendance(limit=25)})


@app.route("/api/register_user", methods=["POST"])
def api_register_user():
    payload = request.get_json(silent=True) or {}

    name = (payload.get("name") or "").strip()
    user_id = (payload.get("id") or "").strip()
    mobile = (payload.get("mobile") or "").strip()
    designation = (payload.get("designation") or "").strip()
    salary = (payload.get("salary") or "").strip()
    frame_data = payload.get("frame")

    if not name:
        return jsonify(success=False, error="Name is required"), 400

    frame = decode_data_url(frame_data)
    if frame is None:
        return jsonify(success=False, error="Invalid frame data"), 400

    face_crop, _ = extract_best_face(frame)
    if face_crop is None:
        return jsonify(success=False, error="No face detected. Please center your face and try again."), 400

    base_key = safe_slug(f"{name}_{user_id}" if user_id else name)
    if not base_key:
        base_key = f"user_{int(datetime.now().timestamp())}"

    metadata = load_users_metadata()
    user_key = base_key
    counter = 2
    while user_key in metadata and (metadata[user_key].get("name") or "").strip().lower() != name.lower():
        user_key = f"{base_key}_{counter}"
        counter += 1

    image_filename = f"{user_key}.jpg"
    image_path = os.path.join(IMAGE_DIR, image_filename)
    cv2.imwrite(image_path, face_crop)

    record = {
        "key": user_key,
        "name": name,
        "user_id": user_id,
        "mobile": mobile,
        "designation": designation,
        "salary": salary,
        "image_file": image_filename,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    upsert_user_metadata(record)
    refresh_known_users()

    return jsonify(
        success=True,
        user={
            "key": user_key,
            "name": name,
            "user_id": user_id,
            "designation": designation,
        },
        known_users=len(KNOWN_USERS),
    )


@app.route("/process_frame", methods=["POST"])
def process_frame():
    data = request.get_json(silent=True) or {}
    frame_data = data.get("frame")

    frame = decode_data_url(frame_data)
    if frame is None:
        return jsonify(success=False, error="invalid_frame"), 400

    face_crop, _ = extract_best_face(frame)
    if face_crop is None:
        return jsonify(success=False, prediction="NO_FACE", mode="none")

    user = None
    confidence = None
    mode = "fallback"

    if FULL_MODE:
        user, confidence = match_user_by_encoding(face_crop)
        mode = "recognition"

    if user is None:
        user, confidence = match_user_by_signature(face_crop)
        mode = "fallback-hist"

    if user is not None:
        marked = mark_attendance(user["name"], user["key"], mode, confidence)
        return jsonify(
            success=True,
            name=user["name"],
            user_key=user["key"],
            mode=mode,
            confidence=round(float(confidence), 3) if confidence is not None else None,
            marked=marked,
        )

    return jsonify(success=False, prediction="UNKNOWN", mode=mode)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
