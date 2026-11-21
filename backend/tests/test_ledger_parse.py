"""台账 CSV 解析测试，仅依赖标准库。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.services.validation import parse_ledger_side, parse_ledgers  # noqa: E402

MACHINE_HEADER = ("serial,sample_id,measured_on,die,machine,resin_lot,ts,"
                  "hold_pressure_mpa,melt_temp_c,cooling_seconds")
MACHINE_KEYS = ["serial", "sample_id", "measured_on", "die", "machine", "resin_lot", "ts",
                "hold_pressure_mpa", "melt_temp_c", "cooling_seconds"]
CALIPER_HEADER = ("serial,sample_id,measured_on,die,machine,resin_lot,ts,"
                  "width_deviation_mm,height_deviation_mm")


def machine_csv():
    return "\n".join([
        MACHINE_HEADER,
        "LM1,A1,2026-11-18,MJ-17,IM-03,ABS-261118A,2026-11-18 08:00:00,64,230,16.5",
        "LM2,A2,2026-11-18,MJ-17,IM-03,ABS-261118B,2026-11-18 08:02:00,66,231,17.0",
    ])


def caliper_csv():
    return "\n".join([
        CALIPER_HEADER,
        "LC1,B1,2026-11-18,MJ-17,IM-03,ABS-261118A,2026-11-18 08:00:20,-0.10,-0.02",
        "LC2,B2,2026-11-18,MJ-17,IM-03,ABS-261118B,2026-11-18 08:02:20,0.02,0.01",
    ])


class LedgerParseTests(unittest.TestCase):
    def test_parse_machine_side_types(self):
        rows = parse_ledger_side(machine_csv(), "machine")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["serial"], "LM1")
        self.assertEqual(rows[0]["ts"], "2026-11-18 08:00:00")
        self.assertEqual(rows[0]["hold_pressure_mpa"], 64.0)
        self.assertEqual(rows[0]["cooling_seconds"], 16.5)
        self.assertEqual(set(rows[0]), set(MACHINE_KEYS))

    def test_parse_both_sides(self):
        machines, calipers = parse_ledgers(machine_csv(), caliper_csv())
        self.assertEqual(len(machines), 2)
        self.assertEqual(len(calipers), 2)
        self.assertEqual(calipers[1]["width_deviation_mm"], 0.02)

    def test_bad_timestamp_rejected(self):
        text = machine_csv().replace("2026-11-18 08:00:00", "18-11-2026 08:00")
        with self.assertRaises(ValueError):
            parse_ledger_side(text, "machine")

    def test_out_of_range_value_rejected(self):
        text = machine_csv().replace(",64,", ",999,")
        with self.assertRaises(ValueError):
            parse_ledger_side(text, "machine")

    def test_header_mismatch_rejected(self):
        text = machine_csv().replace("serial", "record_id")
        with self.assertRaises(ValueError):
            parse_ledger_side(text, "machine")


if __name__ == "__main__":
    unittest.main(verbosity=2)
