"""
Battery / charging / power sensor.

Everything comes from the AppleSmartBattery service in the I/O Registry,
which macOS updates continuously. No sudo, works on Apple Silicon and Intel.

Reading the numbers:
    * "Battery power" is volts x amps measured at the battery itself.
      Positive = charging, negative = discharging. This is the true charge
      rate -- usually less than the adapter's rated watts, because the rest
      runs the machine, and charging tapers off as you approach 100%.
    * "Adapter" shows what the charger negotiated over USB-PD.
"""

import plistlib
import shutil
import subprocess
import sys

from macpower import viz
from macpower.sensors.base import ansi

NAME = "battery"
DESCRIPTION = "Battery charge, power flow, health, and adapter (AppleSmartBattery)"

SENTINEL = 65535  # ioreg's value for "unknown / still estimating"


def available() -> bool:
    return shutil.which("ioreg") is not None


def read() -> dict:
    """Return the AppleSmartBattery property table as a plain dict."""
    out = subprocess.run(
        ["ioreg", "-a", "-r", "-n", "AppleSmartBattery"],
        capture_output=True,
        check=True,
    ).stdout
    if not out.strip():
        sys.exit("No AppleSmartBattery service found (desktop Mac, maybe?).")
    data = plistlib.loads(out)
    return data[0] if isinstance(data, list) else data


def to_signed(v):
    """
    ioreg sometimes reports negative currents as unsigned 32- or 64-bit ints
    (e.g. 18446744073709548123 instead of -3493 mA). Undo that.
    Real battery currents are a few thousand mA, so these thresholds are safe.
    """
    if isinstance(v, int):
        if v >= 2**63:
            return v - 2**64
        if v >= 2**31:
            return v - 2**32
    return v


def fmt_minutes(v):
    """ioreg minute count -> 'H:MM', or None if unknown."""
    if not v or v == SENTINEL:
        return None
    return f"{v // 60}:{v % 60:02d}"


def derive(d: dict) -> dict:
    """Boil the raw property table down to the values you actually want."""
    volts = d.get("Voltage", 0) / 1000                            # mV -> V
    amps = to_signed(d.get("Amperage", 0)) / 1000                 # mA -> A (rolling avg)
    i_amps = to_signed(d.get("InstantAmperage", d.get("Amperage", 0))) / 1000

    external = bool(d.get("ExternalConnected"))
    charging = bool(d.get("IsCharging"))
    full = bool(d.get("FullyCharged"))

    if full and external:
        state = "full (on AC)"
    elif charging:
        state = "charging"
    elif external:
        state = "plugged in, not charging"
    else:
        state = "discharging"

    # On Apple Silicon CurrentCapacity/MaxCapacity are 0-100; on Intel they
    # are mAh. The ratio gives the right percentage either way.
    cur, mx = d.get("CurrentCapacity"), d.get("MaxCapacity")
    percent = round(100 * cur / mx, 1) if cur is not None and mx else None

    raw_max = d.get("AppleRawMaxCapacity")
    design = d.get("DesignCapacity")
    health = round(100 * raw_max / design, 1) if raw_max and design else None

    ad = d.get("AdapterDetails") or {}
    adapter = None
    if external and ad.get("Watts"):
        adapter = {
            "description": ad.get("Name") or ad.get("Description") or "adapter",
            "rated_watts": ad.get("Watts"),
            "volts": (ad.get("AdapterVoltage") or 0) / 1000 or None,
            "amps": (ad.get("Current") or 0) / 1000 or None,
        }

    temp = d.get("Temperature")  # hundredths of a degree C

    return {
        "state": state,
        "percent": percent,
        "battery_watts": round(volts * amps, 2),
        "instant_watts": round(volts * i_amps, 2),
        "volts": round(volts, 2),
        "amps": round(amps, 3),
        "adapter": adapter,
        "temp_c": round(temp / 100, 1) if temp else None,
        "cycle_count": d.get("CycleCount"),
        "health_pct": health,
        "capacity_mah": d.get("AppleRawCurrentCapacity"),
        "max_capacity_mah": raw_max,
        "design_mah": design,
        "time_to_full": fmt_minutes(d.get("AvgTimeToFull")),
        "time_to_empty": fmt_minutes(d.get("AvgTimeToEmpty")),
    }


STATE_COLORS = {
    "charging": "32",                    # green
    "discharging": "33",                 # yellow
    "full (on AC)": "36",                # cyan
    "plugged in, not charging": "36",
}


def render(v: dict) -> str:
    rows = []

    def row(label, value):
        if value not in (None, ""):
            rows.append(f"  {label:<16}{value}")

    flow = v["battery_watts"]
    if flow > 0:
        flow_txt = ansi(f"+{flow:.2f} W into battery", "32")
    elif flow < 0:
        flow_txt = ansi(f"{flow:.2f} W from battery", "33")
    else:
        flow_txt = "0 W (idle)"

    row("State", ansi(v["state"], STATE_COLORS.get(v["state"], "0")))
    if v["percent"] is not None:
        row("Charge", f"{viz.colored_bar(v['percent'])} {v['percent']}%")
    row("Battery power", f"{flow_txt}   ({v['volts']} V x {v['amps']} A)")
    if abs(v["instant_watts"] - flow) > 0.5:
        row("Instantaneous", f"{v['instant_watts']:+.2f} W")
    if v["adapter"]:
        a = v["adapter"]
        negotiated = ""
        if a["volts"] and a["amps"]:
            negotiated = f"  ({a['volts']:.1f} V x {a['amps']:.2f} A negotiated)"
        desc = a["description"]
        # Many adapters embed their wattage in the name ("96W USB-C Power
        # Adapter") -- don't print it twice.
        watts_prefix = ""
        if f"{a['rated_watts']}W" not in desc.replace(" W", "W"):
            watts_prefix = f"{a['rated_watts']} W "
        row("Adapter", f"{watts_prefix}{desc}{negotiated}")
    row("Time to full", v["time_to_full"])
    row("Time to empty", v["time_to_empty"])
    row("Battery temp", f"{v['temp_c']} °C" if v["temp_c"] else None)
    row("Cycles", v["cycle_count"])
    if v["health_pct"]:
        row(
            "Health",
            f"{viz.colored_bar(v['health_pct'])} {v['health_pct']}%  "
            f"({v['max_capacity_mah']} of {v['design_mah']} mAh design)",
        )
    return "\n".join(rows)


def summary(v: dict) -> str:
    """One short line for menu bar / status displays."""
    icon = "⚡" if v["state"] in ("charging", "full (on AC)") else "\U0001f50b"
    pct = f"{v['percent']:.0f}%" if v["percent"] is not None else "?"
    return f"{icon} {pct} {v['battery_watts']:+.1f}W"
