"""
Memory sensor: RAM usage, memory pressure, swap.

Sources (all no-sudo):
    vm_stat                          page counts (wired, active, compressed, ...)
    sysctl hw.memsize                physical RAM in bytes
    sysctl kern.memorystatus_level   system-wide free-memory percentage
    sysctl vm.swapusage              "total = 4096.00M  used = 2831.75M ..."
"""

import re
import shutil

from macpower.sensors.base import ansi, sh

NAME = "memory"
DESCRIPTION = "RAM usage, memory pressure, and swap (vm_stat / sysctl)"


def available() -> bool:
    return shutil.which("vm_stat") is not None and shutil.which("sysctl") is not None


def read() -> dict:
    return {
        "vm_stat": sh("vm_stat"),
        "memsize": sh("sysctl", "-n", "hw.memsize"),
        "free_level": sh("sysctl", "-n", "kern.memorystatus_level"),
        "swapusage": sh("sysctl", "-n", "vm.swapusage"),
    }


def _pages(text: str) -> dict:
    """'Pages wired down:  141630.' lines -> {'wired down': 141630, ...}"""
    out = {}
    for m in re.finditer(r'^"?Pages\s+([^:"]+)"?:\s+(\d+)\.', text, re.M):
        out[m.group(1).strip()] = int(m.group(2))
    return out


def derive(d: dict) -> dict:
    pages = _pages(d["vm_stat"])
    m = re.search(r"page size of (\d+)", d["vm_stat"])
    page = int(m.group(1)) if m else 16384
    gb = lambda n: round(n * page / 1024**3, 2)

    total_b = int(d["memsize"]) if d["memsize"].strip() else None
    wired = pages.get("wired down", 0)
    active = pages.get("active", 0)
    compressed = pages.get("occupied by compressor", 0)
    # "used" the way Activity Monitor counts it: app (active + speculative
    # counted loosely) + wired + compressed. We keep it simple and explicit.
    used = wired + active + compressed

    swap = {}
    sm = re.search(
        r"total = ([\d.]+)M\s+used = ([\d.]+)M\s+free = ([\d.]+)M", d["swapusage"]
    )
    if sm:
        swap = {
            "total_gb": round(float(sm.group(1)) / 1024, 2),
            "used_gb": round(float(sm.group(2)) / 1024, 2),
        }

    free_level = int(d["free_level"]) if d["free_level"].strip() else None
    if free_level is None:
        pressure = None
    elif free_level > 40:
        pressure = "normal"
    elif free_level > 20:
        pressure = "warning"
    else:
        pressure = "critical"

    return {
        "total_gb": round(total_b / 1024**3, 1) if total_b else None,
        "used_gb": gb(used),
        "wired_gb": gb(wired),
        "compressed_gb": gb(compressed),
        "free_pct": free_level,
        "pressure": pressure,
        "swap_used_gb": swap.get("used_gb"),
        "swap_total_gb": swap.get("total_gb"),
    }


PRESSURE_COLORS = {"normal": "32", "warning": "33", "critical": "31"}


def render(v: dict) -> str:
    rows = []

    def row(label, value):
        if value not in (None, ""):
            rows.append(f"  {label:<16}{value}")

    if v["used_gb"] is not None and v["total_gb"]:
        row("Memory used", f"{v['used_gb']} of {v['total_gb']} GB")
    row("Wired", f"{v['wired_gb']} GB" if v["wired_gb"] else None)
    row("Compressed", f"{v['compressed_gb']} GB" if v["compressed_gb"] else None)
    if v["pressure"]:
        label = v["pressure"]
        if v["free_pct"] is not None:
            label += f"  ({v['free_pct']}% free system-wide)"
        row("Pressure", ansi(label, PRESSURE_COLORS.get(v["pressure"], "0")))
    if v["swap_total_gb"]:
        row("Swap", f"{v['swap_used_gb']} of {v['swap_total_gb']} GB used")
    return "\n".join(rows)


def summary(v: dict) -> str:
    return f"\U0001f9e0 {v['used_gb']}/{v['total_gb']}GB"
