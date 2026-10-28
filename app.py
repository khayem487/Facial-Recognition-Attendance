import base64
from datetime import datetime, timezone
import hashlib
import hmac
import os
from pathlib import Path
import re
import secrets
import struct
from uuid import uuid4

import cv2
import numpy as np
from flask import Flask, g, jsonify, render_template, request

from workspace_storage import LocalWorkspaceStorage, StorageError, StorageLimitError

try:
    import face_recognition  # type: ignore
except Exception:
    face_recognition = None

app = Flask(__name__)
BASE_DIR = Path(__file__).resolve().parent
COOKIE_NAME = "attendance_workspace"
COOKIE_MAX_AGE = 30 * 24 * 60 * 60
ATTENDANCE_COOLDOWN_SECONDS = 20
MAX_FRAME_BYTES = 2_500_000
MAX_FRAME_PIXELS = 1920 * 1080
MAX_FRAME_DIMENSION = 1920
app.config.update(MAX_CONTENT_LENGTH=4 * 1024 * 1024,
                  WORKSPACE_DATA_ROOT=os.environ.get("ATTENDANCE_DATA_DIR", str(BASE_DIR / ".attendance-workspaces")),
                  WORKSPACE_STORAGE_FACTORY=None)
FACE_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")


def blob_enabled():
    return bool(os.environ.get("BLOB_READ_WRITE_TOKEN") or os.environ.get("BLOB_STORE_ID"))


def storage_label():
    return "private-vercel-blob" if blob_enabled() else "local-workspace-sqlite"


def csrf_token():
    return hmac.new(g.workspace_token.encode("ascii"), b"attendance-demo/csrf/v1", hashlib.sha256).hexdigest()


@app.before_request
def browser_workspace():
    if not (request.path.startswith("/api/") or request.path == "/process_frame"):
        return None
    # HTML navigation never creates a cookie: a cross-site first navigation with
    # SameSite=Strict must not accidentally replace an existing workspace.
    origin = request.headers.get("Origin")
    # Vercel terminates TLS before the Flask service. Trust the platform's
    # environment, never a caller-supplied X-Forwarded-Proto header.
    scheme = "https" if os.environ.get("VERCEL") else request.scheme
    expected_origin = scheme + "://" + request.host
    if origin and origin.rstrip("/") != expected_origin:
        return jsonify(success=False, error="This request must come from this site"), 403
    if request.headers.get("Sec-Fetch-Site") in ("cross-site", "same-site"):
        return jsonify(success=False, error="This request must come from this site"), 403
    token = request.cookies.get(COOKIE_NAME, "")
    valid = re.fullmatch(r"[0-9a-f]{64}", token) is not None
    if not valid and request.method not in ("GET", "HEAD"):
        return jsonify(success=False, error="Open the page again to start your private workspace"), 403
    g.workspace_token = token if valid else secrets.token_hex(32)
    g.new_workspace = not valid
    g.workspace_id = hashlib.sha256(g.workspace_token.encode("ascii")).hexdigest()
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        supplied = request.headers.get("X-CSRF-Token", "")
        if re.fullmatch(r"[0-9a-f]{64}", supplied) is None or not hmac.compare_digest(supplied, csrf_token()):
            return jsonify(success=False, error="The page session changed; reload before trying again"), 403
    return None


