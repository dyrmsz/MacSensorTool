# macpower

A single-file, zero-dependency Python CLI that reads live battery, charging,
and power data on macOS — straight from the `AppleSmartBattery` service in the
I/O Registry. No sudo, no installs, works on Apple Silicon and Intel.

```
  State           discharging
  Charge          41.0%
  Battery power   -15.75 W from battery   (11.22 V x -1.404 A)
  Time to empty   3:18
  Battery temp    30.5 °C
  Cycles          115
  Health          82.6%  (5016 of 6075 mAh design)
```

## Usage

```bash
python3 macpower.py            # one reading
python3 macpower.py -w         # live view, refreshes every 2 s (Ctrl-C to quit)
python3 macpower.py -w 0.5     # live view with a custom refresh interval
python3 macpower.py --json     # derived values as JSON
python3 macpower.py -w 5 --json >> power.jsonl   # NDJSON logging for charge-curve analysis
python3 macpower.py --raw      # full raw ioreg property table (every key)
```

## Reading the numbers

- **Battery power** is volts × amps measured at the battery itself.
  Positive means charging, negative means discharging. This is the true
  charge rate — usually less than the adapter's rated watts, because the
  rest powers the machine, and charging tapers off near 100%.
- **Adapter** shows what the charger negotiated over USB-PD (only shown
  while plugged in).
- **Health** is the battery's current full-charge capacity as a percentage
  of its factory design capacity.

## How it works

`ioreg -a -r -n AppleSmartBattery` emits an XML plist of the battery
service's property table, which macOS updates continuously. The script
parses it with `plistlib` and derives friendly values from it:

- `read_smart_battery()` fetches the raw property table,
- `derive()` computes the derived values,
- `render()` formats them for the terminal.

`derive()` and `render()` are pure functions, so they can be unit-tested
with mock dicts on any OS.

Some ioreg quirks the script handles for you:

- `Voltage` is mV and `Amperage` is mA; negative amperage means discharging.
  ioreg sometimes encodes negative currents as unsigned 32/64-bit integers,
  which `to_signed()` corrects.
- `65535` is ioreg's sentinel for "unknown / still estimating" in the
  time-remaining fields.
- On Apple Silicon, `CurrentCapacity`/`MaxCapacity` are 0–100 percentages;
  on Intel they are mAh. The ratio gives a correct percentage either way.
- `Temperature` is hundredths of a degree Celsius.

Verified against live `ioreg` output on an Apple Silicon MacBook.

## Requirements

- macOS (any Mac with a battery)
- Python 3 — the stock system Python works; standard library only

## Ideas / roadmap

- `sudo powermetrics` integration for CPU/GPU package power and thermal pressure
- A charge-curve plotter fed by `--json` logs
- A menu bar variant
