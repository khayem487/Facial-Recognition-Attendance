"""Exercise real registration/recognition using a supplied public test fixture.

Only use a deliberately disposable test name. No webcam or personal photo is used.
The created test user's key is printed for scoped cleanup by the store owner.
"""
import argparse
import base64
import json
from pathlib import Path
import time
import urllib.error
import urllib.request
from uuid import uuid4


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url")
    parser.add_argument("--face-image", type=Path, required=True)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    def call(path, payload=None):
        request = urllib.request.Request(
            base + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={"Content-Type": "application/json"} if payload is not None else {},
        )
        started = time.monotonic()
        try:
            response = urllib.request.urlopen(request, timeout=60)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read()
            try:
                body = json.loads(raw)
            except ValueError:
                body = raw.decode(errors="replace")[:300]
            return response.status, body, round(time.monotonic() - started, 3)

    checks = []
    status, health, seconds = call("/health")
    assert status == 200 and health["storage"] == "private-vercel-blob", (status, health)
    checks.append({"check": "real_server_and_durable_private_storage", "seconds": seconds, "result": health})
    status, body, _ = call("/api/register_user", {})
    assert status == 400 and not body["success"], (status, body)
    name = "CODEX DEMO TEST " + uuid4().hex[:10]
    frame = "data:image/jpeg;base64," + base64.b64encode(args.face_image.read_bytes()).decode()
    status, registered, seconds = call("/api/register_user", {"name": name, "id": "PUBLIC-FIXTURE", "frame": frame})
    assert status == 200 and registered["success"], (status, registered)
    key = registered["user"]["key"]
    print(json.dumps({"test_user_key": key}), flush=True)
    checks.append({"check": "real_face_registration", "seconds": seconds})
    status, users, _ = call("/api/users")
    assert status == 200 and any(user["key"] == key for user in users["users"]), users
    status, matched, seconds = call("/process_frame", {"frame": frame})
    assert status == 200 and matched["success"] and matched["user_key"] == key and matched["marked"], matched
    checks.append({"check": "server_side_face_match_and_attendance", "seconds": seconds, "result": matched})
    status, repeated, _ = call("/process_frame", {"frame": frame})
    assert status == 200 and repeated["success"] and not repeated["marked"], repeated
    status, recent, _ = call("/api/attendance/recent")
    assert status == 200 and any(row["UserKey"] == key for row in recent["rows"]), recent
    checks.append({"check": "shared_history_and_duplicate_cooldown", "result": "passed"})
    print(json.dumps({"base_url": base, "test_user_key": key, "checks": checks}, indent=2))


if __name__ == "__main__":
    main()
