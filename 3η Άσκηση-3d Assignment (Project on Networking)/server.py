import argparse
import os
import socket
import struct

BUF = 4096


def recv_line(conn) -> str:
    """Read bytes until newline and return decoded line without newline."""
    data = bytearray()
    while True:
        b = conn.recv(1)
        if not b:
            raise ConnectionError("Client disconnected while sending filename")
        data += b
        if b == b"\n":
            break
    return data.decode(errors="replace").strip()


def safe_join(base_dir: str, filename: str) -> str:
    """
    Prevent path traversal. Only allow files inside base_dir.
    """
    base_dir = os.path.abspath(base_dir)
    candidate = os.path.abspath(os.path.join(base_dir, filename))
    if not candidate.startswith(base_dir + os.sep):
        raise ValueError("Invalid filename/path")
    return candidate


def send_file(conn, path: str):
    """Send 8-byte size (uint64, network order), then file bytes in chunks."""
    size = os.path.getsize(path)
    conn.sendall(struct.pack("!Q", size))

    with open(path, "rb") as f:
        while True:
            chunk = f.read(BUF)
            if not chunk:
                break
            conn.sendall(chunk)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5050)
    parser.add_argument(
        "--dir",
        default="server_data",
        help="Directory that contains s001.m4s ... s160.m4s",
    )
    args = parser.parse_args()

    # Make directory absolute (relative to this script)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    files_dir = args.dir
    if not os.path.isabs(files_dir):
        files_dir = os.path.join(base_dir, files_dir)
    files_dir = os.path.abspath(files_dir)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((args.host, args.port))
        s.listen()

        print(f"Server listening on {args.host}:{args.port}")
        print(f"Serving directory: {files_dir}")

        while True:
            conn, addr = s.accept()
            with conn:
                try:
                    filename = recv_line(conn)
                    path = safe_join(files_dir, filename)

                    if not os.path.isfile(path):
                        # size=0 => not found
                        conn.sendall(struct.pack("!Q", 0))
                        continue

                    send_file(conn, path)

                except Exception:
                    # Keep server alive even if a client misbehaves
                    try:
                        conn.sendall(struct.pack("!Q", 0))
                    except Exception:
                        pass


if __name__ == "__main__":
    main()
