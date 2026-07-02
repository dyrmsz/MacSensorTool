"""
Power sensor: CPU/GPU temperature, fan RPM, and package power via powermetrics.

Sudo-gated -- powermetrics refuses to run at all without root, no partial
no-sudo path exists. Uses `sudo -n` (non-interactive) only: if the one-time
sudoers setup below hasn't been done, read() fails fast instead of hanging
on a password prompt.

One-time setup (run yourself -- macpower never touches sudoers):

    echo "$(whoami) ALL=(ALL) NOPASSWD: /usr/bin/powermetrics" | \\
        sudo tee /etc/sudoers.d/macpower-powermetrics
    sudo visudo -c -f /etc/sudoers.d/macpower-powermetrics

Field names in `powermetrics --format plist` for the smc/cpu_power samplers
are undocumented and can shift across macOS versions, so derive() searches
the parsed structure by key-name substring instead of hardcoding exact
paths. Power values arrive in milliwatts; anything above 50 is assumed to
be mW and scaled down to watts -- real packages draw single/double-digit
watts, so this threshold comfortably separates the two units.
"""

import plistlib
import shutil
import subprocess

from macpower import viz
from macpower.sensors.base import ansi

NAME = "power"
DESCRIPTION = "CPU/GPU temperature, fan RPM, and package power (sudo powermetrics)"

_EMPTY = {
    "authorized": False,
    "cpu_temp_c": None,
    "gpu_temp_c": None,
    "fan_rpm": None,
    "cpu_watts": None,
    "package_watts": None,
}


def available() -> bool:
    return shutil.which("powermetrics") is not None


def read() -> dict:
    try:
        out = subprocess.run(
            ["sudo", "-n", "powermetrics", "-n", "1", "-i", "200",
             "--samplers", "smc,cpu_power", "--format", "plist"],
            capture_output=True, check=True, timeout=10,
        ).stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return {"plist": None}
    return {"plist": out}


def _walk(obj, path=()):
    """Yield (dotted key path, value) for every leaf in a nested plist dict/list."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk(v, path + (k,))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk(v, path + (str(i),))
    else:
        yield ".".join(path), obj


def _find(pairs, *needles):
    """First numeric leaf whose key path contains all `needles` (case-insensitive)."""
    for key, value in pairs:
        low = key.lower()
        if isinstance(value, (int, float)) and all(n in low for n in needles):
            return value
    return None


def _watts(pairs, *needles):
    v = _find(pairs, *needles)
    if v is None:
        return None
    return round(v / 1000, 2) if v > 50 else round(v, 2)


def derive(d: dict) -> dict:
    if not d.get("plist"):
        return dict(_EMPTY)

    try:
        parsed = plistlib.loads(d["plist"])
    except Exception:
        return dict(_EMPTY)

    pairs = list(_walk(parsed))
    cpu_temp = _find(pairs, "cpu", "temp")
    gpu_temp = _find(pairs, "gpu", "temp")

    return {
        "authorized": True,
        "cpu_temp_c": round(cpu_temp, 1) if cpu_temp is not None else None,
        "gpu_temp_c": round(gpu_temp, 1) if gpu_temp is not None else None,
        "fan_rpm": _find(pairs, "fan"),
        "cpu_watts": _watts(pairs, "cpu", "power") or _watts(pairs, "cpu", "watt"),
        "package_watts": (
            _watts(pairs, "package", "power")
            or _watts(pairs, "combined", "power")
            or _watts(pairs, "package", "watt")
        ),
    }


def render(v: dict) -> str:
    if not v["authorized"]:
        return ansi(
            "  (needs passwordless sudo for powermetrics -- see README Setup)", "2"
        )

    rows = []

    def row(label, value):
        if value not in (None, ""):
            rows.append(f"  {label:<16}{value}")

    if v["cpu_temp_c"] is not None:
        pct = max(0.0, min(100.0, (v["cpu_temp_c"] - 30) / 70 * 100))
        row("CPU temp", f"{viz.colored_bar(pct, invert=True)} {v['cpu_temp_c']:.1f} °C")
    if v["gpu_temp_c"] is not None:
        row("GPU temp", f"{v['gpu_temp_c']:.1f} °C")
    if v["fan_rpm"] is not None:
        row("Fan", f"{v['fan_rpm']:.0f} rpm")
    if v["cpu_watts"] is not None:
        row("CPU power", f"{v['cpu_watts']:.2f} W")
    if v["package_watts"] is not None:
        row("Package power", f"{v['package_watts']:.2f} W")
    return "\n".join(rows)


def summary(v: dict) -> str:
    if not v["authorized"]:
        return ""
    parts = []
    if v["cpu_temp_c"] is not None:
        parts.append(f"{v['cpu_temp_c']:.0f}°C")
    if v["fan_rpm"] is not None:
        parts.append(f"{v['fan_rpm']:.0f}rpm")
    return f"\U0001f321️ {' '.join(parts)}" if parts else ""
