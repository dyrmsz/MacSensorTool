# macpower

Zero-dependency (except one optional sudo-gated sensor) Python package that
reads live hardware sensors on macOS: battery/charging (I/O Registry),
memory pressure (vm_stat/sysctl), CPU/load/thermal throttling and usage %
(sysctl/pmset/top), disk space/health/throughput (shutil/diskutil/iostat),
and CPU/GPU temperature + fan + package power (sudo powermetrics). Multiple
outputs: terminal (with gauge bars), JSON/NDJSON, a local HTTP server (incl.
`/history`), xbar/SwiftBar menu bar format, and a full-screen curses
dashboard. Hours-long history is sampled by an optional LaunchAgent into a
local SQLite file.

## Run it

```bash
python3 macpower.py                 # one reading, all sensors
python3 macpower.py battery         # one sensor (see --list)
python3 macpower.py -w              # live view, 2 s refresh (-w 0.5 for faster)
python3 macpower.py --json          # derived values as JSON (add -w for NDJSON logging)
python3 macpower.py --raw [sensor]  # raw source data, every key
python3 macpower.py --serve         # HTTP JSON on http://127.0.0.1:8137
python3 macpower.py --menubar       # xbar/SwiftBar plugin output
python3 macpower.py --dashboard     # full-screen curses TUI: gauges, donut, history
python3 macpower.py --collect       # foreground history sampler (Ctrl-C to stop)
python3 macpower.py --install-agent # same sampler as a LaunchAgent (see README Setup)
python3 tests.py                    # unit tests (pure functions, run anywhere)
```

## Architecture

```
macpower.py                  thin shim so `python3 macpower.py` keeps working
macpower/
  cli.py                     argparse + watch loop + collector loop + dispatch
  viz.py                     pure gauge bar / sparkline / donut + color thresholds
  history.py                 SQLite log + window_stats() for 10m/30m/1h/2h/4h
  agent.py                   LaunchAgent install/uninstall (never invoked automatically)
  sensors/
    base.py                  the sensor contract (documented there) + helpers
    battery.py  memory.py  system.py  disk.py  power.py
    __init__.py              registry: ALL list + get()
  outputs/
    server.py                stdlib ThreadingHTTPServer, 127.0.0.1 only
    menubar.py                xbar/SwiftBar format
    dashboard.py              curses TUI; build_frame() is pure, the loop just paints it
tests.py                     unittest on mock dicts
```

**To add a sensor**: write a module with `NAME`, `DESCRIPTION`, `available()`,
`read()` (the only impure function), `derive(raw)`, `render(derived)`, and
optionally `summary(derived)` for the menu bar; register it in
`macpower/sensors/__init__.py`. It automatically appears in the CLI, `--list`,
`--serve` endpoints (incl. `/history`), and `--menubar`. To also appear in
`--dashboard`, add a panel builder + entry to `outputs/dashboard.py`'s
`PANEL_BUILDERS` / `HISTORY_METRICS`. Add derive/render tests to tests.py
with mock dicts — that is how everything here is tested cross-OS.

`viz.py`'s `bar()`/`donut()`/`sparkline()` return **plain text, no color**
baked in -- `color_for_pct()` returns a matching ANSI code separately.
Terminal `render()` functions combine the two via `viz.colored_bar()` or
`sensors.base.ansi()`; the curses dashboard instead maps the same color
codes to curses color pairs, since curses can't interpret embedded ANSI
escapes. Don't reintroduce baked-in ANSI inside `bar()`/`donut()` themselves.

## Domain quirks (intentional -- do not "fix")

Battery (`sensors/battery.py`):
- `Voltage` is mV, `Amperage` is mA. Battery watts = V x A / 1e6.
  Negative amperage = discharging.
- ioreg sometimes encodes negative currents as unsigned 32- or 64-bit ints
  (e.g. `18446744073709548123` means `-3493` mA). `to_signed()` corrects
  this; the thresholds are safe because real battery currents are only a
  few thousand mA.
- `65535` is ioreg's sentinel for "unknown / still estimating" in the
  time-remaining fields.
- On Apple Silicon, `CurrentCapacity`/`MaxCapacity` are 0-100 percentages;
  on Intel they are mAh. The ratio gives a correct percentage either way.
  `AppleRawCurrentCapacity`/`AppleRawMaxCapacity` are always mAh.
  Health % = `AppleRawMaxCapacity` / `DesignCapacity`.
