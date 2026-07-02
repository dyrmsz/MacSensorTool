"""
--dashboard: a full-screen live TUI -- gauges, a donut for battery charge,
and a max/avg/now history table, refreshed every ~1.5 s.

build_frame() is a pure function (sensor modules + a history connection ->
list of (text, ansi_color_code) lines), so the layout can be sanity-checked
by printing it plainly without a real terminal. The curses loop below just
paints whatever build_frame() returns, mapping each ansi color code to a
curses color pair -- curses can't interpret embedded ANSI escapes, which is
why viz.py's bar()/donut() return plain text and the color comes separately
from viz.color_for_pct().
"""

import curses
import time
from datetime import datetime

from macpower import history, viz
from macpower.sensors import battery, disk, memory, power, system

REFRESH_MS = 1500

# (sensor module, derived key, label) shown in the history table
HISTORY_METRICS = [
    (battery, "percent", "Battery %"),
    (system, "cpu_usage_pct", "CPU %"),
    (power, "cpu_temp_c", "CPU °C"),
    (disk, "percent_used", "Disk %"),
]


def _line(text, color="0"):
    return (text, color)


def _kv(label, value, color="0"):
    return _line(f"  {label:<16}{value}", color)


def _bar_row(label, pct, extra="", invert=False):
    if pct is None:
        return []
    return [_kv(label, f"{viz.bar(pct, invert=invert)} {pct}%{extra}", viz.color_for_pct(pct, invert))]


def _battery_lines(v):
    lines = [_line("BATTERY", "1")]
    if v["percent"] is not None:
        donut_rows = viz.donut(v["percent"])
        color = viz.color_for_pct(v["percent"])
        mid = len(donut_rows) // 2
        remaining = v["time_to_empty"] or v["time_to_full"]
        remaining_label = "to empty" if v["time_to_empty"] else "to full"
        for i, r in enumerate(donut_rows):
            side = ""
            if i == mid - 1:
                side = f"  {v['percent']:.0f}%  {v['state']}"
            elif i == mid:
                side = f"  {v['battery_watts']:+.2f} W"
            elif i == mid + 1 and remaining:
                side = f"  {remaining} {remaining_label}"
            lines.append(_line(f"  {r}{side}", color))
    if v["health_pct"]:
        lines += _bar_row("Health", v["health_pct"])
    return lines


def _memory_lines(v):
    lines = [_line("MEMORY", "1")]
    if v["used_pct"] is not None:
        lines += _bar_row("Used", v["used_pct"], f"  ({v['used_gb']} of {v['total_gb']} GB)", invert=True)
    if v["pressure"]:
        color = {"normal": "32", "warning": "33", "critical": "31"}.get(v["pressure"], "0")
        lines.append(_kv("Pressure", v["pressure"], color))
    if v["swap_total_gb"]:
        lines.append(_kv("Swap", f"{v['swap_used_gb']} of {v['swap_total_gb']} GB"))
    return lines


def _system_lines(v):
    lines = [_line("SYSTEM", "1")]
    if v["cpu"]:
        cpu = f"{v['cpu']}  ({v['cores']} cores)" if v["cores"] else v["cpu"]
        lines.append(_kv("CPU", cpu))
    if v["cpu_usage_pct"] is not None:
        lines += _bar_row("Usage", v["cpu_usage_pct"])
    if v["load_1m"] is not None:
        lines.append(_kv("Load avg", f"{v['load_1m']}  {v['load_5m']}  {v['load_15m']}"))
    if v["throttled"]:
        lines.append(_kv("Thermal", f"throttled to {v['cpu_speed_limit_pct']}%", "31"))
    return lines


def _disk_lines(v):
    lines = [_line("DISK", "1")]
    if v["percent_used"] is not None:
        extra = f"  ({v['used_gb']} of {v['total_gb']} GB, {v['free_gb']} GB free)"
        lines += _bar_row("Used", v["percent_used"], extra, invert=True)
    if v["smart"]:
        lines.append(_kv("SMART", v["smart"], "32" if v["healthy"] else "31"))
    if v["throughput_mbps"] is not None:
        lines.append(_kv("Activity", f"{v['throughput_mbps']} MB/s"))
    return lines


