#!/usr/bin/env python3
"""
Unit tests for the pure derive()/render() functions, using mock raw data.
Runs on any OS: python3 tests.py
"""

import unittest

from macpower.sensors import battery, memory, system


class BatteryTests(unittest.TestCase):
    RAW = {
        "Voltage": 11221,
        "Amperage": -1404,
        "InstantAmperage": -1404,
        "ExternalConnected": False,
        "IsCharging": False,
        "FullyCharged": False,
        "CurrentCapacity": 41,
        "MaxCapacity": 100,
        "AppleRawCurrentCapacity": 1993,
        "AppleRawMaxCapacity": 5016,
        "DesignCapacity": 6075,
        "CycleCount": 115,
        "Temperature": 3053,
        "AvgTimeToEmpty": 198,
        "AvgTimeToFull": 65535,
    }

    def test_discharging(self):
        v = battery.derive(self.RAW)
        self.assertEqual(v["state"], "discharging")
        self.assertEqual(v["percent"], 41.0)
        self.assertEqual(v["battery_watts"], -15.75)
        self.assertEqual(v["temp_c"], 30.5)
        self.assertEqual(v["health_pct"], 82.6)
        self.assertEqual(v["time_to_empty"], "3:18")
        self.assertIsNone(v["time_to_full"])   # 65535 sentinel
        self.assertIsNone(v["adapter"])
        self.assertTrue(battery.render(v))

    def test_unsigned_negative_amperage(self):
        raw = dict(self.RAW, Amperage=18446744073709548123)   # -3493 mA as u64
        self.assertEqual(battery.derive(raw)["amps"], -3.493)
        raw = dict(self.RAW, Amperage=2**32 - 2500)           # -2500 mA as u32
        self.assertEqual(battery.derive(raw)["amps"], -2.5)

    def test_charging_with_adapter(self):
        raw = dict(
            self.RAW,
            Amperage=2000, ExternalConnected=True, IsCharging=True,
            AvgTimeToFull=95, AvgTimeToEmpty=65535,
            AdapterDetails={
                "Watts": 96, "Name": "96W USB-C Power Adapter",
                "AdapterVoltage": 20000, "Current": 4800,
            },
        )
        v = battery.derive(raw)
        self.assertEqual(v["state"], "charging")
        self.assertEqual(v["adapter"]["rated_watts"], 96)
        self.assertEqual(v["time_to_full"], "1:35")
        # wattage embedded in the name must not be printed twice
        self.assertNotIn("96 W 96W", battery.render(v))


class MemoryTests(unittest.TestCase):
    RAW = {
        "vm_stat": (
            "Mach Virtual Memory Statistics: (page size of 16384 bytes)\n"
            "Pages free:                                6970.\n"
            "Pages active:                            308691.\n"
            "Pages wired down:                        141630.\n"
            "Pages occupied by compressor:            100000.\n"
        ),
        "memsize": "17179869184\n",
        "free_level": "61\n",
        "swapusage": "total = 4096.00M  used = 2831.75M  free = 1264.25M  (encrypted)\n",
    }

    def test_derive(self):
        v = memory.derive(self.RAW)
        self.assertEqual(v["total_gb"], 16.0)
        self.assertEqual(v["wired_gb"], 2.16)
        self.assertEqual(v["pressure"], "normal")
        self.assertEqual(v["swap_used_gb"], 2.77)
        self.assertTrue(memory.render(v))

    def test_pressure_levels(self):
        self.assertEqual(memory.derive(dict(self.RAW, free_level="30"))["pressure"], "warning")
        self.assertEqual(memory.derive(dict(self.RAW, free_level="10"))["pressure"], "critical")


class SystemTests(unittest.TestCase):
    RAW = {
        "cpu_brand": "Apple M1 Pro\n",
        "ncpu": "8\n",
        "loadavg": "{ 3.41 5.25 5.24 }\n",
        "boottime": "{ sec = 1782258268, usec = 0 } Mon Jun 23\n",
        "therm": "Note: No thermal warning level has been recorded\n",
        "now": 1782261868.0,   # boottime + 1 h
    }

    def test_derive(self):
        v = system.derive(self.RAW)
        self.assertEqual(v["cpu"], "Apple M1 Pro")
        self.assertEqual(v["load_1m"], 3.41)
        self.assertEqual(v["uptime_h"], 1.0)
        self.assertFalse(v["throttled"])
        self.assertTrue(system.render(v))

    def test_throttled(self):
        raw = dict(self.RAW, therm="CPU_Speed_Limit \t= 60\nCPU_Available_CPUs = 8\n")
        v = system.derive(raw)
        self.assertTrue(v["throttled"])
        self.assertEqual(v["cpu_speed_limit_pct"], 60)


if __name__ == "__main__":
    unittest.main()
