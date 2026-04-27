"""
Integration Tests - T002
Tests the full client-server workflow over the loopback interface (127.0.0.1).
The server is started in a background thread automatically — no manual setup needed.

Run with: python test_integration.py
NOTE: Ports 5000-5003 must be free before running.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

# ── Discovery bootstrap ────────────────────────────────────────────────────────
# client.py calls discover_server() at import time.  We broadcast a fake
# discovery packet on loopback so it resolves to 127.0.0.1 instantly instead
# of waiting the full 10-second timeout.
import socket as _socket
import threading as _threading
import time as _time
from config import DISCOVERY_PORT

def _send_discovery_packets():
    s = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
    for _ in range(60):          # keep sending for ~6 s to cover any timing slack
        try:
            s.sendto(b"MINIDROPBOX_SERVER:127.0.0.1", ("127.0.0.1", DISCOVERY_PORT))
        except Exception:
            pass
        _time.sleep(0.1)
    s.close()

_threading.Thread(target=_send_discovery_packets, daemon=True).start()
_time.sleep(0.05)   # small head-start so the socket is sending before client binds

# ── Normal imports (after discovery bootstrap) ────────────────────────────────
import shutil
import tempfile
import unittest

import server
import client


# ─────────────────────────────────────────────
#  Shared server lifecycle
# ─────────────────────────────────────────────
_server_started = False

def _start_server_once():
    global _server_started
    if _server_started:
        return
    _server_started = True
    _threading.Thread(target=server.start_server, daemon=True).start()
    _time.sleep(0.5)   # give server time to bind all three ports


# ─────────────────────────────────────────────
#  IT-01: LIST on empty server
# ─────────────────────────────────────────────
class TestIT01List(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._orig_storage = server.STORAGE_DIR
        cls._tmpdir = tempfile.mkdtemp()
        server.STORAGE_DIR = cls._tmpdir
        client.SERVER_HOST = "127.0.0.1"
        _start_server_once()

    @classmethod
    def tearDownClass(cls):
        server.STORAGE_DIR = cls._orig_storage
        shutil.rmtree(cls._tmpdir)

    def test_list_empty_server(self):
        """IT-01: LIST command returns a 'no files' message when storage is empty."""
        response = client.send_command("LIST")
        self.assertIn("No files", response,
                      f"Expected 'No files' message, got: {response!r}")


# ─────────────────────────────────────────────
#  IT-02: UPLOAD then LIST
# ─────────────────────────────────────────────
class TestIT02Upload(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._orig_storage = server.STORAGE_DIR
        cls._tmpdir = tempfile.mkdtemp()
        server.STORAGE_DIR = cls._tmpdir
        client.SERVER_HOST = "127.0.0.1"
        _start_server_once()

        # create a small file to upload — must be OUTSIDE the storage dir
        cls._upload_file = tempfile.NamedTemporaryFile(
            delete=False, suffix=".txt",
        )
        cls._upload_file.write(b"Hello from IT-02 upload test")
        cls._upload_file.close()
        cls._filename = os.path.basename(cls._upload_file.name)

    @classmethod
    def tearDownClass(cls):
        server.STORAGE_DIR = cls._orig_storage
        try:
            os.unlink(cls._upload_file.name)
        except FileNotFoundError:
            pass
        shutil.rmtree(cls._tmpdir)

    def test_upload_succeeds(self):
        """IT-02a: upload_file() completes without raising an exception."""
        try:
            client.upload_file(self._upload_file.name)
        except Exception as e:
            self.fail(f"upload_file() raised an exception: {e}")

    def test_uploaded_file_appears_in_list(self):
        """IT-02b: After upload, the filename appears in the LIST response."""
        client.upload_file(self._upload_file.name)
        response = client.send_command("LIST")
        self.assertIn(self._filename, response,
                      f"Uploaded file '{self._filename}' not found in LIST: {response!r}")


# ─────────────────────────────────────────────
#  IT-03: UPLOAD then DOWNLOAD, verify contents
# ─────────────────────────────────────────────
class TestIT03Download(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._orig_storage = server.STORAGE_DIR
        cls._tmpdir = tempfile.mkdtemp()
        server.STORAGE_DIR = cls._tmpdir
        client.SERVER_HOST = "127.0.0.1"
        _start_server_once()

        cls._content = b"Round-trip file content for IT-03"
        cls._upload_file = tempfile.NamedTemporaryFile(
            delete=False, suffix=".txt",
        )
        cls._upload_file.write(cls._content)
        cls._upload_file.close()
        cls._filename = os.path.basename(cls._upload_file.name)

        cls._download_dir = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        server.STORAGE_DIR = cls._orig_storage
        try:
            os.unlink(cls._upload_file.name)
        except FileNotFoundError:
            pass
        shutil.rmtree(cls._tmpdir)
        shutil.rmtree(cls._download_dir)

    def test_download_after_upload_matches_original(self):
        """IT-03: File downloaded after upload must be byte-for-byte identical."""
        client.upload_file(self._upload_file.name)
        client.download_file(self._filename, save_dir=self._download_dir)

        downloaded_path = os.path.join(self._download_dir, self._filename)
        self.assertTrue(os.path.exists(downloaded_path),
                        "Downloaded file was not created.")

        with open(downloaded_path, "rb") as f:
            downloaded = f.read()
        self.assertEqual(downloaded, self._content,
                         "Downloaded file contents do not match the original.")

    def test_download_nonexistent_file_does_not_crash(self):
        """IT-03b: Requesting a file that does not exist should not raise an exception."""
        try:
            client.download_file("does_not_exist.txt", save_dir=self._download_dir)
        except Exception as e:
            self.fail(f"download_file() raised an unexpected exception: {e}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