def _power_lines(v):
    lines = [_line("POWER", "1")]
    if not v["authorized"]:
        lines.append(_line("  not authorized -- see README Setup for passwordless sudo", "2"))
        return lines
    if v["cpu_temp_c"] is not None:
        pct = max(0.0, min(100.0, (v["cpu_temp_c"] - 30) / 70 * 100))
        lines += _bar_row("CPU temp", round(pct, 1), f"  ({v['cpu_temp_c']:.1f} °C)", invert=True)
    if v["fan_rpm"] is not None:
        lines.append(_kv("Fan", f"{v['fan_rpm']:.0f} rpm"))
    if v["package_watts"] is not None:
        lines.append(_kv("Package power", f"{v['package_watts']:.2f} W"))
    return lines


PANEL_BUILDERS = {
    "battery": _battery_lines,
    "memory": _memory_lines,
    "system": _system_lines,
    "disk": _disk_lines,
    "power": _power_lines,
}


def _history_lines(conn, mods):
    lines = [_line("HISTORY  (max / avg / now)", "1")]
    windows = [label for label, _ in history.WINDOWS]
    lines.append(_line("  {:<12}".format("") + "".join(f"{w:>14}" for w in windows)))

    metrics = [(mod, key, label) for mod, key, label in HISTORY_METRICS if mod in mods]
    any_data = False
    for mod, key, label in metrics:
        stats = history.window_stats(conn, mod.NAME, key)
        cells = []
        for w in windows:
            s = stats[w]
            if s["now"] is None:
                cells.append("...".rjust(14))
            else:
                any_data = True
                cells.append(f"{s['max']:.0f}/{s['avg']:.0f}/{s['now']:.0f}".rjust(14))
        lines.append(_line(f"  {label:<12}" + "".join(cells)))

    if metrics and not any_data:
        lines.append(_line("  (no samples yet -- run --collect or --install-agent)", "2"))
    return lines


def build_frame(mods, conn, now=None):
    """[(text, ansi_color_code)] describing one full dashboard refresh."""
    now = time.time() if now is None else now
    stamp = datetime.fromtimestamp(now).isoformat(timespec="seconds")
    lines = [_line(f"macpower  {stamp}   (q to quit)", "1"), _line("")]
    for mod in mods:
        builder = PANEL_BUILDERS.get(mod.NAME)
        if builder is None:
            continue
        lines += builder(mod.derive(mod.read()))
        lines.append(_line(""))
    lines += _history_lines(conn, mods)
    return lines


_COLOR_PAIRS = {"31": 1, "32": 2, "33": 3, "36": 4}  # ansi code -> curses pair id


def _attr_for(code):
    if code == "1":
        return curses.A_BOLD
    if code == "2":
        return curses.A_DIM
    pair_id = _COLOR_PAIRS.get(code)
    return curses.color_pair(pair_id) if pair_id else curses.A_NORMAL


def _loop(stdscr, mods):
    curses.curs_set(0)
    stdscr.timeout(REFRESH_MS)
    if curses.has_colors():
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_RED, -1)
        curses.init_pair(2, curses.COLOR_GREEN, -1)
        curses.init_pair(3, curses.COLOR_YELLOW, -1)
        curses.init_pair(4, curses.COLOR_CYAN, -1)

    conn = history.connect()
    while True:
        stdscr.erase()
        max_y, max_x = stdscr.getmaxyx()
        for y, (text, code) in enumerate(build_frame(mods, conn)):
            if y >= max_y:
                break
            try:
                stdscr.addstr(y, 0, text[:max_x - 1], _attr_for(code))
            except curses.error:
                pass  # bottom-right cell write; harmless
        stdscr.refresh()
        key = stdscr.getch()
        if key in (ord("q"), ord("Q"), 27):
            break


def run(mods):
    curses.wrapper(_loop, mods)
