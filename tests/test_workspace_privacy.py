"""Offline workspace/privacy regressions. Pixel fixtures are synthetic, not faces."""

import base64
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4
from urllib.parse import unquote, urlsplit
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np

import app as web
import blob_storage as cloud
from workspace_storage import LocalWorkspaceStorage, StorageError


def image(value=64):
    frame = np.full((128, 128, 3), value, dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", frame)
    assert ok
    return "data:image/jpeg;base64," + base64.b64encode(encoded).decode("ascii")


FRAME_A, FRAME_B = image(64), image(192)


class FakeBlob:
    """Small conditional-object API; every operation stays in memory."""

    def __init__(self):
        self.objects = {}
        self.calls = []
        self.fail_event_put = False
        self.fail_profile_delete = False
        self.stale_cdn = False
        self.delivery_cache = {}

    def get_blob(self, path, **options):
        self.calls.append(("get", path))
        assert options.get("access") == "private"
        delivery_key = path
        parsed = urlsplit(path)
        if parsed.scheme:
            path = unquote(parsed.path).lstrip("/")
        if self.stale_cdn and delivery_key in self.delivery_cache:
            body, etag = self.delivery_cache[delivery_key]
            return SimpleNamespace(body=body, metadata=SimpleNamespace(etag=etag))
        if path not in self.objects:
            raise cloud.BlobNotFoundError()
        body, etag = self.objects[path]
        self.delivery_cache[delivery_key] = (body, etag)
        return SimpleNamespace(body=body, metadata=SimpleNamespace(etag=etag))

    def head_blob(self, path):
        self.calls.append(("head", path))
        if path not in self.objects:
            raise cloud.BlobNotFoundError()
        return SimpleNamespace(etag=self.objects[path][1],
            url="https://teststore.private.blob.vercel-storage.com/" + path)

    def put_blob(self, path, body, **options):
        self.calls.append(("put", path))
        assert options.get("access") == "private"
        if self.fail_event_put and "/events/" in path:
            raise cloud.BlobError("TEST upstream failure includes PRIVATE_TOKEN", status_code=503)
        if path in self.objects and not options.get("allow_overwrite"):
            raise cloud.BlobError("TEST exists", status_code=409, code="already_exists")
        etag = uuid4().hex
        self.objects[path] = (bytes(body), etag)
        return SimpleNamespace(etag=etag)

    def query_blobs(self, prefix):
        self.calls.append(("list", prefix))
        return [SimpleNamespace(pathname=path, url=path)
                for path in sorted(self.objects) if path.startswith(prefix)]

    def delete_blob(self, path, **options):
        self.calls.append(("delete", path))
        if self.fail_profile_delete and "/users/" in path:
            raise cloud.BlobError("TEST private URL and PRIVATE_TOKEN", status_code=503)
        if path not in self.objects:
            raise cloud.BlobNotFoundError()
        if options.get("if_match") and options["if_match"] != self.objects[path][1]:
            raise cloud.BlobPreconditionFailedError()
        del self.objects[path]


class APIContract:
    backend = "local"

    def setUp(self):
        self.temp = TemporaryDirectory(prefix="attendance-workspace-test-")
        self.addCleanup(self.temp.cleanup)
        self.old = {key: web.app.config.get(key)
                    for key in ("TESTING", "WORKSPACE_DATA_ROOT", "WORKSPACE_STORAGE_FACTORY")}
        self.addCleanup(web.app.config.update, self.old)
        web.app.config.update(TESTING=True, WORKSPACE_DATA_ROOT=self.temp.name, WORKSPACE_STORAGE_FACTORY=None)
        self.addCleanup(patch.stopall)
        patch.object(web, "blob_enabled", return_value=False).start()
        patch.object(web, "face_recognition", None).start()
        # Synthetic constant-colour images exercise actual JPEG decoding and
        # histogram comparison; only face detection is replaced in these tests.
        patch.object(web, "detect_faces", return_value=[(0, 0, 128, 128)]).start()
        if self.backend == "blob":
            self.fake = FakeBlob()
            patch.object(cloud, "blob", self.fake).start()
            web.app.config["WORKSPACE_STORAGE_FACTORY"] = cloud.BlobStorage
        self.a, self.b = web.app.test_client(), web.app.test_client()
        self.csrf_a = self.a.get("/api/session").get_json()["csrf_token"]
        self.csrf_b = self.b.get("/api/session").get_json()["csrf_token"]

    def call(self, client, method, path, payload=None, csrf=None, **kwargs):
        token = csrf if csrf is not None else self.csrf_a if client is self.a else self.csrf_b
        headers = {"X-CSRF-Token": token, **kwargs.pop("headers", {})}
        return client.open(path, method=method, json=payload, headers=headers, **kwargs)

    def register(self, client, name="TEST Alice", frame=FRAME_A):
        response = self.call(client, "POST", "/api/register_user",
                             {"name": name, "id": "TEST-ID", "designation": "Synthetic test", "frame": frame})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.get_json()["user"]["key"]

    def namespace(self, client):
        return hashlib.sha256(client.get_cookie(web.COOKIE_NAME).value.encode()).hexdigest()

    def store(self, client):
        if self.backend == "blob":
            return cloud.BlobStorage(self.namespace(client))
        return LocalWorkspaceStorage(self.temp.name, self.namespace(client))

    def test_workspace_cookie_is_opaque_private_and_bootstrap_is_stable(self):
        session = self.a.get("/api/session")
        token = self.a.get_cookie(web.COOKIE_NAME).value
        self.assertRegex(token, r"^[0-9a-f]{64}$")
        self.assertNotEqual(token, self.b.get_cookie(web.COOKIE_NAME).value)
        self.assertEqual(session.get_json()["csrf_token"], self.csrf_a)
        self.assertNotIn(token, session.get_data(as_text=True))
        self.assertEqual(session.get_json()["isolation"], "browser")
        self.assertIsNone(session.headers.get("Set-Cookie"), "stable API reads do not rotate the capability")
        response = web.app.test_client().get("/api/session", base_url="https://localhost")
        cookie = response.headers["Set-Cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        self.assertIn("Secure", cookie)
        self.assertIn("Path=/", cookie)
        self.assertNotIn("Domain=", cookie)

    def test_health_reports_capability_without_global_or_workspace_counts(self):
        self.register(self.a)
        response = web.app.test_client().get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["isolation"], "browser")
        self.assertNotIn("known_users", response.get_json())
        self.assertNotIn("users", response.get_json())
        self.assertIsNone(response.headers.get("Set-Cookie"))
        self.assertIn("no-store", response.headers["Cache-Control"])

    def test_two_browsers_cannot_list_or_recognize_each_others_profiles(self):
        key_a = self.register(self.a)
        self.assertEqual(self.b.get("/api/users").get_json(), {"users": []})
        result = self.call(self.b, "POST", "/process_frame", {"frame": FRAME_A})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.get_json()["prediction"], "UNKNOWN")
        self.assertNotIn("TEST Alice", result.get_data(as_text=True))
        key_b = self.register(self.b, "TEST Bob", FRAME_B)
        a_users = self.a.get("/api/users").get_json()["users"]
        b_users = self.b.get("/api/users").get_json()["users"]
        self.assertEqual([row["key"] for row in a_users], [key_a])
        self.assertEqual([row["key"] for row in b_users], [key_b])
        matched = self.call(self.a, "POST", "/process_frame", {"frame": FRAME_A}).get_json()
        self.assertTrue(matched["success"])
        self.assertEqual(matched["user_key"], key_a)
        self.assertEqual(self.b.get("/api/attendance/recent").get_json(), {"rows": []})

    def test_registration_uses_immutable_random_keys_instead_of_name_overwrite(self):
        first, second = self.register(self.a), self.register(self.a)
        self.assertNotEqual(first, second)
        self.assertRegex(first, r"^[0-9a-f]{32}$")
        self.assertEqual(len(self.a.get("/api/users").get_json()["users"]), 2)

    def test_delete_is_scoped_and_removes_reference_events_and_cooldown(self):
        key_a = self.register(self.a)
        key_b = self.register(self.b, "TEST Bob", FRAME_B)
        self.assertEqual(self.call(self.a, "POST", "/process_frame", {"frame": FRAME_A}).get_json()["marked"], True)
        self.assertEqual(self.call(self.b, "DELETE", "/api/users/" + key_a).status_code, 404)
        self.assertTrue(self.store(self.a).has_user(key_a))
        removed = self.call(self.a, "DELETE", "/api/users/" + key_a)
        self.assertEqual(removed.status_code, 200)
        self.assertTrue(removed.get_json()["success"])
        self.assertEqual(self.call(self.a, "DELETE", "/api/users/" + key_a).status_code, 404)
        self.assertEqual(self.a.get("/api/users").get_json(), {"users": []})
        self.assertEqual(self.a.get("/api/attendance/recent").get_json(), {"rows": []})
        self.assertFalse(self.store(self.a).has_user(key_a))
        self.assertEqual(self.call(self.a, "POST", "/process_frame", {"frame": FRAME_A}).get_json()["prediction"], "UNKNOWN")
        self.assertTrue(self.store(self.b).has_user(key_b))
        self.assertEqual([row["key"] for row in self.b.get("/api/users").get_json()["users"]], [key_b])
        if self.backend == "local":
            with closing(sqlite3.connect(self.store(self.a).path)) as database:
                for table in ("profiles", "events", "cooldowns"):
                    self.assertEqual(database.execute("SELECT COUNT(*) FROM " + table).fetchone()[0], 0)
        else:
            namespace = self.store(self.a).prefix
            remaining = {path: json.loads(body) for path, (body, _) in self.fake.objects.items()
                         if path.startswith(namespace)}
            self.assertEqual(list(remaining), [namespace + "deleted/" + key_a + ".json"])
            self.assertEqual(list(next(iter(remaining.values()))), ["deleted_at"])

    def test_fresh_storage_instance_observes_deletion_and_cannot_remark(self):
        key = self.register(self.a)
        old = self.store(self.a)
        self.assertEqual(len(old.users()), 1)
        self.assertTrue(self.store(self.a).delete_user(key))
        self.assertEqual(old.users(), [])
        self.assertFalse(old.has_user(key))
        self.assertFalse(old.mark({"UserKey": key, "Name": "TEST Alice"}, 20))
        self.assertEqual(old.recent(), [])

    def test_browser_cookie_and_cooldown_survive_new_client_and_store_instances(self):
        key = self.register(self.a)
        first = self.call(self.a, "POST", "/process_frame", {"frame": FRAME_A}).get_json()
        self.assertTrue(first["marked"])
        restored = web.app.test_client()
        restored.set_cookie(web.COOKIE_NAME, self.a.get_cookie(web.COOKIE_NAME).value)
        token = restored.get("/api/session").get_json()["csrf_token"]
        self.assertEqual(token, self.csrf_a)
        self.assertEqual(restored.get("/api/users").get_json()["users"][0]["key"], key)
        response = self.call(restored, "POST", "/process_frame", {"frame": FRAME_A}, csrf=token).get_json()
        self.assertTrue(response["success"])
        self.assertFalse(response["marked"])
        self.assertEqual(len(restored.get("/api/attendance/recent").get_json()["rows"]), 1)

    def test_invalid_cookie_rotates_to_empty_workspace_without_touching_another(self):
        key = self.register(self.a)
        self.b.set_cookie(web.COOKIE_NAME, "../TEST-INVALID")
        response = self.b.get("/api/session")
        self.assertEqual(response.status_code, 200)
        new_cookie = self.b.get_cookie(web.COOKIE_NAME).value
        self.assertRegex(new_cookie, r"^[0-9a-f]{64}$")
        self.assertEqual(self.b.get("/api/users").get_json(), {"users": []})
        self.assertTrue(self.store(self.a).has_user(key))

    def test_csrf_and_cross_origin_requests_cannot_change_or_rotate_workspace(self):
        key = self.register(self.a)
        for token in ("", "x" * 64, self.csrf_b, "é"):
            response = self.call(self.a, "DELETE", "/api/users/" + key, csrf=token)
            self.assertEqual(response.status_code, 403)
        for headers in ({"Origin": "https://example.invalid"}, {"Origin": "null"},
                        {"Sec-Fetch-Site": "cross-site"}, {"Sec-Fetch-Site": "same-site"}):
            response = self.call(self.a, "DELETE", "/api/users/" + key, headers=headers)
            self.assertEqual(response.status_code, 403)
        outsider = web.app.test_client()
        denied = outsider.get("/api/session", headers={"Sec-Fetch-Site": "cross-site"})
        self.assertEqual(denied.status_code, 403)
        self.assertIsNone(denied.headers.get("Set-Cookie"))
        page = outsider.get("/", headers={"Sec-Fetch-Site": "cross-site"})
        self.assertEqual(page.status_code, 200)
        self.assertIsNone(page.headers.get("Set-Cookie"))
        self.assertTrue(self.store(self.a).has_user(key))

    def test_malformed_payloads_and_unneeded_personal_fields_are_rejected(self):
        for payload in ([], None, {"name": ["bad"], "frame": FRAME_A},
                        {"name": "TEST", "mobile": "unused", "frame": FRAME_A},
                        {"name": "TEST", "salary": "unused", "frame": FRAME_A},
                        {"name": "x" * 81, "frame": FRAME_A},
                        {"name": "TEST\nBAD", "frame": FRAME_A}):
            response = self.call(self.a, "POST", "/api/register_user", payload)
            self.assertIn(response.status_code, (400, 415))
        self.assertEqual(self.a.get("/api/users").get_json(), {"users": []})
        self.assertEqual(self.call(self.a, "DELETE", "/api/users/../legacy").status_code, 404)

    def test_every_private_response_is_noncacheable_without_cors_exposure(self):
        for path in ("/api/session", "/api/users", "/api/attendance/recent", "/health"):
            response = self.a.get(path)
            self.assertIn("no-store", response.headers["Cache-Control"])
            self.assertIsNone(response.headers.get("Access-Control-Allow-Origin"))
            self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])

    def test_vercel_https_origin_is_valid_behind_tls_terminator_without_trusting_forwarded_headers(self):
        with patch.dict(os.environ, {"VERCEL": "1"}):
            result = self.call(self.a, "POST", "/api/register_user",
                               {"name": "TEST TLS", "frame": FRAME_A}, headers={"Origin": "https://localhost"})
            self.assertEqual(result.status_code, 200)
            denied = self.call(self.a, "POST", "/process_frame", {"frame": FRAME_A},
                               headers={"Origin": "http://localhost"})
            self.assertEqual(denied.status_code, 403)
        with patch.dict(os.environ):
            os.environ.pop("VERCEL", None)
            denied = self.call(self.a, "POST", "/process_frame", {"frame": FRAME_A},
                               headers={"Origin": "https://localhost", "X-Forwarded-Proto": "https"})
            self.assertEqual(denied.status_code, 403)

    def test_storage_initialization_error_does_not_expose_paths_or_secrets(self):
        def broken_factory(namespace):
            raise RuntimeError("TEST PRIVATE_TOKEN and private/path")
        web.app.config["WORKSPACE_STORAGE_FACTORY"] = broken_factory
        result = self.a.get("/api/users")
        self.assertEqual(result.status_code, 503)
        self.assertNotIn("PRIVATE_TOKEN", result.get_data(as_text=True))
        self.assertNotIn("private/path", result.get_data(as_text=True))

    def test_oversized_request_gets_json_error_before_storage_or_image_decode(self):
        with patch.object(web, "decode_data_url", side_effect=AssertionError("must reject body first")):
            result = self.a.post("/api/register_user", data=b"x" * (4 * 1024 * 1024 + 1),
                                 headers={"Content-Type": "application/json", "X-CSRF-Token": self.csrf_a})
        self.assertEqual(result.status_code, 413)
        self.assertFalse(result.get_json()["success"])

    def test_unavailable_optional_recognition_falls_back_without_cross_workspace_state(self):
        key = self.register(self.a)
        broken = SimpleNamespace(face_encodings=lambda frame: (_ for _ in ()).throw(RuntimeError("TEST unavailable")))
        with patch.object(web, "face_recognition", broken):
            result = self.call(self.a, "POST", "/process_frame", {"frame": FRAME_A}).get_json()
        self.assertTrue(result["success"])
        self.assertEqual(result["user_key"], key)
        self.assertEqual(result["mode"], "fallback-hist")

    def test_profile_capacity_is_bounded_per_workspace(self):
        store = self.store(self.a)
        raw = base64.b64decode(FRAME_A.split(",", 1)[1])
        for number in range(25):
            store.save_user({"key": f"{number:032x}", "name": "TEST", "user_id": "", "designation": ""}, raw)
        response = self.call(self.a, "POST", "/api/register_user", {"name": "TEST EXTRA", "frame": FRAME_A})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(len(self.a.get("/api/users").get_json()["users"]), 25)
        self.assertEqual(self.b.get("/api/users").get_json(), {"users": []})


