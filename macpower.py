#!/usr/bin/env python3
"""
macpower.py -- battery / charging / power readout for macOS.

Everything comes from the AppleSmartBattery service in the I/O Registry,
which macOS updates continuously. No sudo, no third-party dependencies,
works on Apple Silicon and Intel.

Usage:
    python3 macpower.py              one reading
    python3 macpower.py -w           live view (2 s refresh)
    python3 macpower.py -w 0.5       live view (custom refresh)
    python3 macpower.py --json       derived values as JSON
    python3 macpower.py -w 5 --json  one JSON object per line (great for logging:
                                     python3 macpower.py -w 5 --json >> power.jsonl)
    python3 macpower.py --raw        full raw ioreg dump (see every available key)

Reading the numbers:
    * "Battery power" is volts x amps measured at the battery itself.
      Positive = charging, negative = discharging. This is the true charge
      rate -- usually less than the adapter's rated watts, because the rest
      runs the machine, and charging tapers off as you approach 100%.
    * "Adapter" shows what the charger negotiated over USB-PD.
"""

import argparse
import json
import plistlib
import shutil
import subprocess
import sys
import time
from datetime import datetime

SENTINEL = 65535  # ioreg's value for "unknown / still estimating"


# ------------------------------------------------------------------ fetching

def read_smart_battery() -> dict:
    """Return the AppleSmartBattery property table as a plain dict."""
    if shutil.which("ioreg") is None:
        sys.exit("ioreg not found -- this script only runs on macOS.")
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


# ------------------------------------------------------------------ deriving

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
        "timestamp": datetime.now().isoformat(timespec="seconds"),
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


# ----------------------------------------------------------------- rendering

def _c(txt, code):
    """Wrap txt in an ANSI color when writing to a real terminal."""
    if sys.stdout.isatty():
        return f"\x1b[{code}m{txt}\x1b[0m"
    return str(txt)


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
        flow_txt = _c(f"+{flow:.2f} W into battery", "32")
    elif flow < 0:
        flow_txt = _c(f"{flow:.2f} W from battery", "33")
    else:
        flow_txt = "0 W (idle)"

    row("State", _c(v["state"], STATE_COLORS.get(v["state"], "0")))
    row("Charge", f"{v['percent']}%" if v["percent"] is not None else None)
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
    row("Battery temp", f"{v['temp_c']} \u00b0C" if v["temp_c"] else None)
    row("Cycles", v["cycle_count"])
    if v["health_pct"]:
        row(
            "Health",
            f"{v['health_pct']}%  "
            f"({v['max_capacity_mah']} of {v['design_mah']} mAh design)",
        )
    return "\n".join(rows)


# ---------------------------------------------------------------------- main

def main():
    p = argparse.ArgumentParser(
        description="Battery / charging / power readout for macOS."
    )
    p.add_argument(
        "-w", "--watch",
        nargs="?", const=2.0, type=float, metavar="SEC",
        help="refresh continuously (default every 2 s)",
    )
    g = p.add_mutually_exclusive_group()
    g.add_argument("--json", action="store_true",
                   help="print derived values as JSON")
    g.add_argument("--raw", action="store_true",
                   help="print the full raw ioreg property table")
    args = p.parse_args()

    if args.raw:
        print(json.dumps(read_smart_battery(), indent=2, default=repr))
        return

    if args.watch:
        try:
            while True:
                v = derive(read_smart_battery())
                if args.json:
                    print(json.dumps(v), flush=True)   # one object per line
                else:
                    print("\x1b[2J\x1b[H", end="")     # clear screen
                    print(f"macpower  {v['timestamp']}   (Ctrl-C to quit)\n")
                    print(render(v))
                time.sleep(args.watch)
        except KeyboardInterrupt:
            print()
        return

    v = derive(read_smart_battery())
    print(json.dumps(v, indent=2) if args.json else render(v))


if __name__ == "__main__":
    main()
