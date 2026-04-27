"""
Unit Tests - T001
Tests individual server helper functions in isolation (no network required).
Run with: python test_unit.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import json
import socket
import tempfile
import shutil
import unittest

import server
from config import CONTROL_PORT, UPLOAD_PORT, DOWNLOAD_PORT


# ─────────────────────────────────────────────
#  sanitize_filename
# ─────────────────────────────────────────────
class TestSanitizeFilename(unittest.TestCase):

    def test_normal_filename_unchanged(self):
        self.assertEqual(server.sanitize_filename("hello.txt"), "hello.txt")

    def test_removes_forward_slash(self):
        self.assertEqual(server.sanitize_filename("folder/secret.txt"), "foldersecret.txt")

    def test_removes_backslash(self):
        self.assertEqual(server.sanitize_filename("folder\\secret.txt"), "foldersecret.txt")

    def test_removes_dotdot(self):
        # path traversal attempt should be neutralized
        self.assertEqual(server.sanitize_filename("../etc/passwd"), "etcpasswd")

    def test_strips_surrounding_whitespace(self):
        self.assertEqual(server.sanitize_filename("  notes.txt  "), "notes.txt")

    def test_empty_string(self):
        self.assertEqual(server.sanitize_filename(""), "")


# ─────────────────────────────────────────────
#  list_files
# ─────────────────────────────────────────────
class TestListFiles(unittest.TestCase):

    def setUp(self):
        self._orig = server.STORAGE_DIR
        self._tmp = tempfile.mkdtemp()
        server.STORAGE_DIR = self._tmp

    def tearDown(self):
        server.STORAGE_DIR = self._orig
        shutil.rmtree(self._tmp)

    def _make_versioned_file(self, original_name):
        safe = original_name.replace(".", "")
        folder = os.path.join(self._tmp, safe)
        os.makedirs(folder)
        versioned = f"{safe}_v1"
        open(os.path.join(folder, versioned), "wb").close()
        versions = [{
            "version": 1,
            "timestamp": "2026-01-01_00-00-00",
            "original_filename": original_name,
            "versioned_filename": versioned,
        }]
        with open(os.path.join(folder, "versions.json"), "w") as f:
            json.dump(versions, f)

    def test_empty_storage_returns_message(self):
        result = server.list_files()
        self.assertEqual(result, "No files stored yet.")

    def test_single_file_appears_in_listing(self):
        self._make_versioned_file("notes.txt")
        result = server.list_files()
        self.assertIn("notes.txt", result)

    def test_multiple_files_all_listed(self):
        self._make_versioned_file("a.txt")
        self._make_versioned_file("b.txt")
        result = server.list_files()
        self.assertIn("a.txt", result)
        self.assertIn("b.txt", result)

    def test_directory_without_versions_json_is_skipped(self):
        # A folder with no versions.json should not appear in output
        os.makedirs(os.path.join(self._tmp, "orphan"))
        result = server.list_files()
        self.assertEqual(result, "No files stored yet.")


# ─────────────────────────────────────────────
#  get_latest_version
# ─────────────────────────────────────────────
class TestGetLatestVersion(unittest.TestCase):

    def setUp(self):
        self._orig = server.STORAGE_DIR
        self._tmp = tempfile.mkdtemp()
        server.STORAGE_DIR = self._tmp

    def tearDown(self):
        server.STORAGE_DIR = self._orig
        shutil.rmtree(self._tmp)

    def test_missing_file_returns_none(self):
        self.assertIsNone(server.get_latest_version("nonexistent.txt"))

    def test_returns_path_to_latest_version(self):
        safe = "report"
        folder = os.path.join(self._tmp, safe)
        os.makedirs(folder)
        v1 = "report_v1"
        v2 = "report_v2"
        open(os.path.join(folder, v1), "wb").close()
        open(os.path.join(folder, v2), "wb").close()
        versions = [
            {"version": 1, "timestamp": "t1", "original_filename": "report", "versioned_filename": v1},
            {"version": 2, "timestamp": "t2", "original_filename": "report", "versioned_filename": v2},
        ]
        with open(os.path.join(folder, "versions.json"), "w") as f:
            json.dump(versions, f)

        result = server.get_latest_version("report")
        self.assertEqual(result, os.path.join(folder, v2))

    def test_empty_versions_list_returns_none(self):
        safe = "empty"
        folder = os.path.join(self._tmp, safe)
        os.makedirs(folder)
        with open(os.path.join(folder, "versions.json"), "w") as f:
            json.dump([], f)
        self.assertIsNone(server.get_latest_version("empty"))


# ─────────────────────────────────────────────
#  Socket binding
# ─────────────────────────────────────────────
class TestSocketBinding(unittest.TestCase):
    """Verify the three server ports can be bound on this machine."""

    def _can_bind(self, port):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False
        finally:
            s.close()

    def test_control_port_available(self):
        self.assertTrue(self._can_bind(CONTROL_PORT),
                        f"Port {CONTROL_PORT} is already in use — close any running server first.")

    def test_upload_port_available(self):
        self.assertTrue(self._can_bind(UPLOAD_PORT),
                        f"Port {UPLOAD_PORT} is already in use — close any running server first.")

    def test_download_port_available(self):
        self.assertTrue(self._can_bind(DOWNLOAD_PORT),
                        f"Port {DOWNLOAD_PORT} is already in use — close any running server first.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
