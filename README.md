# macpower

A zero-dependency Python sensor monitor for macOS. Reads live battery,
charging, memory, and CPU data straight from the OS — no sudo, no installs,
stock Python, works on Apple Silicon and Intel.

```
battery
  State           discharging
  Charge          40.0%
  Battery power   -6.00 W from battery   (11.29 V x -0.532 A)
  Time to empty   3:12
  Battery temp    30.4 °C
  Cycles          115
  Health          82.5%  (5011 of 6075 mAh design)

memory
  Memory used     10.56 of 16.0 GB
  Pressure        normal  (61% free system-wide)
  Swap            2.77 of 4.0 GB used

system
  CPU             Apple M1 Pro  (8 cores)
  Load avg        3.54  3.92  4.48
  Uptime          8d 23.1h
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
```

## Sensors

| Sensor    | Data | Source |
|-----------|------|--------|
| `battery` | charge %, true charge/discharge watts, adapter negotiation, temperature, cycles, health | `ioreg` AppleSmartBattery |
| `memory`  | used/wired/compressed RAM, memory pressure, swap | `vm_stat`, `sysctl` |
| `system`  | CPU model, load averages, uptime, thermal throttling | `sysctl`, `pmset -g therm` |

## Show it in macOS

**Menu bar** — install [SwiftBar](https://swiftbar.app) or
[xbar](https://xbarapp.com), then drop this two-line wrapper into the plugin
folder as `macpower.5s.sh` (the `5s` = refresh every 5 seconds):

```bash
#!/bin/zsh
exec python3 /path/to/MacSensorTool/macpower.py --menubar
```

You get a live `🔋 40% -6.0W` in the menu bar with all sensors in the dropdown.

**HTTP endpoints** — anything local (widgets, dashboards, Shortcuts,
Raycast) can read the sensors as JSON:

```bash
python3 macpower.py --serve          # http://127.0.0.1:8137
curl http://127.0.0.1:8137/sensors          # everything
curl http://127.0.0.1:8137/sensors/battery  # one sensor
curl http://127.0.0.1:8137/raw/battery      # raw source data
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
`--list`, the HTTP endpoints, and the menu bar dropdown.

`derive()` and `render()` are pure functions — test them with mock dicts
(see `tests.py`, runs on any OS: `python3 tests.py`).

## Requirements

- macOS (battery sensor needs a Mac with a battery; the rest work anywhere)
- Python 3 — the stock system Python works; standard library only

## Roadmap

- `powermetrics` sensor (sudo): CPU/GPU package power, per-cluster
  frequency, fan speed, real thermal pressure
- Disk sensor: SMART status, free space, I/O rates
- Network sensor: throughput per interface
- Charge-curve plotter fed by `--json` logs
- History ring buffer + `/history` endpoint for graphing dashboards
- Native SwiftUI menu bar app reading the HTTP endpoint