class LocalAPITests(APIContract, unittest.TestCase):
    backend = "local"

    def test_local_storage_never_imports_shared_legacy_files(self):
        root = Path(self.temp.name)
        legacy = root / "users.csv"
        legacy.write_text("key;name\nTEST_LEGACY;TEST PRIVATE LEGACY\n", encoding="utf-8")
        photo = root / "imageAttendance" / "TEST_LEGACY.jpg"
        photo.parent.mkdir()
        photo.write_bytes(base64.b64decode(FRAME_A.split(",", 1)[1]))
        self.assertEqual(self.a.get("/api/users").get_json(), {"users": []})
        self.register(self.a)
        self.assertTrue(photo.exists())
        self.assertIn("TEST PRIVATE LEGACY", legacy.read_text(encoding="utf-8"))

    def test_local_cooldown_is_atomic_across_two_storage_instances(self):
        key = self.register(self.a)
        one, two = self.store(self.a), self.store(self.a)
        row = {"UserKey": key, "Name": "TEST", "RecordedAt": "2026-10-29T12:00:00Z"}
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda store: store.mark(row, 20), (one, two)))
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(len(one.recent()), 1)


class BlobAPITests(APIContract, unittest.TestCase):
    backend = "blob"

    def test_deleted_cached_photo_cannot_restore_visibility_or_repeat_delete_success(self):
        self.fake.stale_cdn = True
        key = self.register(self.a)
        path = self.store(self.a).prefix + "users/" + key + ".json"
        self.assertIn(path, self.fake.delivery_cache)
        self.assertEqual(self.call(self.a, "POST", "/process_frame", {"frame": FRAME_A}).status_code, 200)
        self.assertEqual(self.call(self.a, "DELETE", "/api/users/" + key).status_code, 200)
        self.assertIn(b"TEST Alice", self.fake.get_blob(path, access="private").body,
                      "fixture deliberately keeps the deleted CDN body available")
        self.assertEqual(self.call(self.a, "DELETE", "/api/users/" + key).status_code, 404)
        self.assertFalse(self.store(self.a).has_user(key))
        self.assertEqual(self.a.get("/api/users").get_json()["users"], [])
        self.assertEqual(self.a.get("/api/attendance/recent").get_json()["rows"], [])
        self.assertEqual(self.call(self.a, "POST", "/process_frame", {"frame": FRAME_A}).get_json()["prediction"], "UNKNOWN")

    def test_replaced_cooldown_uses_catalog_version_when_old_delivery_bodies_remain_cached(self):
        self.fake.stale_cdn = True
        key = self.register(self.a)
        store = self.store(self.a)
        row = {"UserKey": key, "Name": "TEST", "RecordedAt": "2026-10-29T12:00:00Z"}
        for now, expected in [(100, True), (101, False), (121, True), (122, False), (142, True)]:
            with patch.object(cloud.time, "time", return_value=now):
                self.assertEqual(store.mark(row, 20), expected)
        self.assertEqual(len(store.recent()), 3)
        downloads = [path for operation, path in self.fake.calls if operation == "get" and "/cooldowns/" in path]
        self.assertTrue(downloads and all("?version=" in path for path in downloads))

    def test_mismatched_delivery_version_cannot_remove_newer_cooldown(self):
        key = self.register(self.a)
        store = self.store(self.a)
        row = {"UserKey": key, "Name": "TEST", "RecordedAt": "2026-10-29T12:00:00Z"}
        with patch.object(cloud.time, "time", return_value=100):
            self.assertTrue(store.mark(row, 20))
        claim_path = store.prefix + "cooldowns/" + key + ".json"
        original_claim = self.fake.objects[claim_path]
        for delivery_etag in (None, "wrong-version"):
            stale = SimpleNamespace(body=b'{"timestamp":0}', metadata=SimpleNamespace(etag=delivery_etag))
            with patch.object(self.fake, "get_blob", return_value=stale), patch.object(cloud.time, "time", return_value=121):
                with self.assertRaises(StorageError):
                    store.mark(row, 20)
            self.assertEqual(self.fake.objects[claim_path], original_claim)
        self.assertEqual(len(store.recent()), 1)

    def test_blob_storage_never_lists_or_changes_shared_legacy_objects(self):
        legacy = "attendance-app/users/TEST_LEGACY.json"
        self.fake.objects[legacy] = (b'{"metadata":{"name":"TEST PRIVATE LEGACY"}}', "TEST-etag")
        key = self.register(self.a)
        self.assertEqual(self.call(self.a, "DELETE", "/api/users/" + key).status_code, 200)
        self.assertIn(legacy, self.fake.objects)
        self.assertTrue(all("/workspaces/" in path for _, path in self.fake.calls))

    def test_failed_physical_delete_is_not_reported_success_and_can_be_retried(self):
        key = self.register(self.a)
        self.fake.fail_profile_delete = True
        result = self.call(self.a, "DELETE", "/api/users/" + key)
        self.assertEqual(result.status_code, 503)
        self.assertNotIn("PRIVATE_TOKEN", result.get_data(as_text=True))
        self.assertEqual(self.a.get("/api/users").get_json(), {"users": []}, "tombstone masks incomplete cleanup")
        self.fake.fail_profile_delete = False
        self.assertEqual(self.call(self.a, "DELETE", "/api/users/" + key).status_code, 200)
        self.assertFalse(self.store(self.a).has_user(key))

    def test_failed_attendance_write_rolls_back_claim_and_can_retry(self):
        self.register(self.a)
        self.fake.fail_event_put = True
        result = self.call(self.a, "POST", "/process_frame", {"frame": FRAME_A})
        self.assertEqual(result.status_code, 503)
        self.assertNotIn("PRIVATE_TOKEN", result.get_data(as_text=True))
        self.assertFalse(any("/cooldowns/" in path for path in self.fake.objects))
        self.fake.fail_event_put = False
        result = self.call(self.a, "POST", "/process_frame", {"frame": FRAME_A})
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.get_json()["marked"])


