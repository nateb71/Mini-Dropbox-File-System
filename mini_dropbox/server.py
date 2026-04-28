import socket
import threading
import os
import json
from datetime import datetime

import time

from config import CONTROL_PORT, UPLOAD_PORT, DOWNLOAD_PORT, DISCOVERY_PORT, BUFFER_SIZE, STORAGE_DIR

# Make sure the storage root folder exists when the module loads
os.makedirs(STORAGE_DIR, exist_ok=True)

# These are set in start_server() and shared across threads
upload_socket   = None
download_socket = None


# Utility helpers

def sanitize_filename(filename):

    # Replace both slash styles and remove any '..' component
    filename = filename.replace("/", "").replace("\\", "")
    filename = filename.replace("..", "")
    return filename.strip()


def list_files():

    names = []
    for entry in os.scandir(STORAGE_DIR):
        if not entry.is_dir():
            continue
        versions_path = os.path.join(entry.path, "versions.json")
        if not os.path.exists(versions_path):
            continue
        with open(versions_path, "r") as f:
            versions = json.load(f)
        if versions:
            # The original filename is the same for every version, grab from latest
            names.append(versions[-1]["original_filename"])

    if not names:
        return "No files stored yet."
    return "\n".join(sorted(names))


def get_latest_version(filename):

    safe   = sanitize_filename(filename)
    folder = os.path.join(STORAGE_DIR, safe)
    versions_path = os.path.join(folder, "versions.json")

    if not os.path.exists(versions_path):
        return None

    with open(versions_path, "r") as f:
        versions = json.load(f)

    if not versions:
        return None

    # versions list is ordered oldest-first, so the last entry is the latest
    latest_entry = versions[-1]
    return os.path.join(folder, latest_entry["versioned_filename"])

# Upload / download over their dedicated sockets

def receive_file(filename):

    conn, addr = upload_socket.accept()
    print(f"[UPLOAD] Connection from {addr}")

    try:
        # The client sends the file size as a plain text line ending with '\n'
        size_header = b""
        while not size_header.endswith(b"\n"):
            chunk = conn.recv(1)
            if not chunk:
                break
            size_header += chunk
        file_size = int(size_header.strip())
        print(f"[UPLOAD] Expecting {file_size} bytes for '{filename}'")

        # Build the versioned folder and load (or create) versions.json
        safe   = sanitize_filename(filename)
        folder = os.path.join(STORAGE_DIR, safe)
        os.makedirs(folder, exist_ok=True)

        versions_path = os.path.join(folder, "versions.json")
        if os.path.exists(versions_path):
            with open(versions_path, "r") as f:
                versions = json.load(f)
        else:
            versions = []

        # Build a timestamp and version number for this upload
        version_num = len(versions) + 1
        timestamp   = datetime.now().strftime("%m-%d-%Y %H-%M")
        versioned_name = f"{safe}_v{version_num}({timestamp})"
        save_path      = os.path.join(folder, versioned_name)

        # Read the file data in BUFFER_SIZE chunks until we have it all
        received = 0
        with open(save_path, "wb") as f:
            while received < file_size:
                to_read = min(BUFFER_SIZE, file_size - received)
                chunk   = conn.recv(to_read)
                if not chunk:
                    break
                f.write(chunk)
                received += len(chunk)

        print(f"[UPLOAD] Saved '{versioned_name}' ({received} bytes)")

        # Record this version in versions.json
        versions.append({
            "version":           version_num,
            "timestamp":         timestamp,
            "original_filename": filename,
            "versioned_filename": versioned_name,
        })
        with open(versions_path, "w") as f:
            json.dump(versions, f, indent=2)

        conn.sendall(b"OK: file uploaded successfully\n")

    except Exception as e:
        print(f"[UPLOAD] Error: {e}")
        conn.sendall(f"ERROR: {e}\n".encode())
    finally:
        conn.close()


def send_file(filename):

    conn, addr = download_socket.accept()
    print(f"[DOWNLOAD] Connection from {addr}")

    try:
        file_path = get_latest_version(filename)
        if file_path is None:
            # Tell the client we don't have this file (size 0 = nothing follows)
            conn.sendall(b"0\n")
            conn.sendall(b"ERROR: file not found\n")
            print(f"[DOWNLOAD] '{filename}' not found")
            return

        file_size = os.path.getsize(file_path)
        print(f"[DOWNLOAD] Sending '{filename}' ({file_size} bytes) to {addr}")

        # Send the size header so the client knows when to stop reading
        conn.sendall(f"{file_size}\n".encode())

        # Stream the file in chunks
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(BUFFER_SIZE)
                if not chunk:
                    break
                conn.sendall(chunk)

        print(f"[DOWNLOAD] Done sending '{filename}'")

    except Exception as e:
        print(f"[DOWNLOAD] Error: {e}")
    finally:
        conn.close()