@app.after_request
def private_headers(response):
    if getattr(g, "new_workspace", False):
        response.set_cookie(COOKIE_NAME, g.workspace_token, max_age=COOKIE_MAX_AGE,
                            secure=request.is_secure or bool(os.environ.get("VERCEL")),
                            httponly=True, samesite="Strict", path="/")
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; "
        "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
    response.headers["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=()"
    if request.path.startswith("/api/") or request.path in ("/process_frame", "/health"):
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Vary"] = "Cookie"
    return response


def get_store():
    if not hasattr(g, "workspace_store"):
        try:
            factory = app.config.get("WORKSPACE_STORAGE_FACTORY")
            if factory:
                g.workspace_store = factory(g.workspace_id)
            elif blob_enabled():
                from blob_storage import BlobStorage
                g.workspace_store = BlobStorage(g.workspace_id)
            else:
                g.workspace_store = LocalWorkspaceStorage(app.config["WORKSPACE_DATA_ROOT"], g.workspace_id)
        except StorageError:
            raise
        except Exception as error:
            raise StorageError("Workspace storage is temporarily unavailable") from error
    return g.workspace_store


def image_dimensions(raw, mime):
    if mime == "png":
        if len(raw) < 33 or raw[:8] != b"\x89PNG\r\n\x1a\n" or raw[12:16] != b"IHDR":
            return None
        return struct.unpack(">II", raw[16:24])
    if raw[:2] != b"\xff\xd8":
        return None
    cursor = 2
    # Read only JPEG marker headers before decoding any pixel allocation.
    while cursor + 3 < len(raw):
        if raw[cursor] != 0xFF:
            return None
        while cursor < len(raw) and raw[cursor] == 0xFF:
            cursor += 1
        if cursor >= len(raw):
            return None
        marker = raw[cursor]
        cursor += 1
        if marker in (0xD9, 0xDA):
            return None
        if marker in (0x01, *range(0xD0, 0xD9)):
            continue
        if cursor + 2 > len(raw):
            return None
        length = int.from_bytes(raw[cursor:cursor + 2], "big")
        if length < 2 or cursor + length > len(raw):
            return None
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            if length < 8:
                return None
            height, width = struct.unpack(">HH", raw[cursor + 3:cursor + 7])
            return width, height
        cursor += length
    return None


def decode_data_url(data_url):
    if not isinstance(data_url, str) or len(data_url) > 3_400_000:
        return None
    matched = re.fullmatch(r"data:image/(jpeg|png);base64,([A-Za-z0-9+/]*={0,2})", data_url)
    if matched is None:
        return None
    try:
        raw = base64.b64decode(matched[2], validate=True)
        if not raw or len(raw) > MAX_FRAME_BYTES:
            return None
        size = image_dimensions(raw, matched[1])
        if not size or not all(16 <= value <= MAX_FRAME_DIMENSION for value in size) or size[0] * size[1] > MAX_FRAME_PIXELS:
            return None
        frame = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None or frame.shape[:2] != (size[1], size[0]):
            return None
        return frame
    except (ValueError, cv2.error, struct.error):
        return None


def detect_faces(frame_bgr):
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    faces = FACE_CASCADE.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
    return sorted(faces, key=lambda box: box[2] * box[3], reverse=True) if len(faces) else []


def crop_face(frame_bgr, box, pad_ratio=0.2):
    x, y, width, height = map(int, box)
    left, top = max(0, x - int(width * pad_ratio)), max(0, y - int(height * pad_ratio))
    right, bottom = min(frame_bgr.shape[1], x + width + int(width * pad_ratio)), min(frame_bgr.shape[0], y + height + int(height * pad_ratio))
    return frame_bgr[top:bottom, left:right] if right > left and bottom > top else None


def extract_best_face(frame_bgr):
    faces = detect_faces(frame_bgr)
    return (crop_face(frame_bgr, faces[0]), faces[0]) if faces else (None, None)


def compute_face_signature(face_bgr):
    gray = cv2.resize(cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY), (128, 128))
    histogram = cv2.calcHist([gray], [0], None, [64], [0, 256])
    return cv2.normalize(histogram, histogram).flatten()


def build_known_users():
    users = []
    for record in get_store().users(force=True):
        image = decode_data_url("data:image/jpeg;base64," + record["image"])
        if image is None:
            continue
        face, _ = extract_best_face(image)
        reference = face if face is not None else image
        encoding = None
        if face_recognition is not None:
            try:
                encoded = face_recognition.face_encodings(cv2.cvtColor(reference, cv2.COLOR_BGR2RGB))
                encoding = encoded[0] if encoded else None
            except Exception:
                encoding = None
        users.append({**record["metadata"], "signature": compute_face_signature(reference), "encoding": encoding})
    return users


def match_user_by_encoding(face_crop, users):
    if face_recognition is None:
        return None, None
    try:
        encodings = face_recognition.face_encodings(cv2.cvtColor(face_crop, cv2.COLOR_BGR2RGB))
    except Exception:
        return None, None
    candidates = [user for user in users if user.get("encoding") is not None]
    if not encodings or not candidates:
        return None, None
    try:
        distances = face_recognition.face_distance([user["encoding"] for user in candidates], encodings[0])
    except Exception:
        return None, None
    if len(distances) == 0:
        return None, None
    best = int(np.argmin(distances))
    distance = float(distances[best])
    return (candidates[best], max(0.0, 1.0 - distance)) if distance <= 0.50 else (None, None)


def match_user_by_signature(face_crop, users):
    if not users:
        return None, None
    signature = compute_face_signature(face_crop).astype(np.float32)
    scores = [(float(cv2.compareHist(signature, user["signature"].astype(np.float32), cv2.HISTCMP_BHATTACHARYYA)), user)
              for user in users]
    distance, user = min(scores, key=lambda item: item[0])
    return (user, max(0.0, 1.0 - distance)) if distance <= 0.42 else (None, None)


def read_payload(allowed):
    if not request.is_json:
        return None, (jsonify(success=False, error="Send a JSON object"), 415)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or set(payload) - set(allowed):
        return None, (jsonify(success=False, error="Invalid or unsupported fields"), 400)
    return payload, None