class FrameValidationTests(unittest.TestCase):
    def test_actual_synthetic_jpeg_decodes_but_spoofed_mime_and_invalid_base64_do_not(self):
        self.assertEqual(web.decode_data_url(FRAME_A).shape, (128, 128, 3))
        for value in ("data:image/png;base64," + FRAME_A.split(",", 1)[1],
                      "data:image/svg+xml;base64,PHN2Zz4=", "data:image/jpeg;base64,***",
                      "data:image/jpeg;base64,AA==", None, {"frame": "bad"}):
            self.assertIsNone(web.decode_data_url(value))

    def test_oversized_dimensions_are_rejected_before_pixel_decoding(self):
        raw = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + (50000).to_bytes(4, "big") * 2 + b"\x08\x02\x00\x00\x00" + b"\x00" * 4
        with patch.object(web.cv2, "imdecode", side_effect=AssertionError("unsafe allocation")):
            self.assertIsNone(web.decode_data_url("data:image/png;base64," + base64.b64encode(raw).decode()))
        jpeg = b"\xff\xd8\xff\xc0\x00\x08\x08" + (50000).to_bytes(2, "big") * 2 + b"\x03"
        with patch.object(web.cv2, "imdecode", side_effect=AssertionError("unsafe allocation")):
            self.assertIsNone(web.decode_data_url("data:image/jpeg;base64," + base64.b64encode(jpeg).decode()))

    def test_no_import_time_legacy_face_or_attendance_globals_exist(self):
        for name in ("KNOWN_USERS", "LAST_MARKS", "FULL_MODE", "USERS_FILE", "ATTENDANCE_FILE", "IMAGE_DIR"):
            self.assertFalse(hasattr(web, name), name)


if __name__ == "__main__":
    unittest.main()