# Control socket handler

def handle_client(conn, addr):

    print(f"[CONTROL] Connection from {addr}")
    try:
        data = conn.recv(BUFFER_SIZE).decode().strip()
        if not data:
            conn.sendall(b"ERROR: empty command\n")
            return

        parts   = data.split(" ", 1)   # split into [command, rest]
        command = parts[0].upper()

        if command == "LIST":
            result = list_files()
            conn.sendall((result + "\n").encode())

        elif command == "UPLOAD":
            if len(parts) < 2:
                conn.sendall(b"ERROR: UPLOAD requires a filename\n")
                return
            filename = sanitize_filename(parts[1].strip())
            if not filename:
                conn.sendall(b"ERROR: invalid filename\n")
                return
            # Tell the client we're ready, then handle the actual transfer
            conn.sendall(b"READY\n")
            receive_file(filename)

        elif command == "DOWNLOAD":
            if len(parts) < 2:
                conn.sendall(b"ERROR: DOWNLOAD requires a filename\n")
                return
            filename = sanitize_filename(parts[1].strip())
            if not filename:
                conn.sendall(b"ERROR: invalid filename\n")
                return
            conn.sendall(b"READY\n")
            send_file(filename)

        else:
            conn.sendall(f"ERROR: unknown command '{command}'. Use LIST, UPLOAD, or DOWNLOAD\n".encode())

    except Exception as e:
        print(f"[CONTROL] Error handling {addr}: {e}")
    finally:
        conn.close()
        print(f"[CONTROL] Closed connection from {addr}")


# Listener loop (runs in its own thread for each socket)

def accept_loop(server_sock, name):

    while True:
        try:
            conn, addr = server_sock.accept()
            t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            t.start()
        except Exception as e:
            print(f"[{name}] Accept error: {e}")
            break


# Discovery broadcaster

def broadcast_presence():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    # connect trick: routes without sending data, reveals our LAN IP
    tmp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    tmp.connect(("8.8.8.8", 80))
    my_ip = tmp.getsockname()[0]
    tmp.close()
    subnet_broadcast = ".".join(my_ip.split(".")[:3]) + ".255"
    msg = f"MINIDROPBOX_SERVER:{my_ip}".encode()
    print(f"[DISCOVERY] Broadcasting presence as {my_ip} on port {DISCOVERY_PORT}")
    while True:
        sock.sendto(msg, (subnet_broadcast, DISCOVERY_PORT))
        time.sleep(2)


# Entry point

def start_server():
    """
    Bind all three sockets (control, upload, download) and start a listener
    thread for the control socket.  The upload and download sockets are stored
    as module-level globals so receive_file / send_file can use them.
    Blocks forever waiting for the control listener thread to finish (it won't
    under normal operation, so the server runs until you press Ctrl+C).
    """
    global upload_socket, download_socket

    def make_socket(port):
        # SO_REUSEADDR lets us restart the server quickly without 'address in use' errors
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("0.0.0.0", port))
        s.listen(5)
        return s

    control_sock  = make_socket(CONTROL_PORT)
    upload_socket = make_socket(UPLOAD_PORT)
    download_socket = make_socket(DOWNLOAD_PORT)

    print(f"[SERVER] Control  socket listening on port {CONTROL_PORT}")
    print(f"[SERVER] Upload   socket listening on port {UPLOAD_PORT}")
    print(f"[SERVER] Download socket listening on port {DOWNLOAD_PORT}")
    print("[SERVER] Ready — waiting for clients...\n")

    threading.Thread(target=broadcast_presence, daemon=True).start()

    # Only the control socket needs an accept loop; upload/download sockets are
    # accepted inside receive_file / send_file which are called from handle_client
    t = threading.Thread(target=accept_loop, args=(control_sock, "CONTROL"), daemon=True)
    t.start()
    t.join()  # block main thread so the server stays alive


if __name__ == "__main__":
    start_server()
