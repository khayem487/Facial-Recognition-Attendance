"""Local workspace storage. No legacy/shared files are opened by this module."""

import base64
from contextlib import contextmanager
from functools import wraps
import json
from pathlib import Path
import re
import sqlite3
import time
from uuid import uuid4


class StorageError(Exception):
    """An operation failed; its private path or credential is not an API error."""


class StorageLimitError(StorageError):
    pass


def storage_operation(function):
    @wraps(function)
    def run(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except StorageError:
            raise
        except Exception as error:
            raise StorageError("Workspace storage is temporarily unavailable") from error
    return run


def checked_namespace(namespace):
    if not isinstance(namespace, str) or re.fullmatch(r"[0-9a-f]{64}", namespace) is None:
        raise ValueError("Invalid workspace namespace")
    return namespace


def checked_key(key):
    if not isinstance(key, str) or re.fullmatch(r"[0-9a-f]{32}", key) is None:
        raise ValueError("Invalid profile key")
    return key


class LocalWorkspaceStorage:
    """A separate SQLite database per browser; deletion cascades atomically."""

    def __init__(self, root, namespace):
        self.directory = Path(root) / checked_namespace(namespace)
        self.path = self.directory / "workspace.sqlite3"
        self.directory.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection, connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS profiles (
                    key TEXT PRIMARY KEY, metadata TEXT NOT NULL, image BLOB NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    user_key TEXT NOT NULL REFERENCES profiles(key) ON DELETE CASCADE,
                    created_at REAL NOT NULL, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS cooldowns (
                    user_key TEXT PRIMARY KEY REFERENCES profiles(key) ON DELETE CASCADE,
                    marked_at REAL NOT NULL
                );
            """)

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA secure_delete = ON")
        try:
            yield connection
        finally:
            connection.close()

    @storage_operation
    def users(self, force=False):
        with self._connection() as connection:
            rows = connection.execute("SELECT metadata, image FROM profiles ORDER BY key").fetchall()
        return [{"metadata": json.loads(metadata), "image": base64.b64encode(image).decode("ascii")}
                for metadata, image in rows]

    @storage_operation
    def has_user(self, key):
        with self._connection() as connection:
            return connection.execute("SELECT 1 FROM profiles WHERE key = ?", (checked_key(key),)).fetchone() is not None

    @storage_operation
    def save_user(self, record, jpeg_bytes):
        checked_key(record["key"])
        with self._connection() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute("SELECT COUNT(*) FROM profiles").fetchone()[0] >= 25:
                raise StorageLimitError("This workspace already contains 25 profiles")
            connection.execute("INSERT INTO profiles (key, metadata, image) VALUES (?, ?, ?)",
                               (record["key"], json.dumps(record, ensure_ascii=False), jpeg_bytes))

    @storage_operation
    def mark(self, row, cooldown_seconds):
        key, now = checked_key(row["UserKey"]), time.time()
        with self._connection() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute("SELECT 1 FROM profiles WHERE key = ?", (key,)).fetchone() is None:
                return False
            previous = connection.execute("SELECT marked_at FROM cooldowns WHERE user_key = ?", (key,)).fetchone()
            if previous and now - previous[0] < cooldown_seconds:
                return False
            connection.execute("INSERT INTO cooldowns (user_key, marked_at) VALUES (?, ?) "
                               "ON CONFLICT(user_key) DO UPDATE SET marked_at = excluded.marked_at", (key, now))
            connection.execute("INSERT INTO events (id, user_key, created_at, payload) VALUES (?, ?, ?, ?)",
                               (uuid4().hex, key, now, json.dumps(row, ensure_ascii=False)))
            return True

    @storage_operation
    def recent(self, limit=20):
        with self._connection() as connection:
            rows = connection.execute("SELECT payload FROM events ORDER BY created_at DESC, id DESC LIMIT ?",
                                      (max(1, min(int(limit), 100)),)).fetchall()
        return [json.loads(row[0]) for row in rows]

    @storage_operation
    def delete_user(self, key):
        with self._connection() as connection, connection:
            deleted = connection.execute("DELETE FROM profiles WHERE key = ?", (checked_key(key),)).rowcount
        return bool(deleted)
