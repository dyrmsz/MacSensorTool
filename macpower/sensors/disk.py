"""
Disk sensor: free space, SMART health, and I/O throughput for the boot volume.

Sources (all no-sudo):
    shutil.disk_usage("/")      total/used/free bytes (stdlib, no subprocess)
    diskutil info /             SMART Status line
    iostat -d -c 2 -w 1 disk0   second row is the live 1s sample; the first
                                 row is the since-boot average and is dropped
"""

import re
import shutil

from macpower import viz
from macpower.sensors.base import ansi, sh

NAME = "disk"
DESCRIPTION = "Free space, SMART health, and I/O throughput (shutil / diskutil / iostat)"


def available() -> bool:
    return shutil.which("diskutil") is not None


def read() -> dict:
    usage = shutil.disk_usage("/")
    return {
        "total": usage.total,
        "used": usage.used,
        "free": usage.free,
        "diskutil": sh("diskutil", "info", "/"),
        "iostat": sh("iostat", "-d", "-c", "2", "-w", "1", "disk0"),
    }


def derive(d: dict) -> dict:
    total_gb = round(d["total"] / 1024**3, 1)
    used_gb = round(d["used"] / 1024**3, 1)
    free_gb = round(d["free"] / 1024**3, 1)
    percent_used = round(d["used"] / d["total"] * 100, 1) if d["total"] else None

    sm = re.search(r"SMART Status:\s*(.+)", d["diskutil"])
    smart = sm.group(1).strip() if sm else None

    lines = [l for l in d["iostat"].strip().splitlines() if l.strip()]
    cols = lines[-1].split() if lines else []
    kbps = tps = mbps = None
    if len(cols) == 3:
        try:
            kbps, tps, mbps = float(cols[0]), int(cols[1]), float(cols[2])
        except ValueError:
            pass

    return {
        "total_gb": total_gb,
        "used_gb": used_gb,
        "free_gb": free_gb,
        "percent_used": percent_used,
        "smart": smart,
        "healthy": (smart == "Verified") if smart else None,
        "throughput_mbps": mbps,
        "transfers_per_sec": tps,
        "kb_per_transfer": kbps,
    }


def render(v: dict) -> str:
    rows = []

    def row(label, value):
        if value not in (None, ""):
            rows.append(f"  {label:<16}{value}")

    if v["percent_used"] is not None:
        gauge = viz.colored_bar(v["percent_used"], invert=True)
        row("Disk used", f"{gauge} {v['percent_used']}%  ({v['used_gb']} of {v['total_gb']} GB)")
    row("Free", f"{v['free_gb']} GB" if v["free_gb"] is not None else None)
    if v["smart"]:
        row("Health (SMART)", ansi(v["smart"], "32" if v["healthy"] else "31"))
    if v["throughput_mbps"] is not None:
        row("Activity", f"{v['throughput_mbps']} MB/s  ({v['transfers_per_sec']} transfers/s)")
    return "\n".join(rows)


def summary(v: dict) -> str:
    pct = v["percent_used"]
    return f"\U0001f4be {pct}%" if pct is not None else "\U0001f4be"
