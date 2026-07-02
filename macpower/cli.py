"""
macpower CLI.

    python3 macpower.py                    one reading, all sensors
    python3 macpower.py battery            just one sensor
    python3 macpower.py -w [SEC]           live view
    python3 macpower.py --json [-w SEC]    JSON (NDJSON when watching)
    python3 macpower.py --raw [sensor]     raw source data
    python3 macpower.py --list             available sensors
    python3 macpower.py --serve [PORT]     local HTTP JSON endpoints
    python3 macpower.py --menubar          xbar / SwiftBar plugin output
"""

import argparse
import json
import sys
import time
from datetime import datetime

from macpower import sensors


def snapshot(mods) -> dict:
    out = {"timestamp": datetime.now().isoformat(timespec="seconds")}
    for mod in mods:
        out[mod.NAME] = mod.derive(mod.read())
    return out


def render_all(mods) -> str:
    blocks = []
    for mod in mods:
        text = mod.render(mod.derive(mod.read()))
        if text:
            blocks.append(f"{mod.NAME}\n{text}" if len(mods) > 1 else text)
    return "\n\n".join(blocks)


def main():
    p = argparse.ArgumentParser(
        description="Live hardware sensor readout for macOS (battery, memory, system)."
    )
    p.add_argument(
        "sensor", nargs="*",
        help=f"sensors to read (default: all). Available: {', '.join(sensors.REGISTRY)}",
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
                   help="print the raw source data")
    g.add_argument("--list", action="store_true",
                   help="list available sensors")
    g.add_argument("--serve", nargs="?", const=8137, type=int, metavar="PORT",
                   help="serve sensors as local HTTP JSON endpoints (default port 8137)")
    g.add_argument("--menubar", action="store_true",
                   help="emit xbar/SwiftBar plugin format for the macOS menu bar")
    args = p.parse_args()

    if args.list:
        for mod in sensors.ALL:
            ok = "" if mod.available() else "  (unavailable on this machine)"
            print(f"  {mod.NAME:<10}{mod.DESCRIPTION}{ok}")
        return

    try:
        mods = sensors.get(args.sensor or None)
    except KeyError as e:
        sys.exit(str(e.args[0]))
    if not mods:
        sys.exit("No sensors available on this machine.")

    if args.serve is not None:
        from macpower.outputs import server
        server.serve(args.serve)
        return

    if args.menubar:
        from macpower.outputs import menubar
        print(menubar.emit(mods))
        return

    if args.raw:
        print(json.dumps({m.NAME: m.read() for m in mods}, indent=2, default=repr))
        return

    if args.watch:
        try:
            while True:
                if args.json:
                    print(json.dumps(snapshot(mods)), flush=True)  # NDJSON
                else:
                    print("\x1b[2J\x1b[H", end="")                 # clear screen
                    stamp = datetime.now().isoformat(timespec="seconds")
                    print(f"macpower  {stamp}   (Ctrl-C to quit)\n")
                    print(render_all(mods))
                time.sleep(args.watch)
        except KeyboardInterrupt:
            print()
        return

    if args.json:
        print(json.dumps(snapshot(mods), indent=2))
    else:
        print(render_all(mods))
