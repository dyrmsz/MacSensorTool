"""
xbar / SwiftBar plugin output: puts the sensors in the macOS menu bar.

Install SwiftBar (https://swiftbar.app) or xbar (https://xbarapp.com), then
drop a tiny wrapper in the plugin folder, e.g. macpower.5s.sh:

    #!/bin/zsh
    exec python3 /path/to/MacSensorTool/macpower.py --menubar

Format: first line = menu bar text, "---" separator, then dropdown lines.
"""

from macpower.sensors import battery


def emit(mods) -> str:
    snapshots = [(mod, mod.derive(mod.read())) for mod in mods]

    # Menu bar title: battery summary if we have it, else the first sensor.
    title = ""
    for mod, v in snapshots:
        if mod is battery:
            title = mod.summary(v)
            break
    if not title and snapshots:
        mod, v = snapshots[0]
        title = getattr(mod, "summary", lambda _: mod.NAME)(v)

    lines = [title, "---"]
    for mod, v in snapshots:
        lines.append(f"{mod.NAME} | size=12")
        for row in mod.render(v).splitlines():
            # monospaced dropdown rows; xbar/SwiftBar params come after |
            lines.append(f"{row} | font=Menlo size=11")
        lines.append("---")
    lines.append("Refresh | refresh=true")
    return "\n".join(lines)
