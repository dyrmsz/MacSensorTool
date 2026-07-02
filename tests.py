#!/usr/bin/env python3
"""
Unit tests for the pure derive()/render() functions, using mock raw data.
Runs on any OS: python3 tests.py
"""

import plistlib
import unittest

from macpower import history, viz
from macpower.sensors import battery, disk, memory, power, system


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
        "top": (
            "CPU usage: 12.00% user, 8.00% sys, 80.00% idle \n"
            "CPU usage: 15.00% user, 10.00% sys, 75.00% idle \n"
        ),
        "now": 1782261868.0,   # boottime + 1 h
    }

    def test_derive(self):
        v = system.derive(self.RAW)
        self.assertEqual(v["cpu"], "Apple M1 Pro")
        self.assertEqual(v["load_1m"], 3.41)
        self.assertEqual(v["uptime_h"], 1.0)
        self.assertEqual(v["cpu_usage_pct"], 25.0)  # 100 - 75% idle, second (live) sample
        self.assertFalse(v["throttled"])
        self.assertTrue(system.render(v))

    def test_throttled(self):
        raw = dict(self.RAW, therm="CPU_Speed_Limit \t= 60\nCPU_Available_CPUs = 8\n")
        v = system.derive(raw)
        self.assertTrue(v["throttled"])
        self.assertEqual(v["cpu_speed_limit_pct"], 60)

    def test_missing_top_output(self):
        v = system.derive(dict(self.RAW, top=""))
        self.assertIsNone(v["cpu_usage_pct"])
        self.assertTrue(system.render(v))


class DiskTests(unittest.TestCase):
    RAW = {
        "total": 500_000_000_000,
        "used": 285_000_000_000,
        "free": 215_000_000_000,
        "diskutil": "   SMART Status:              Verified\n",
        "iostat": (
            "              disk0 \n"
            "    KB/t  tps  MB/s \n"
            "   19.82   81  1.56 \n"
            "    4.00    6  0.02 \n"
        ),
    }

    def test_derive(self):
        v = disk.derive(self.RAW)
        self.assertEqual(v["percent_used"], 57.0)
        self.assertEqual(v["smart"], "Verified")
        self.assertTrue(v["healthy"])
        self.assertEqual(v["throughput_mbps"], 0.02)
        self.assertEqual(v["transfers_per_sec"], 6)
        self.assertTrue(disk.render(v))

    def test_failing_smart(self):
        v = disk.derive(dict(self.RAW, diskutil="   SMART Status:              Failing\n"))
        self.assertFalse(v["healthy"])

    def test_missing_iostat(self):
        v = disk.derive(dict(self.RAW, iostat=""))
        self.assertIsNone(v["throughput_mbps"])
        self.assertTrue(disk.render(v))


class PowerTests(unittest.TestCase):
    def _raw(self, data):
        return {"plist": plistlib.dumps(data)}

    def test_derive_authorized(self):
        raw = self._raw({
            "processor": {
                "cpu_die_temperature": 45.3,
                "gpu_die_temperature": 42.1,
                "cpu_power": 3821,       # mW
                "combined_power": 4823,  # mW
            },
            "fan_speed_rpm": 1800,
        })
        v = power.derive(raw)
        self.assertTrue(v["authorized"])
        self.assertEqual(v["cpu_temp_c"], 45.3)
        self.assertEqual(v["gpu_temp_c"], 42.1)
        self.assertEqual(v["fan_rpm"], 1800)
        self.assertEqual(v["cpu_watts"], 3.82)
        self.assertEqual(v["package_watts"], 4.82)
        self.assertTrue(power.render(v))

    def test_not_authorized(self):
        v = power.derive({"plist": None})
        self.assertFalse(v["authorized"])
        self.assertIn("passwordless sudo", power.render(v))

    def test_malformed_plist(self):
        v = power.derive({"plist": b"not a plist"})
        self.assertFalse(v["authorized"])


class VizTests(unittest.TestCase):
    def test_color_for_pct(self):
        self.assertEqual(viz.color_for_pct(80), "32")
        self.assertEqual(viz.color_for_pct(45), "33")
        self.assertEqual(viz.color_for_pct(10), "31")
        self.assertEqual(viz.color_for_pct(None), "0")
        self.assertEqual(viz.color_for_pct(80, invert=True), "31")
        self.assertEqual(viz.color_for_pct(10, invert=True), "32")

    def test_bar(self):
        self.assertEqual(viz.bar(50, width=20).count("█"), 10)
        self.assertEqual(viz.bar(0, width=20).count("█"), 0)
        self.assertEqual(viz.bar(100, width=20).count("█"), 20)
        self.assertEqual(viz.bar(None, width=10), "░" * 10)

    def test_colored_bar(self):
        self.assertIn("█", viz.colored_bar(50))

    def test_sparkline(self):
        s = viz.sparkline([1, 2, 3, 4, 5], width=40)
        self.assertEqual(len(s), 5)
        self.assertEqual(s[0], viz.SPARK_CHARS[0])
        self.assertEqual(s[-1], viz.SPARK_CHARS[-1])
        self.assertEqual(viz.sparkline([]), "")

    def test_donut(self):
        self.assertNotIn("█", "".join(viz.donut(0)))
        full = "".join(viz.donut(100))
        self.assertNotIn("░", full)
        self.assertIn("█", full)


class HistoryTests(unittest.TestCase):
    def test_window_stats(self):
        conn = history.connect(":memory:")
        now = 1_000_000.0
        for i in range(90, 0, -1):  # one sample/minute for the last 90 minutes
            history.record(conn, now - i * 60, "system", {"cpu_usage_pct": float(i)})

        stats = history.window_stats(conn, "system", "cpu_usage_pct", now=now)
        self.assertEqual(stats["10m"]["max"], 10.0)
        self.assertEqual(stats["10m"]["now"], 1.0)
        self.assertAlmostEqual(stats["10m"]["avg"], 5.5, places=2)
        self.assertEqual(stats["4h"]["max"], 90.0)

    def test_no_data(self):
        conn = history.connect(":memory:")
        stats = history.window_stats(conn, "system", "cpu_usage_pct", now=1_000_000.0)
        for label in ("10m", "30m", "1h", "2h", "4h"):
            self.assertIsNone(stats[label]["now"])

    def test_retention_prunes_old_rows(self):
        conn = history.connect(":memory:")
        now = 1_000_000.0
        history.record(conn, now - history.RETENTION_SECONDS - 10, "system", {"cpu_usage_pct": 1.0})
        history.record(conn, now, "system", {"cpu_usage_pct": 2.0})
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM readings").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
