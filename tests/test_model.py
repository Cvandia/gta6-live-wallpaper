import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from model import DEFAULT_TARGET, START, parse_target, snapshot, format_target


class CountdownTest(unittest.TestCase):
    def test_chinese_date_label_under_c_locale(self):
        import locale
        previous=locale.setlocale(locale.LC_TIME)
        try:
            locale.setlocale(locale.LC_TIME,"C")
            self.assertEqual(format_target(parse_target(DEFAULT_TARGET)),"2026年11月19日 — 00:00 GMT+8")
        finally:
            locale.setlocale(locale.LC_TIME,previous)

    def test_store_utc_is_beijing_midnight(self):
        self.assertEqual(parse_target(DEFAULT_TARGET), datetime(2026,11,18,16,tzinfo=timezone.utc))

    def test_independent_of_local_time_zone(self):
        target = parse_target(DEFAULT_TARGET)
        local = datetime.fromisoformat("2026-10-15T21:51:00+08:00")
        utc = datetime.fromisoformat("2026-10-15T13:51:00Z")
        a, b = snapshot(local, target), snapshot(utc, target)
        self.assertEqual(a, b)
        self.assertEqual([a[k] for k in ("days","hours","minutes","seconds")], [34,2,9,0])

    def test_last_fractional_second_and_zero(self):
        target = parse_target(DEFAULT_TARGET)
        self.assertEqual(snapshot(datetime.fromisoformat("2026-11-18T23:59:59.9+08:00"), target)["seconds"], 1)
        state = snapshot(target, target)
        self.assertTrue(state["released"])
        self.assertEqual(state["progress"], 1)
        self.assertEqual([state[k] for k in ("days","hours","minutes","seconds")], [0,0,0,0])

    def test_progress_clamp_after_and_before(self):
        self.assertEqual(snapshot(datetime.fromisoformat("2020-01-01T00:00:00Z"), parse_target(DEFAULT_TARGET))["progress"], 0)
        self.assertEqual(snapshot(datetime.fromisoformat("2030-01-01T00:00:00Z"), parse_target(DEFAULT_TARGET))["progress"], 1)

    def test_no_implicit_system_timezone(self):
        with self.assertRaises(ValueError):
            parse_target("2026-11-19T00:00:00")
        with self.assertRaises(ValueError):
            snapshot(datetime.now(), parse_target(DEFAULT_TARGET))


if __name__ == "__main__":
    unittest.main()
