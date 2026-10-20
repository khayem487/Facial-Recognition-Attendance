"""Private durable storage for the existing Flask attendance application.

Reference photos never receive a public URL. Separate user/event objects avoid
overwriting another request's registration or attendance history.
"""

import base64
import json
import time
from datetime import datetime
from uuid import uuid4

from vercel.blob import sync as blob
from vercel.blob.errors import BlobError, BlobNotFoundError, BlobPreconditionFailedError


class BlobStorage:
    def __init__(self, prefix="attendance-app/"):
        self.prefix = prefix
        self._users = None
        self._loaded_at = 0

    def _get(self, path):
        result = blob.get_blob(self.prefix + path, access="private")
        return json.loads(result.body), result.metadata.etag

    def _put(self, path, value, overwrite=False):
        return blob.put_blob(
            self.prefix + path,
            json.dumps(value, ensure_ascii=False).encode("utf-8"),
            access="private",
            content_type="application/json",
            allow_overwrite=overwrite,
            cache_control_max_age=0,
        )

    def invalidate_users(self):
        self._users = None

    def users(self, force=False):
        # A short local cache avoids a storage listing on every webcam frame.
        # Other warm instances discover a new registration within 3 seconds.
        if not force and self._users is not None and time.monotonic() - self._loaded_at < 3:
            return self._users
        records = []
        for item in blob.query_blobs(prefix=self.prefix + "users/"):
            result = blob.get_blob(item.url, access="private")
            records.append(json.loads(result.body))
        self._users = records
        self._loaded_at = time.monotonic()
        return records

    def save_user(self, record, jpeg_bytes):
        self._put(
            "users/" + record["key"] + ".json",
            {"metadata": record, "image": base64.b64encode(jpeg_bytes).decode("ascii")},
            overwrite=True,
        )
        self.invalidate_users()

    def mark(self, row, cooldown_seconds):
        key = row["UserKey"]
        claim_path = "cooldowns/" + key + ".json"
        now = time.time()
        try:
            previous, etag = self._get(claim_path)
        except BlobNotFoundError:
            previous = None
        if previous is not None:
            if now - previous["timestamp"] < cooldown_seconds:
                return False
            # A conditional delete prevents two instances replacing one lease.
            try:
                blob.delete_blob(self.prefix + claim_path, if_match=etag)
            except (BlobNotFoundError, BlobPreconditionFailedError):
                return False
        try:
            claim = self._put(claim_path, {"timestamp": now})
        except BlobError as exc:
            # A simultaneous request may have created the same lease first.
            # Do not swallow credentials, quota or other operational failures.
            if exc.code in ("blob_already_exists", "already_exists", "precondition_failed") or exc.status_code in (409, 412):
                return False
            raise
        path = "events/" + datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex + ".json"
        try:
            self._put(path, row)
        except Exception:
            blob.delete_blob(self.prefix + claim_path, if_match=claim.etag)
            raise
        return True

    def recent(self, limit=20):
        entries = sorted(
            blob.query_blobs(prefix=self.prefix + "events/"),
            key=lambda entry: entry.pathname,
            reverse=True,
        )[:limit]
        return [json.loads(blob.get_blob(entry.url, access="private").body) for entry in entries]
