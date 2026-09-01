import argparse
import csv
import datetime as dt
import json
import os
import socket
import struct
import subprocess
import time
from pathlib import Path

BUF = 4096


def recv_exact(sock, n: int) -> bytes:
    """Read exactly n bytes (or raise ConnectionError)."""
    data = b""
    while len(data) < n:
        packet = sock.recv(n - len(data))
        if not packet:
            raise ConnectionError("Socket closed early")
        data += packet
    return data


def download_one(ip: str, port: int, filename: str, out_dir: Path, timeout: float) -> int:
    """
    Download one file. Return bytes written.
    Protocol:
      - send: "filename\n"
      - recv: 8 bytes uint64 size, then size bytes data
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / filename

    with socket.create_connection((ip, port), timeout=timeout) as s:
        s.sendall((filename + "\n").encode())

        size = struct.unpack("!Q", recv_exact(s, 8))[0]
        if size == 0:
            raise FileNotFoundError(filename)

        remaining = size
        written = 0
        with open(out_path, "wb") as f:
            while remaining > 0:
                chunk = s.recv(min(BUF, remaining))
                if not chunk:
                    raise ConnectionError("Socket closed mid-file")
                f.write(chunk)
                written += len(chunk)
                remaining -= len(chunk)

    return written


def run_transfer(nA: int, nB: int, ipA: str, ipB: str, portA: int, portB: int,
                 files_total: int, out_dir: Path, timeout: float) -> dict:
    """
    Download files_total segments using round-robin:
    request nA from A, then nB from B, repeat, until finished.
    """
    start = time.perf_counter()

    total_bytes = 0
    file_id = 1

    while file_id <= files_total:
        for _ in range(nA):
            if file_id > files_total:
                break
            filename = f"s{file_id:03d}.m4s"
            total_bytes += download_one(ipA, portA, filename, out_dir, timeout)
            file_id += 1

        for _ in range(nB):
            if file_id > files_total:
                break
            filename = f"s{file_id:03d}.m4s"
            total_bytes += download_one(ipB, portB, filename, out_dir, timeout)
            file_id += 1

    end = time.perf_counter()
    total_time = end - start
    mbps = (total_bytes * 8) / (total_time * 1_000_000) if total_time > 0 else 0.0

    return {
        "total_time_sec": total_time,
        "total_bytes": total_bytes,
        "avg_rate_mbps": mbps,
    }


def run_iperf3(iperf3_path: str, server_ip: str, seconds: int, reverse: bool, port: int) -> dict:
    """
    Runs iperf3 client and returns a small dict with throughput.
    Uses JSON output when available (iperf3 -J).
    Note: iperf3 server must already be running on the remote host.
    """
    cmd = [iperf3_path, "-c", server_ip, "-t", str(seconds), "-p", str(port), "-J"]
    if reverse:
        cmd.insert(3, "-R")  # iperf3 -c <ip> -R ...

    p = subprocess.run(cmd, capture_output=True, text=True)

    if p.returncode != 0:
        return {"ok": False, "error": (p.stderr or p.stdout).strip()}

    try:
        data = json.loads(p.stdout)
        # Keep both fields because reverse mode can be confusing; store both.
        end = data.get("end", {})
        sum_sent = end.get("sum_sent", {}) or {}
        sum_received = end.get("sum_received", {}) or {}
        return {
            "ok": True,
            "bps_sum_sent": sum_sent.get("bits_per_second"),
            "bps_sum_received": sum_received.get("bits_per_second"),
        }
    except Exception:
        return {"ok": False, "error": "Could not parse iperf3 JSON output"}


def append_csv(csv_path: Path, row: dict):
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = csv_path.exists()

    fieldnames = list(row.keys())
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            w.writeheader()
        w.writerow(row)


def ratios_default():
    # Exactly as in the assignment list
    return [(1, 5), (1, 4), (1, 3), (1, 2), (1, 1), (2, 1), (3, 1), (4, 1), (5, 1)]


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--ipA", required=True)
    common.add_argument("--ipB", required=True)
    common.add_argument("--portA", type=int, default=5050)
    common.add_argument("--portB", type=int, default=5050)
    common.add_argument("--files", type=int, default=160)
    common.add_argument("--timeout", type=float, default=10.0)
    common.add_argument("--scenario", required=True, help="e.g. S1 or S2")
    common.add_argument("--location", required=True, help="e.g. near, mid, far")
    common.add_argument("--csv", default="results.csv")
    common.add_argument("--repeats", type=int, default=1)
    common.add_argument("--outroot", default="downloads")

    # Optional iperf3 measurement
    common.add_argument("--iperf", action="store_true", help="Also run iperf3 tests and log them")
    common.add_argument("--iperf3", default="iperf3")
    common.add_argument("--iperf-seconds", type=int, default=10)
    common.add_argument("--iperf-port", type=int, default=5201)
    common.add_argument("--iperf-reverse", action="store_true", default=True)

    p_run = sub.add_parser("run", parents=[common])
    p_run.add_argument("nA", type=int)
    p_run.add_argument("nB", type=int)

    p_sweep = sub.add_parser("sweep", parents=[common])

    args = parser.parse_args()

    csv_path = Path(args.csv)
    outroot = Path(args.outroot)

    ratios = [(args.nA, args.nB)] if args.cmd == "run" else ratios_default()

    for rep in range(1, args.repeats + 1):
        for (nA, nB) in ratios:
            # Separate output dir per experiment to avoid mixing files
            out_dir = outroot / f"{args.scenario}_{args.location}_nA{nA}_nB{nB}_rep{rep}"

            iperfA = iperfB = None
            if args.iperf:
                iperfA = run_iperf3(args.iperf3, args.ipA, args.iperf_seconds, args.iperf_reverse, args.iperf_port)
                iperfB = run_iperf3(args.iperf3, args.ipB, args.iperf_seconds, args.iperf_reverse, args.iperf_port)

            try:
                transfer = run_transfer(
                    nA=nA, nB=nB,
                    ipA=args.ipA, ipB=args.ipB,
                    portA=args.portA, portB=args.portB,
                    files_total=args.files,
                    out_dir=out_dir,
                    timeout=args.timeout,
                )
                status = "OK"
                err = ""
            except Exception as e:
                transfer = {"total_time_sec": None, "total_bytes": None, "avg_rate_mbps": None}
                status = "FAIL"
                err = str(e)

            row = {
                "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
                "scenario": args.scenario,
                "location": args.location,
                "repeat": rep,
                "nA": nA,
                "nB": nB,
                "ipA": args.ipA,
                "ipB": args.ipB,
                "portA": args.portA,
                "portB": args.portB,
                "files": args.files,
                "status": status,
                "error": err,
                "total_time_sec": transfer["total_time_sec"],
                "total_bytes": transfer["total_bytes"],
                "avg_rate_mbps": transfer["avg_rate_mbps"],
                "iperfA_ok": (iperfA or {}).get("ok") if iperfA else None,
                "iperfA_bps_sent": (iperfA or {}).get("bps_sum_sent") if iperfA else None,
                "iperfA_bps_recv": (iperfA or {}).get("bps_sum_received") if iperfA else None,
                "iperfB_ok": (iperfB or {}).get("ok") if iperfB else None,
                "iperfB_bps_sent": (iperfB or {}).get("bps_sum_sent") if iperfB else None,
                "iperfB_bps_recv": (iperfB or {}).get("bps_sum_received") if iperfB else None,
                "out_dir": str(out_dir),
            }
            append_csv(csv_path, row)

            print(f"[{status}] scenario={args.scenario} loc={args.location} nA={nA} nB={nB} rep={rep} "
                  f"time={row['total_time_sec']}s avg={row['avg_rate_mbps']} Mbps -> {out_dir}")


if __name__ == "__main__":
    main()
