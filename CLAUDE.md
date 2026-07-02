# macpower

Single-file, zero-dependency Python CLI that reads live battery / charging /
power data on macOS from the `AppleSmartBattery` service in the I/O Registry.

## Run it

```bash
python3 macpower.py            # one reading
python3 macpower.py -w         # live view, 2 s refresh (-w 0.5 for faster)
python3 macpower.py --json     # derived values as JSON (add -w for NDJSON logging)
python3 macpower.py --raw      # full raw ioreg property table, every key
```

## How it works

- Data source: `ioreg -a -r -n AppleSmartBattery` -> XML plist -> `plistlib.loads`.
- `read_smart_battery()` fetches, `derive()` computes friendly values,
  `render()` formats for the terminal. Keep these separated: `derive()` and
  `render()` are pure functions so they can be tested with mock dicts on any
  OS (that is how they were tested originally).

## Domain quirks (intentional -- do not "fix")

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

## Status / known gaps

- Logic was verified against mocked ioreg data only, never on real
  hardware. First job: run it on this Mac, compare against `--raw` output,
  and fix any keys or encodings that differ from the assumptions above.
- No README yet.
- Extension ideas: `sudo powermetrics` integration for CPU/GPU package
  power and thermal pressure, a charge-curve plotter fed by `--json` logs,
  a menu bar variant.

## Conventions

- Python 3 standard library only -- keep it dependency-free so it runs on
  a stock Mac with no install step.
- Preserve the fetch / derive / render separation and add tests as pure
  functions on mock dicts where possible.
