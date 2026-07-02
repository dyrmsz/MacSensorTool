# macpower

Zero-dependency Python package that reads live hardware sensors on macOS:
battery/charging (I/O Registry), memory pressure (vm_stat/sysctl), and
CPU/load/thermal throttling (sysctl/pmset). Multiple outputs: terminal,
JSON/NDJSON, a local HTTP server, and xbar/SwiftBar menu bar format.

## Run it

```bash
python3 macpower.py                 # one reading, all sensors
python3 macpower.py battery         # one sensor (see --list)
python3 macpower.py -w              # live view, 2 s refresh (-w 0.5 for faster)
python3 macpower.py --json          # derived values as JSON (add -w for NDJSON logging)
python3 macpower.py --raw [sensor]  # raw source data, every key
python3 macpower.py --serve         # HTTP JSON on http://127.0.0.1:8137
python3 macpower.py --menubar       # xbar/SwiftBar plugin output
python3 tests.py                    # unit tests (pure functions, run anywhere)
```

## Architecture

```
macpower.py                  thin shim so `python3 macpower.py` keeps working
macpower/
  cli.py                     argparse + watch loop + dispatch
  sensors/
    base.py                  the sensor contract (documented there) + helpers
    battery.py  memory.py  system.py
    __init__.py              registry: ALL list + get()
  outputs/
    server.py                stdlib ThreadingHTTPServer, 127.0.0.1 only
    menubar.py               xbar/SwiftBar format
tests.py                     unittest on mock dicts
```

**To add a sensor**: write a module with `NAME`, `DESCRIPTION`, `available()`,
`read()` (the only impure function), `derive(raw)`, `render(derived)`, and
optionally `summary(derived)` for the menu bar; register it in
`macpower/sensors/__init__.py`. It automatically appears in the CLI, `--list`,
`--serve` endpoints, and `--menubar`. Add derive/render tests to tests.py
with mock dicts — that is how everything here is tested cross-OS.

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

## Status

- Battery, memory, and system verified against live command output on an
  Apple Silicon MacBook (2026-07-02). The plugged-in adapter path is still
  unverified on real hardware (machine was on battery).
- Extension ideas live in README "Roadmap".

## Conventions

- Python 3 standard library only -- keep it dependency-free so it runs on
  a stock Mac with no install step.
- Per sensor, `read()` is the only impure function; keep `derive()`/`render()`
  pure and covered in tests.py with mock dicts.
- The HTTP server binds 127.0.0.1 only; keep it that way.
