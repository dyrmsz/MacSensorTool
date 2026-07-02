"""
System sensor: CPU model, load averages, uptime, usage %, and thermal
throttling.

Sources (all no-sudo):
    sysctl machdep.cpu.brand_string / hw.ncpu / vm.loadavg / kern.boottime
    pmset -g therm       CPU speed limit when macOS is thermally throttling
    top -l 2 -n 0 -s 0   two quick samples; the second "CPU usage" line is
                         the live delta (the first is since the last sample
                         top took, which we discard). ~0.7 s wall time.
"""

import re
import shutil
import time

from macpower import viz
from macpower.sensors.base import ansi, sh

NAME = "system"
DESCRIPTION = "CPU model, load average, uptime, thermal throttling (sysctl / pmset)"


def available() -> bool:
    return shutil.which("sysctl") is not None


def read() -> dict:
    return {
        "cpu_brand": sh("sysctl", "-n", "machdep.cpu.brand_string"),
        "ncpu": sh("sysctl", "-n", "hw.ncpu"),
        "loadavg": sh("sysctl", "-n", "vm.loadavg"),
        "boottime": sh("sysctl", "-n", "kern.boottime"),
        "therm": sh("pmset", "-g", "therm"),
        "top": sh("top", "-l", "2", "-n", "0", "-s", "0"),
        "now": time.time(),
    }


def derive(d: dict) -> dict:
    load = None
    m = re.search(r"\{?\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)", d["loadavg"])
    if m:
        load = [float(m.group(i)) for i in (1, 2, 3)]

    uptime_h = None
    bm = re.search(r"sec = (\d+)", d["boottime"])
    if bm:
        uptime_h = round((d["now"] - int(bm.group(1))) / 3600, 1)

    # pmset -g therm prints "CPU_Speed_Limit = 100" style lines while macOS
    # is tracking thermal pressure; "No ... recorded" notes mean nominal.
    tm = re.search(r"CPU_Speed_Limit\s*=\s*(\d+)", d["therm"])
    speed_limit = int(tm.group(1)) if tm else None
    throttled = speed_limit is not None and speed_limit < 100

    # Two "CPU usage" lines from top -l 2; the second is the live sample.
    usage_lines = re.findall(r"CPU usage:\s*[\d.]+%\s*user,\s*[\d.]+%\s*sys,\s*([\d.]+)%\s*idle", d["top"])
    cpu_usage_pct = round(100 - float(usage_lines[-1]), 1) if usage_lines else None

    return {
        "cpu": d["cpu_brand"].strip() or None,
        "cores": int(d["ncpu"]) if d["ncpu"].strip() else None,
        "cpu_usage_pct": cpu_usage_pct,
        "load_1m": load[0] if load else None,
        "load_5m": load[1] if load else None,
        "load_15m": load[2] if load else None,
        "uptime_h": uptime_h,
        "cpu_speed_limit_pct": speed_limit,
        "throttled": throttled,
    }


def render(v: dict) -> str:
    rows = []

    def row(label, value):
        if value not in (None, ""):
            rows.append(f"  {label:<16}{value}")

    cpu = v["cpu"]
    if cpu and v["cores"]:
        cpu += f"  ({v['cores']} cores)"
    row("CPU", cpu)
    if v["cpu_usage_pct"] is not None:
        row("CPU usage", f"{viz.colored_bar(v['cpu_usage_pct'])} {v['cpu_usage_pct']}%")
    if v["load_1m"] is not None:
        row("Load avg", f"{v['load_1m']}  {v['load_5m']}  {v['load_15m']}")
    if v["uptime_h"] is not None:
        days, hours = divmod(v["uptime_h"], 24)
        row("Uptime", f"{int(days)}d {hours:.1f}h" if days else f"{v['uptime_h']} h")
    if v["throttled"]:
        row("Thermal", ansi(f"throttled to {v['cpu_speed_limit_pct']}% CPU speed", "31"))
    elif v["cpu_speed_limit_pct"] is not None:
        row("Thermal", ansi("nominal (100% CPU speed)", "32"))
    return "\n".join(rows)


def summary(v: dict) -> str:
    cpu = f" {v['cpu_usage_pct']}%" if v["cpu_usage_pct"] is not None else ""
    hot = " 🔥" if v["throttled"] else ""
    return f"\U0001f4bb{cpu}{hot}"
