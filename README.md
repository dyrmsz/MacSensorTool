# macpower

A (nearly) zero-dependency Python sensor monitor for macOS. Reads live
battery, memory, disk, and CPU data straight from the OS, renders it with
gauge bars and a full-screen dashboard, and keeps hours of history so you
don't have to do the math yourself. Stock Python, works on Apple Silicon and
Intel; the one optional feature (real temperature/power/fan numbers) needs a
one-time sudo setup because macOS gates that data behind root.

```
battery
  State           discharging
  Charge          ████████░░░░░░░░░░░░ 40.0%
  Battery power   -6.00 W from battery   (11.29 V x -0.532 A)
  Time to empty   3:12
  Battery temp    30.4 °C
  Cycles          115
  Health          ████████████████░░░░ 82.5%  (5011 of 6075 mAh design)

memory
  Memory used     ██████████████░░░░░░ 68.8%  (11.01 of 16.0 GB)
  Pressure        normal  (53% free system-wide)
  Swap            2.76 of 4.0 GB used

system
  CPU             Apple M1 Pro  (8 cores)
  CPU usage       ████████░░░░░░░░░░░░ 37.9%
  Load avg        3.54  3.92  4.48
  Uptime          8d 23.1h

disk
  Disk used       ███████████░░░░░░░░░ 57.1%  (262.8 of 460.4 GB)
  Free            197.7 GB
  Health (SMART)  Verified
  Activity        0.1 MB/s  (5 transfers/s)
```

## Usage

```bash
python3 macpower.py                 # one reading, all sensors
python3 macpower.py battery         # a single sensor
python3 macpower.py --list          # what's available on this machine
python3 macpower.py -w              # live view, refreshes every 2 s
python3 macpower.py -w 0.5          # custom refresh interval
python3 macpower.py --json          # derived values as JSON
python3 macpower.py -w 5 --json >> power.jsonl    # NDJSON logging
python3 macpower.py --raw battery   # full raw source data, every key
python3 macpower.py --dashboard     # full-screen live TUI: gauges, donut, history
```

## Sensors

| Sensor    | Data | Source |
|-----------|------|--------|
| `battery` | charge %, true charge/discharge watts, adapter negotiation, temperature, cycles, health | `ioreg` AppleSmartBattery |
| `memory`  | used/wired/compressed RAM, memory pressure, swap | `vm_stat`, `sysctl` |
| `system`  | CPU model, live CPU usage %, load averages, uptime, thermal throttling | `sysctl`, `top`, `pmset -g therm` |
| `disk`    | free space %, SMART health, I/O throughput | `shutil.disk_usage`, `diskutil`, `iostat` |
| `power`   | CPU/GPU temperature, fan RPM, package power (needs sudo, see Setup below) | `powermetrics` |

## Setup: real temperature, power, and fan numbers

macOS only exposes CPU/GPU temperature, package power, and fan RPM through
`powermetrics`, which refuses to run at all without root — there's no
partial no-sudo path. macpower calls it non-interactively (`sudo -n`) so it
never hangs on a password prompt; instead, do this **one-time setup** so
it's authorized for good:

```bash
echo "$(whoami) ALL=(ALL) NOPASSWD: /usr/bin/powermetrics" | \
    sudo tee /etc/sudoers.d/macpower-powermetrics
sudo visudo -c -f /etc/sudoers.d/macpower-powermetrics   # sanity-check the syntax
```

This grants passwordless sudo for the `powermetrics` binary only — nothing
else. Until you do this, `python3 macpower.py power` just prints a hint
instead of numbers; everything else works with no setup at all.

## Hours of history

"Max/avg/current over the last 10 min / 30 min / 1 h / 2 h / 4 h" needs
samples collected continuously, so it comes from a small background
collector, not the CLI itself:

```bash
python3 macpower.py --install-agent            # installs + starts it (LaunchAgent)
python3 macpower.py --install-agent --interval 5   # sample every 5 s instead of 10
python3 macpower.py --uninstall-agent          # removes it
```

This writes `~/Library/LaunchAgents/com.macpower.collector.plist` and loads
it with `launchctl`, so it keeps sampling every sensor into a small SQLite
file (`~/Library/Application Support/macpower/history.sqlite3`) even with no
terminal open, and restarts at login. Logs land in `~/Library/Logs/macpower/`.
`--dashboard` and `GET /history/<sensor>` (see below) read from this file —
if you'd rather not install anything persistent, `python3 macpower.py
--collect` runs the same sampler in the foreground for as long as you leave
it open.

## Show it in macOS

**Full-screen dashboard** — `python3 macpower.py --dashboard`: a live
curses TUI with a donut gauge for battery charge, color-coded bars for
everything else, and the history table once the collector above has been
running a while. `q` to quit.

**Menu bar** — install [SwiftBar](https://swiftbar.app) or
[xbar](https://xbarapp.com), then drop this two-line wrapper into the plugin
folder as `macpower.5s.sh` (the `5s` = refresh every 5 seconds):

```bash
#!/bin/zsh
exec python3 /path/to/MacSensorTool/macpower.py --menubar
```

You get a live `🔋 40% -6.0W` in the menu bar with all sensors in the dropdown
(each sensor also has its own short `summary()`, e.g. system's `💻 38% 🔥`
when thermally throttling — whichever includes battery is used as the title
when present).

**HTTP endpoints** — anything local (widgets, dashboards, Shortcuts,
Raycast) can read the sensors as JSON:

```bash
python3 macpower.py --serve          # http://127.0.0.1:8137
curl http://127.0.0.1:8137/sensors          # everything
curl http://127.0.0.1:8137/sensors/battery  # one sensor
curl http://127.0.0.1:8137/raw/battery      # raw source data
curl http://127.0.0.1:8137/history/battery  # max/avg/now per window, per field
```

The server binds to 127.0.0.1 only. To keep it running in the background,
load it as a LaunchAgent (`launchctl`) or just leave a terminal tab open.

## Reading the battery numbers

- **Battery power** is volts × amps measured at the battery itself.
  Positive = charging, negative = discharging. This true charge rate is
  usually less than the adapter's rated watts — the rest powers the
  machine, and charging tapers off near 100%.
- **Health** is current full-charge capacity vs. factory design capacity.

## Adding a sensor

Each sensor is one module in `macpower/sensors/` implementing a small
contract (see `macpower/sensors/base.py`): `NAME`, `DESCRIPTION`,
`available()`, `read()` → raw dict, `derive(raw)` → friendly dict,
`render(derived)` → terminal text. Register it in
`macpower/sensors/__init__.py` and it automatically shows up in the CLI,
`--list`, the HTTP endpoints, `--dashboard`, and the menu bar dropdown.

`derive()` and `render()` are pure functions — test them with mock dicts
(see `tests.py`, runs on any OS: `python3 tests.py`). Visual helpers
(gauge bars, sparklines, the donut) live in `macpower/viz.py`, also pure
and tested the same way.

## Requirements

- macOS (battery sensor needs a Mac with a battery; the rest work anywhere)
- Python 3 — the stock system Python works; standard library only
- The `power` sensor and `--dashboard`'s live history need the one-time
  sudo setup and background collector described above; everything else
  needs neither

## Roadmap

- Network sensor: throughput per interface
- Alerts (`osascript -e 'display notification'`) on thresholds: low
  battery, critical memory pressure, thermal throttling starting
- Native SwiftUI menu bar app reading the HTTP endpoint
