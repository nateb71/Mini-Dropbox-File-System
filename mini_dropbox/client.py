import socket
import os

from config import CONTROL_PORT, UPLOAD_PORT, DOWNLOAD_PORT, DISCOVERY_PORT, BUFFER_SIZE


def discover_server(timeout=10):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", DISCOVERY_PORT))
    sock.settimeout(timeout)
    print(f"[DISCOVERY] Listening for server on port {DISCOVERY_PORT} (up to {timeout}s)...")
    try:
        data, _ = sock.recvfrom(1024)
        msg = data.decode()
        if msg.startswith("MINIDROPBOX_SERVER:"):
            ip = msg.split(":", 1)[1]
            print(f"[DISCOVERY] Found server at {ip}")
            return ip
    except socket.timeout:
        print("[DISCOVERY] No server found via broadcast.")
        return None
    finally:
        sock.close()


SERVER_HOST = discover_server() or os.environ.get("SERVER_HOST") or "127.0.0.1"


# -----------------------------
# CONTROL CONNECTION
# -----------------------------
def send_command(command):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((SERVER_HOST, CONTROL_PORT))
        sock.sendall((command + "\n").encode())

        response = sock.recv(BUFFER_SIZE).decode().strip()
        return response


# -----------------------------
# LIST FILES
# -----------------------------
def list_files():
    response = send_command("LIST")
    print("\n[FILES ON SERVER]")
    print(response)


# -----------------------------
# UPLOAD FILE
# -----------------------------
def upload_file(filepath):
    if not os.path.exists(filepath):
        print("File does not exist.")
        return

    filename = os.path.basename(filepath)

    # Step 1: Tell server we want to upload
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as control_sock:
        control_sock.connect((SERVER_HOST, CONTROL_PORT))
        control_sock.sendall(f"UPLOAD {filename}\n".encode())

        response = control_sock.recv(BUFFER_SIZE).decode().strip()
        if response != "READY":
            print("Server error:", response)
            return

    # Step 2: Send file over upload socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as upload_sock:
        upload_sock.connect((SERVER_HOST, UPLOAD_PORT))

        file_size = os.path.getsize(filepath)
        upload_sock.sendall(f"{file_size}\n".encode())

        with open(filepath, "rb") as f:
            while True:
                chunk = f.read(BUFFER_SIZE)
                if not chunk:
                    break
                upload_sock.sendall(chunk)

        # Receive confirmation
        response = upload_sock.recv(BUFFER_SIZE).decode().strip()
        print(response)


# -----------------------------
# DOWNLOAD FILE
# -----------------------------
def download_file(filename, save_dir="downloads"):
    os.makedirs(save_dir, exist_ok=True)
    save_path = os.path.join(save_dir, filename)

    # Step 1: Tell server we want to download
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as control_sock:
        control_sock.connect((SERVER_HOST, CONTROL_PORT))
        control_sock.sendall(f"DOWNLOAD {filename}\n".encode())

        response = control_sock.recv(BUFFER_SIZE).decode().strip()
        if response != "READY":
            print("Server error:", response)
            return

    # Step 2: Receive file over download socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as download_sock:
        download_sock.connect((SERVER_HOST, DOWNLOAD_PORT))

        # Read file size
        size_header = b""
        while not size_header.endswith(b"\n"):
            chunk = download_sock.recv(1)
            if not chunk:
                break
            size_header += chunk

        file_size = int(size_header.strip())

        if file_size == 0:
            error_msg = download_sock.recv(BUFFER_SIZE).decode()
            print(error_msg)
            return

        received = 0
        with open(save_path, "wb") as f:
            while received < file_size:
                chunk = download_sock.recv(min(BUFFER_SIZE, file_size - received))
                if not chunk:
                    break
                f.write(chunk)
                received += len(chunk)

        print(f"Downloaded '{filename}' ({received} bytes)")


# -----------------------------
# SIMPLE CLI
# -----------------------------
def main():
    while True:
        print("\nCommands: LIST, UPLOAD <file>, DOWNLOAD <file>, EXIT")
        cmd = input(">> ").strip()

        if cmd.upper() == "LIST":
            list_files()

        elif cmd.upper().startswith("UPLOAD"):
            parts = cmd.split(" ", 1)
            if len(parts) < 2:
                print("Usage: UPLOAD <filepath>")
                continue
            upload_file(parts[1])

        elif cmd.upper().startswith("DOWNLOAD"):
            parts = cmd.split(" ", 1)
            if len(parts) < 2:
                print("Usage: DOWNLOAD <filename>")
                continue
            download_file(parts[1])

        elif cmd.upper() == "EXIT":
            break

        else:
            print("Unknown command")


if __name__ == "__main__":
    main()