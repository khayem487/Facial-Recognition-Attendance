"""Private, browser-scoped Blob storage; legacy shared objects stay untouched."""

import base64
from datetime import datetime, timezone
import json
import time
from urllib.parse import quote
from uuid import uuid4

from vercel.blob import sync as blob
from vercel.blob.errors import BlobError, BlobNotFoundError, BlobPreconditionFailedError

from workspace_storage import checked_key, checked_namespace, storage_operation, StorageError, StorageLimitError


class BlobStorage:
    def __init__(self, namespace):
        self.prefix = "attendance-app/workspaces/" + checked_namespace(namespace) + "/"

    def _get(self, path):
        if path.startswith("cooldowns/"):
            # This pathname is reused. Its catalog ETag selects a new CDN key
            # after each lease replacement, rather than reading a stale body.
            metadata = blob.head_blob(self.prefix + path)
            separator = "&" if "?" in metadata.url else "?"
            result = blob.get_blob(metadata.url + separator + "version=" + quote(metadata.etag, safe=""), access="private")
            if not result.metadata.etag or result.metadata.etag.strip('"') != metadata.etag.strip('"'):
                raise StorageError("Workspace storage is temporarily unavailable")
            return json.loads(result.body), metadata.etag
        result = blob.get_blob(self.prefix + path, access="private")
        return json.loads(result.body), result.metadata.etag

    def _exists(self, path):
        # Delivery GETs may remain cached after deletion. The catalog API is
        # authoritative for visibility and cleanup; never use a cached photo
        # download as evidence that a deleted profile still exists.
        try:
            blob.head_blob(self.prefix + path)
            return True
        except BlobNotFoundError:
            return False

    def _put(self, path, value, overwrite=False):
        return blob.put_blob(self.prefix + path,
                             json.dumps(value, ensure_ascii=False).encode("utf-8"),
                             access="private", content_type="application/json",
                             allow_overwrite=overwrite, cache_control_max_age=0)

    def _entries(self, path):
        prefix = self.prefix + path
        return [entry for entry in blob.query_blobs(prefix=prefix)
                if entry.pathname.startswith(prefix)]

    def _missing(self, path):
        try:
            return self._get(path)
        except BlobNotFoundError:
            return None

    def _delete(self, path, **kwargs):
        try:
            blob.delete_blob(self.prefix + path, **kwargs)
        except BlobNotFoundError:
            pass

    def _deleted_keys(self):
        return {entry.pathname.rsplit("/", 1)[-1].removesuffix(".json")
                for entry in self._entries("deleted/")}

    @storage_operation
    def users(self, force=False):
        # Each request reads this workspace afresh. A warm instance cannot keep
        # recognizing a profile removed by a different instance.
        deleted = self._deleted_keys()
        records = []
        for entry in self._entries("users/"):
            key = entry.pathname.rsplit("/", 1)[-1].removesuffix(".json")
            if key in deleted:
                continue
            try:
                record, _ = self._get("users/" + checked_key(key) + ".json")
            except BlobNotFoundError:
                continue
            if record["metadata"]["key"] == key:
                records.append(record)
        return records

    @storage_operation
    def has_user(self, key):
        key = checked_key(key)
        return not self._exists("deleted/" + key + ".json") and self._exists("users/" + key + ".json")

    @storage_operation
    def save_user(self, record, jpeg_bytes):
        key = checked_key(record["key"])
        if self._exists("deleted/" + key + ".json"):
            raise ValueError("A deleted profile key cannot be reused")
        if len(self.users()) >= 25:
            raise StorageLimitError("This workspace already contains 25 profiles")
        self._put("users/" + key + ".json",
                  {"metadata": record, "image": base64.b64encode(jpeg_bytes).decode("ascii")})

    @storage_operation
    def mark(self, row, cooldown_seconds):
        key, now = checked_key(row["UserKey"]), time.time()
        if not self.has_user(key):
            return False
        claim_path = "cooldowns/" + key + ".json"
        previous = self._missing(claim_path)
        if previous is not None:
            record, etag = previous
            if now - record["timestamp"] < cooldown_seconds:
                return False
            try:
                blob.delete_blob(self.prefix + claim_path, if_match=etag)
            except (BlobNotFoundError, BlobPreconditionFailedError):
                return False
        try:
            claim = self._put(claim_path, {"timestamp": now})
        except BlobError as error:
            if error.code in ("blob_already_exists", "already_exists", "precondition_failed") or error.status_code in (409, 412):
                return False
            raise
        event = "events/" + key + "/" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f") + "-" + uuid4().hex + ".json"
        try:
            self._put(event, row)
            if not self.has_user(key):
                self._delete(event)
                self._delete(claim_path, if_match=claim.etag)
                return False
        except Exception:
            self._delete(claim_path, if_match=claim.etag)
            raise
        return True

    @storage_operation
    def recent(self, limit=20):
        existing = {record["metadata"]["key"] for record in self.users()}
        rows = []
        for entry in sorted(self._entries("events/"), key=lambda item: item.pathname, reverse=True):
            relative = entry.pathname.removeprefix(self.prefix)
            parts = relative.split("/")
            if len(parts) != 3 or parts[1] not in existing:
                continue
            try:
                row, _ = self._get(relative)
            except BlobNotFoundError:
                continue
            if row.get("UserKey") == parts[1]:
                rows.append(row)
        return sorted(rows, key=lambda row: row.get("RecordedAt", ""), reverse=True)[:max(1, min(int(limit), 100))]

    @storage_operation
    def delete_user(self, key):
        key = checked_key(key)
        tombstone = "deleted/" + key + ".json"
        if not self._exists("users/" + key + ".json"):
            if not self._exists(tombstone):
                return False
            # An already completed deletion is missing, just like local SQLite.
            # A partial failed cleanup remains retryable while objects exist.
            if not self._entries("events/" + key + "/") and not self._exists("cooldowns/" + key + ".json"):
                return False
        # Hide the profile first; retries can finish physical cleanup if a Blob
        # operation fails. The tombstone contains no name, image or event data.
        self._put(tombstone, {"deleted_at": datetime.now(timezone.utc).isoformat()}, overwrite=True)
        self._delete("users/" + key + ".json")
        for entry in self._entries("events/" + key + "/"):
            self._delete(entry.pathname.removeprefix(self.prefix))
        self._delete("cooldowns/" + key + ".json")
        return True
