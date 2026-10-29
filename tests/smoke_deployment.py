"""Check two private visitor workspaces; optional disposable public-photo fixture.

No webcam or personal photo is used. Every registration created by this script is
deleted in a finally block, using only its own browser cookie and scoped key.
"""
import argparse
import base64
from http.cookiejar import CookieJar
import json
from pathlib import Path
import time
import urllib.error
import urllib.request
from uuid import uuid4


class Visitor:
    def __init__(self, base):
        self.base = base.rstrip("/")
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
        self.csrf = self.call("/api/session")[1]["csrf_token"]

    def call(self, path, payload=None, method=None, csrf=True):
        headers = {"Accept": "application/json", "Origin": self.base, "Sec-Fetch-Site": "same-origin"}
        actual_method = method or ("POST" if payload is not None else "GET")
        if actual_method not in ("GET", "HEAD"):
            headers["Content-Type"] = "application/json"
            if csrf:
                headers["X-CSRF-Token"] = getattr(self, "csrf", "")
        request = urllib.request.Request(self.base + path, method=actual_method, headers=headers,
            data=json.dumps(payload).encode() if payload is not None else None)
        started = time.monotonic()
        try:
            response = self.opener.open(request, timeout=60)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read()
            try:
                body = json.loads(raw)
            except ValueError:
                body = {"error": "Non-JSON response", "status": response.status}
            return response.status, body, round(time.monotonic() - started, 3)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url")
    parser.add_argument("--face-image", type=Path)
    parser.add_argument("--check-cooldown-expiry", action="store_true",
                        help="Wait for the real 20-second lease and verify a new mark")
    parser.add_argument("--expect-storage", choices=["private-vercel-blob", "local-workspace-sqlite"])
    args = parser.parse_args()
    first, other = Visitor(args.base_url), Visitor(args.base_url)
    checks, created = [], []
    status, health, seconds = first.call("/health")
    assert status == 200 and health["isolation"] == "browser" and "known_users" not in health
    if args.expect_storage:
        assert health["storage"] == args.expect_storage
    checks.append({"check": "private_browser_workspace_health", "seconds": seconds, "result": health})
    for visitor in (first, other):
        assert visitor.call("/api/users")[1]["users"] == []
        assert visitor.call("/api/attendance/recent")[1]["rows"] == []
    assert first.call("/api/register_user", {}, csrf=False)[0] == 403
    assert first.call("/api/register_user", {})[0] == 400
    checks.append({"check": "separate_empty_workspaces_and_csrf", "result": "passed"})
    if not args.face_image:
        print(json.dumps({"base_url": args.base_url, "checks": checks}, indent=2))
        return
    frame = "data:image/jpeg;base64," + base64.b64encode(args.face_image.read_bytes()).decode("ascii")
    try:
        status, registered, seconds = first.call("/api/register_user", {
            "name": "DISPOSABLE FIXTURE " + uuid4().hex[:8], "id": "PUBLIC-FIXTURE", "frame": frame})
        assert status == 200 and registered.get("success"), (status, registered.get("error"))
        key = registered["user"]["key"]
        created.append(key)
        assert any(user["key"] == key for user in first.call("/api/users")[1]["users"])
        assert other.call("/api/users")[1]["users"] == []
        assert other.call("/api/users/" + key, method="DELETE")[0] == 404
        assert first.call("/api/users/" + key, method="DELETE", csrf=False)[0] == 403
        checks.append({"check": "actual_registration_and_foreign_workspace_isolation", "seconds": seconds})
        status, unknown, _ = other.call("/process_frame", {"frame": frame})
        assert status == 200 and not unknown["success"] and unknown["prediction"] == "UNKNOWN"
        assert other.call("/api/attendance/recent")[1]["rows"] == []
        status, matched, seconds = first.call("/process_frame", {"frame": frame})
        assert status == 200 and matched.get("success") and matched["user_key"] == key and matched["marked"], (status, matched)
        status, repeated, _ = first.call("/process_frame", {"frame": frame})
        assert status == 200 and repeated["success"] and not repeated["marked"]
        assert any(row["UserKey"] == key for row in first.call("/api/attendance/recent")[1]["rows"])
        checks.append({"check": "actual_match_scoped_history_and_duplicate_cooldown", "seconds": seconds})
        if args.check_cooldown_expiry:
            time.sleep(21)
            status, renewed, seconds = first.call("/process_frame", {"frame": frame})
            assert status == 200 and renewed["success"] and renewed["marked"], (status, renewed)
            status, repeated, _ = first.call("/process_frame", {"frame": frame})
            assert status == 200 and repeated["success"] and not repeated["marked"], (status, repeated)
            rows = first.call("/api/attendance/recent")[1]["rows"]
            assert len([row for row in rows if row["UserKey"] == key]) == 2
            checks.append({"check": "expired_blob_lease_replaced_without_stale_cached_body", "seconds": seconds})
        assert first.call("/api/users/" + key, method="DELETE")[0] == 200
        created.remove(key)
        assert first.call("/api/users")[1]["users"] == []
        assert first.call("/api/attendance/recent")[1]["rows"] == []
        status, deleted_again, _ = first.call("/api/users/" + key, method="DELETE")
        assert status == 404, (status, deleted_again)
        status, deleted, _ = first.call("/process_frame", {"frame": frame})
        assert status == 200 and not deleted["success"] and deleted["prediction"] == "UNKNOWN"
        checks.append({"check": "reference_and_history_deleted_no_further_match", "result": "passed"})
    finally:
        for key in created:
            status, _, _ = first.call("/api/users/" + key, method="DELETE")
            if status not in (200, 404):
                raise RuntimeError("Disposable fixture cleanup failed")
    print(json.dumps({"base_url": args.base_url, "checks": checks, "disposable_profiles_remaining": len(created)}, indent=2))


if __name__ == "__main__":
    main()