def text_field(payload, name, maximum, required=False):
    value = payload.get(name, "")
    if not isinstance(value, str) or len(value) > maximum or re.search(r"[\x00-\x1f\x7f]", value):
        raise ValueError("Invalid " + name)
    value = value.strip()
    if required and not value:
        raise ValueError("Name is required")
    return value


@app.errorhandler(StorageLimitError)
def workspace_full(error):
    return jsonify(success=False, error="This workspace has reached its 25-profile limit; delete a profile before adding another"), 409


@app.errorhandler(StorageError)
def storage_unavailable(error):
    return jsonify(success=False, error="Your private workspace is temporarily unavailable. Please try again."), 503


@app.errorhandler(413)
def frame_too_large(error):
    return jsonify(success=False, error="Frame exceeds the 4 MB request limit"), 413


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/mark_attendance_page")
def mark_attendance_page():
    return render_template("mark_attendance_page.html")


@app.route("/create_user")
def create_user():
    return render_template("create_user.html")


@app.get("/health")
def health():
    return jsonify(status="ok", mode="recognition" if face_recognition is not None else "fallback",
                   full_recognition_available=face_recognition is not None,
                   storage=storage_label(), isolation="browser")


@app.get("/api/session")
def api_session():
    return jsonify(csrf_token=csrf_token(), isolation="browser", storage=storage_label())


@app.get("/api/users")
def api_users():
    return jsonify(users=[{field: record["metadata"].get(field, "")
                           for field in ("key", "name", "user_id", "designation")}
                          for record in get_store().users(force=True)])


@app.get("/api/attendance/recent")
def api_recent_attendance():
    return jsonify(rows=get_store().recent(limit=25))


@app.post("/api/register_user")
def api_register_user():
    payload, error = read_payload(("name", "id", "designation", "frame"))
    if error:
        return error
    try:
        name = text_field(payload, "name", 80, required=True)
        user_id = text_field(payload, "id", 40)
        designation = text_field(payload, "designation", 80)
    except ValueError as error:
        return jsonify(success=False, error=str(error)), 400
    frame = decode_data_url(payload.get("frame"))
    if frame is None:
        return jsonify(success=False, error="Use a valid JPEG or PNG frame up to 1920 pixels and 2.5 MB"), 400
    face, _ = extract_best_face(frame)
    if face is None:
        return jsonify(success=False, error="No face detected. Center one face and try again."), 400
    encoded, jpeg = cv2.imencode(".jpg", face)
    if not encoded:
        return jsonify(success=False, error="Unable to encode the reference image"), 400
    key = uuid4().hex
    record = {"key": key, "name": name, "user_id": user_id, "designation": designation,
              "created_at": datetime.now(timezone.utc).isoformat()}
    get_store().save_user(record, jpeg.tobytes())
    return jsonify(success=True, user={field: record[field] for field in ("key", "name", "user_id", "designation")},
                   known_users=len(get_store().users(force=True)))


@app.delete("/api/users/<key>")
def api_delete_user(key):
    if re.fullmatch(r"[0-9a-f]{32}", key) is None or not get_store().delete_user(key):
        return jsonify(success=False, error="Profile not found in this workspace"), 404
    return jsonify(success=True)


@app.post("/process_frame")
def process_frame():
    payload, error = read_payload(("frame",))
    if error:
        return error
    frame = decode_data_url(payload.get("frame"))
    if frame is None:
        return jsonify(success=False, error="Invalid or oversized JPEG/PNG frame"), 400
    face, _ = extract_best_face(frame)
    if face is None:
        return jsonify(success=False, prediction="NO_FACE", mode="none")
    users = build_known_users()
    user, confidence, mode = None, None, "fallback-hist"
    if face_recognition is not None:
        user, confidence = match_user_by_encoding(face, users)
        mode = "recognition"
    if user is None:
        user, confidence = match_user_by_signature(face, users)
        mode = "fallback-hist"
    store = get_store()
    if user is None or not store.has_user(user["key"]):
        return jsonify(success=False, prediction="UNKNOWN", mode=mode)
    now = datetime.now(timezone.utc)
    row = {"Name": user["name"], "UserKey": user["key"], "Time": now.strftime("%d/%m/%Y %H:%M:%S"),
           "RecordedAt": now.isoformat(), "Mode": mode,
           "Confidence": f"{confidence:.3f}" if confidence is not None else ""}
    marked = store.mark(row, ATTENDANCE_COOLDOWN_SECONDS)
    if not store.has_user(user["key"]):
        return jsonify(success=False, prediction="UNKNOWN", mode=mode)
    return jsonify(success=True, name=user["name"], user_key=user["key"], mode=mode,
                   confidence=round(float(confidence), 3) if confidence is not None else None, marked=marked)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
