"""配对引擎单元测试，仅依赖标准库，用 ``python -I -m unittest`` 运行。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.domain.matching import LedgerError, match_ledgers  # noqa: E402

DAY = "2026-11-18"
DIE, MACHINE = "MJ-17", "IM-03"


def machine(serial, sample, hhmmss, die=DIE, machine_no=MACHINE, day=DAY):
    return {"serial": serial, "sample_id": sample, "measured_on": day, "die": die,
            "machine": machine_no, "ts": f"{day} {hhmmss}"}


def caliper(serial, sample, hhmmss, die=DIE, machine_no=MACHINE, day=DAY):
    return machine(serial, sample, hhmmss, die, machine_no, day)


class CardinalityAndCostTests(unittest.TestCase):
    def test_maximizes_pair_count_before_total_delta(self):
        # M2 在窗内只能配 C1（M2-C2 时差 8.5 分钟超窗）。最近邻贪心让 M1 先抢 C1，
        # M2 随即落空只成 1 件；最大匹配 M1-C2、M2-C1 可成 2 件，件数优先。
        machines = [machine("M1", "A1", "08:00:00"), machine("M2", "A2", "08:04:00")]
        calipers = [caliper("C1", "B1", "08:02:00"), caliper("C2", "B2", "07:55:30")]
        result = match_ledgers(machines, calipers)
        self.assertEqual(result["confident_count"], 2)
        self.assertEqual(result["pending_count"], 0)
        pairs = {(p["machine_serial"], p["caliper_serial"]) for p in result["confident_pairs"]}
        self.assertEqual(pairs, {("M1", "C2"), ("M2", "C1")})

    def test_minimizes_total_delta_among_maximum_matchings(self):
        # 两种完美配法都可行：直配总时差 10s，交叉配总时差 110s，应选直配。
        machines = [machine("M1", "A1", "08:00:00"), machine("M2", "A2", "08:01:00")]
        calipers = [caliper("C1", "B1", "08:00:10"), caliper("C2", "B2", "08:01:00")]
        result = match_ledgers(machines, calipers)
        self.assertEqual(result["confident_count"], 2)
        pairs = {(p["machine_serial"], p["caliper_serial"]) for p in result["confident_pairs"]}
        self.assertEqual(pairs, {("M1", "C1"), ("M2", "C2")})
        total = sum(p["delta_seconds"] for p in result["confident_pairs"])
        self.assertEqual(total, 10)

    def test_records_outside_window_go_to_pending(self):
        machines = [machine("M1", "A1", "08:00:00")]
        calipers = [caliper("C1", "B1", "08:06:00")]  # 恰好 6 分钟，超窗
        result = match_ledgers(machines, calipers)
        self.assertEqual(result["confident_count"], 0)
        self.assertEqual(result["pending_count"], 2)
        self.assertTrue(all(p["review_reason"] for p in result["pending_records"]))

    def test_boundary_five_minutes_is_eligible(self):
        machines = [machine("M1", "A1", "08:00:00")]
        calipers = [caliper("C1", "B1", "08:05:00")]  # 恰好 5 分钟，界内含
        result = match_ledgers(machines, calipers)
        self.assertEqual(result["confident_count"], 1)
        self.assertEqual(result["confident_pairs"][0]["delta_seconds"], 300)


class TieTests(unittest.TestCase):
    def test_symmetric_tie_marks_both_edges_ambiguous(self):
        # M1、M2 与 C1、C2 等距，两种完美配法同件数同总时差 → 全部歧义。
        machines = [machine("M1", "A1", "08:00:00"), machine("M2", "A2", "08:00:00")]
        calipers = [caliper("C1", "B1", "08:01:00"), caliper("C2", "B2", "08:01:00")]
        result = match_ledgers(machines, calipers)
        self.assertEqual(result["confident_count"], 0)
        self.assertEqual(result["review_pair_count"], 2)
        self.assertTrue(all(p["status"] == "ambiguous" for p in result["review_pairs"]))

    def test_partial_tie_keeps_only_common_edge_confident(self):
        # M3-C3 是唯一确定的边；M1/M2 与 C1/C2 等距产生歧义。
        machines = [machine("M1", "A1", "08:00:00"), machine("M2", "A2", "08:00:00"),
                    machine("M3", "A3", "08:20:00")]
        calipers = [caliper("C1", "B1", "08:01:00"), caliper("C2", "B2", "08:01:00"),
                    caliper("C3", "B3", "08:20:30")]
        result = match_ledgers(machines, calipers)
        self.assertEqual(result["confident_count"], 1)
        self.assertEqual(result["confident_pairs"][0]["machine_serial"], "M3")
        self.assertEqual(result["review_pair_count"], 2)

    def test_anchored_pair_is_never_ambiguous(self):
        # 样件号一致直接锚定，即使时间上存在并列候选也保持确定。
        machines = [machine("M1", "K-1", "08:00:00"), machine("M2", "A2", "08:00:00")]
        calipers = [caliper("C1", "K-1", "08:01:00"), caliper("C2", "B2", "08:01:00")]
        result = match_ledgers(machines, calipers)
        anchored = next(p for p in result["confident_pairs"] if p["match_kind"] == "anchored")
        self.assertEqual((anchored["machine_serial"], anchored["caliper_serial"]), ("M1", "C1"))

    def test_anchor_over_window_goes_to_review_not_confident(self):
        machines = [machine("M1", "K-1", "08:00:00")]
        calipers = [caliper("C1", "K-1", "08:09:00")]
        result = match_ledgers(machines, calipers)
        self.assertEqual(result["confident_count"], 0)
        self.assertEqual(result["review_pairs"][0]["status"], "anchor_over_window")


class GroupingTests(unittest.TestCase):
    def test_groups_are_isolated_by_date_die_machine(self):
        machines = [
            machine("M1", "A1", "08:00:00", die="MJ-17", machine_no="IM-03"),
            machine("M2", "A2", "08:00:00", die="MJ-22", machine_no="IM-07"),
        ]
        calipers = [
            caliper("C1", "B1", "08:01:00", die="MJ-17", machine_no="IM-03"),
            caliper("C2", "B2", "08:01:00", die="MJ-22", machine_no="IM-07"),
        ]
        result = match_ledgers(machines, calipers)
        self.assertEqual(result["group_count"], 2)
        self.assertEqual(result["confident_count"], 2)

    def test_same_time_other_machine_does_not_cross_pair(self):
        machines = [machine("M1", "A1", "08:00:00", machine_no="IM-03")]
        calipers = [caliper("C1", "B1", "08:00:01", machine_no="IM-07")]
        result = match_ledgers(machines, calipers)
        self.assertEqual(result["confident_count"], 0)
        self.assertEqual(result["pending_count"], 2)

    def test_records_without_counterpart_form_singleton_groups(self):
        machines = [machine("M1", "A1", "08:00:00")]
        result = match_ledgers(machines, [])
        self.assertEqual(result["group_count"], 1)
        self.assertEqual(result["pending_count"], 1)


class ValidationTests(unittest.TestCase):
    def test_duplicate_serial_rejected(self):
        machines = [machine("M1", "A1", "08:00:00"), machine("M1", "A2", "08:01:00")]
        calipers = [caliper("C1", "B1", "08:00:30")]
        with self.assertRaises(LedgerError):
            match_ledgers(machines, calipers)

    def test_timestamp_date_mismatch_rejected(self):
        machines = [machine("M1", "A1", "08:00:00", day="2026-11-19")]
        machines[0]["measured_on"] = DAY
        calipers = [caliper("C1", "B1", "08:00:30")]
        with self.assertRaises(LedgerError):
            match_ledgers(machines, calipers)

    def test_bad_window_rejected(self):
        machines = [machine("M1", "A1", "08:00:00")]
        calipers = [caliper("C1", "B1", "08:00:30")]
        with self.assertRaises(LedgerError):
            match_ledgers(machines, calipers, window_seconds=10)


class RerunTests(unittest.TestCase):
    def test_late_record_triggers_full_group_repair(self):
        # 先到两条机台、一条卡尺，组内只能成一对且 M2 待核对。
        machines = [machine("M1", "A1", "08:00:00"), machine("M2", "A2", "08:02:00")]
        calipers = [caliper("C1", "B1", "08:00:20")]
        first = match_ledgers(machines, calipers)
        self.assertEqual(first["confident_count"], 1)
        self.assertEqual(first["pending_count"], 1)
        # 迟到的卡尺补录后整组重配，两条都应配上。
        calipers.append(caliper("C2", "B2", "08:02:20"))
        second = match_ledgers(machines, calipers)
        self.assertEqual(second["confident_count"], 2)
        self.assertEqual(second["pending_count"], 0)

    def test_deterministic_across_calls(self):
        machines = [machine(f"M{i}", f"A{i}", f"08:{i:02d}:00") for i in range(4)]
        calipers = [caliper(f"C{i}", f"B{i}", f"08:{i:02d}:30") for i in range(4)]
        first = match_ledgers(machines, calipers)
        second = match_ledgers(machines, calipers)
        self.assertEqual(
            [(p["machine_serial"], p["caliper_serial"]) for p in first["confident_pairs"]],
            [(p["machine_serial"], p["caliper_serial"]) for p in second["confident_pairs"]],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
