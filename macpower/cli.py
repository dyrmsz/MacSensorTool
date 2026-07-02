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
    python3 macpower.py --dashboard        full-screen live TUI
    python3 macpower.py --collect          run the history sampler (foreground)
    python3 macpower.py --install-agent    install it as a background LaunchAgent
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


def collect(mods, interval: float) -> None:
    from macpower import history

    conn = history.connect()
    print(f"macpower collector: {len(mods)} sensor(s) every {interval}s -> {history.DB_PATH}")
    try:
        while True:
            now = time.time()
            for mod in mods:
                try:
                    history.record(conn, now, mod.NAME, mod.derive(mod.read()))
                except Exception:
                    continue  # one bad sensor shouldn't kill the collector
            time.sleep(interval)
    except KeyboardInterrupt:
        print()


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
    g.add_argument("--dashboard", action="store_true",
                   help="full-screen live dashboard (gauges, sparklines, history)")
    g.add_argument("--collect", action="store_true",
                   help="run the history sampler in the foreground (Ctrl-C to stop)")
    g.add_argument("--install-agent", action="store_true",
                   help="install --collect as a background LaunchAgent")
    g.add_argument("--uninstall-agent", action="store_true",
                   help="remove the LaunchAgent installed by --install-agent")
    p.add_argument("--interval", type=float, default=10.0, metavar="SEC",
                   help="sampling interval for --collect/--install-agent (default 10 s)")
    args = p.parse_args()

    if args.list:
        for mod in sensors.ALL:
            ok = "" if mod.available() else "  (unavailable on this machine)"
            print(f"  {mod.NAME:<10}{mod.DESCRIPTION}{ok}")
        return

    if args.install_agent:
        from macpower import agent
        agent.install(args.interval)
        return

    if args.uninstall_agent:
        from macpower import agent
        agent.uninstall()
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

    if args.dashboard:
        from macpower.outputs import dashboard
        dashboard.run(mods)
        return

    if args.collect:
        collect(mods, args.interval)
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