- `Temperature` is hundredths of a degree C.
- `AdapterDetails` only carries meaningful data while `ExternalConnected`
  is true; many Apple adapters embed their wattage in their name, which
  `render()` dedupes.
- Battery watts (actual charge rate) is normally lower than the adapter's
  rated watts: the rest powers the machine, and charging tapers near 100%.

Memory / system:
- `kern.memorystatus_level` is the system-wide free-memory percentage that
  `memory_pressure` reports; >40 normal, >20 warning, else critical.
- `pmset -g therm` prints "No ... recorded" notes when thermals are nominal;
  `CPU_Speed_Limit < 100` means macOS is throttling.
- `kern.cp_time` (the usual BSD tick-counter sysctl) does not exist on this
  macOS/Apple Silicon setup -- `system.py` gets instantaneous CPU usage % by
  parsing the second of two `top -l 2 -n 0 -s 0` samples instead (the first
  sample is discarded; it's the delta since top's last internal reading,
  not a live one). Adds ~0.7 s to every `system` read().

Disk (`sensors/disk.py`):
- Space comes from `shutil.disk_usage("/")` (stdlib, no subprocess) rather
  than parsing `df` -- simpler and already structured.
- `iostat -d -c 2 -w 1 disk0` prints two rows: the first is the average
  since boot, the second is the live 1 s sample. Only the second is used.
  Order of arguments matters: flags first, drive name last, or iostat
  rejects them (`-d disk0 -c 2` fails; `-d -c 2 disk0` works).

Power (`sensors/power.py`):
- `powermetrics` refuses to run at all without root (no partial data
  without sudo) -- see README "Setup" for the one-time passwordless
  sudoers.d entry. `read()` uses `sudo -n` only, deliberately never falls
  back to an interactive prompt, so it fails fast instead of hanging.
- Field names in `--format plist` output for the `smc`/`cpu_power`
  samplers are undocumented and can shift across macOS versions, so
  `derive()` searches the parsed plist by key-name substring
  (temp/fan/power) instead of hardcoding exact paths. Power values arrive
  in milliwatts; anything above 50 is assumed to be mW and divided by 1000
  (real packages draw single/double-digit watts).

History (`history.py`):
- One SQLite row per `(timestamp, sensor, JSON blob of derive())` rather
  than a normalized schema -- simplest thing that works at this data
  volume (a handful of sensors sampled every ~10 s for days is a few
  thousand rows). Retention is pruned to 48 h on every write, well past
  the longest (4 h) window.
- The collector (`--collect` / `--install-agent`) samples whatever sensors
  are available, including `power` -- if the sudoers setup above hasn't
  been done, `power`'s fields are just `None` and get skipped, they don't
  break the loop.

## Status

- Battery, memory, system, and disk verified against live command output
  on an Apple Silicon MacBook (2026-07-02). The plugged-in adapter path
  (battery) is still unverified on real hardware (machine was on battery).
- `power` sensor: field-name parsing in `derive()` is written defensively
  (substring search, see Domain quirks above) but has not yet been
  verified against real `powermetrics --format plist` output on this
  machine, since that requires the one-time sudoers setup in README
  "Setup" first. Verify the parsed field names once that's done.
- `--dashboard`'s curses rendering was checked non-interactively (runs
  without crashing, correct layout/colors captured via a pty) but not
  eyeballed live in a real terminal -- do that once, especially after any
  layout change.
- Extension ideas live in README "Roadmap".

## Conventions

- Python 3 standard library only -- keep it dependency-free so it runs on
  a stock Mac with no install step. (`power` is the one sensor that needs
  something extra: a one-time sudoers entry, documented in README, never
  applied automatically.)
- Per sensor, `read()` is the only impure function; keep `derive()`/`render()`
  pure and covered in tests.py with mock dicts.
- The HTTP server binds 127.0.0.1 only; keep it that way.
- Nothing in this codebase edits `/etc/sudoers` or calls `launchctl load`
  on its own -- `--install-agent`/`--uninstall-agent` and the sudoers.d
  setup are explicit, user-invoked actions (persistent background process,
  system auth file). Keep it that way; don't wire either into another flag
  or run automatically.
