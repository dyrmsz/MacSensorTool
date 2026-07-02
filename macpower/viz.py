"""
Visual primitives shared by every sensor's render() and the --dashboard TUI.

Pure functions of numbers -> text (no I/O), so they're unit-tested directly
with plain numbers, same convention as sensors/*.derive().

bar()/donut()/sparkline() return *plain* text with no color baked in --
color_for_pct() returns a matching ANSI code separately. Terminal render()
functions wrap the two together with sensors.base.ansi(); the curses
dashboard instead maps color_for_pct()'s code to a curses color pair,
since curses can't interpret embedded ANSI escapes.
"""

import math

from macpower.sensors.base import ansi

BAR_FULL = "█"
BAR_EMPTY = "░"
SPARK_CHARS = "▁▂▃▄▅▆▇█"


def color_for_pct(pct, invert=False):
    """Green/yellow/red ANSI code for a 0-100 value.

    invert=True when a high value is bad (temperature, % full disk/memory)
    instead of good (battery charge, health, free space).
    """
    if pct is None:
        return "0"
    pct = max(0.0, min(100.0, pct))
    if invert:
        pct = 100 - pct
    if pct >= 60:
        return "32"
    if pct >= 30:
        return "33"
    return "31"


def bar(pct, width=20, invert=False):
    """Plain Unicode block gauge, e.g. '███████░░░'. Pair with color_for_pct()."""
    if pct is None:
        return BAR_EMPTY * width
    clamped = max(0.0, min(100.0, pct))
    filled = round(width * clamped / 100)
    return BAR_FULL * filled + BAR_EMPTY * (width - filled)


def colored_bar(pct, width=20, invert=False):
    """bar() + color_for_pct() combined, for plain-terminal render() calls."""
    return ansi(bar(pct, width, invert), color_for_pct(pct, invert))


def sparkline(values, width=40):
    """Downsample a series to at most `width` Unicode block characters."""
    values = [v for v in values if v is not None]
    if not values:
        return ""
    if len(values) > width:
        step = len(values) / width
        bucketed = []
        for i in range(width):
            chunk = values[int(i * step):int((i + 1) * step)] or [values[-1]]
            bucketed.append(sum(chunk) / len(chunk))
        values = bucketed
    lo, hi = min(values), max(values)
    span = hi - lo or 1
    top = len(SPARK_CHARS) - 1
    return "".join(SPARK_CHARS[min(top, int((v - lo) / span * top))] for v in values)


def donut(pct, diameter=9):
    """A small circular gauge as a list of plain text rows, filled clockwise
    from the top. Pair with color_for_pct() for coloring. The grid is twice
    as wide as tall since terminal character cells are roughly twice as
    tall as they are wide.
    """
    pct = 0.0 if pct is None else max(0.0, min(100.0, pct))
    fraction = pct / 100
    radius = diameter / 2
    inner = radius * 0.55
    rows = []
    for y in range(diameter):
        dy = (y + 0.5) - radius
        cells = []
        for x in range(diameter * 2):
            dx = ((x + 0.5) / 2) - radius
            dist = math.hypot(dx, dy)
            if inner <= dist <= radius:
                angle = (math.atan2(dx, -dy) / (2 * math.pi)) % 1.0
                cells.append(BAR_FULL if angle < fraction else BAR_EMPTY)
            else:
                cells.append(" ")
        rows.append("".join(cells))
    return rows
