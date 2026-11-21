"""快照分析端到端测试：配对 → 拼联表 → 秩相关 → 入算/待核对表。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.domain.ledger_join import build_snapshot, join_confident_pairs  # noqa: E402
from src.domain.snapshot_analysis import analyze_snapshot  # noqa: E402

DAY = "2026-11-18"
RESIN = "ABS-261118A"


def machine(serial, sample, hhmmss, pressure, temp=230, cooling=16):
    return {"serial": serial, "sample_id": sample, "measured_on": DAY, "die": "MJ-17",
            "machine": "IM-03", "resin_lot": RESIN, "ts": f"{DAY} {hhmmss}",
            "hold_pressure_mpa": float(pressure), "melt_temp_c": float(temp),
            "cooling_seconds": float(cooling)}


def caliper(serial, sample, hhmmss, width, height=0.0):
    return {"serial": serial, "sample_id": sample, "measured_on": DAY, "die": "MJ-17",
            "machine": "IM-03", "resin_lot": RESIN, "ts": f"{DAY} {hhmmss}",
            "width_deviation_mm": float(width), "height_deviation_mm": float(height)}


PARAMS = {"process_variable": "保压压力（MPa）", "dimension_variable": "卡扣外宽偏差（mm）",
          "stratify_by": "模具 × 机台", "min_n": 3}


class SnapshotAnalysisTests(unittest.TestCase):
    def _ledgers(self):
        # 6 条机台、6 条卡尺；其中一组构造并列歧义，其余稳定配对。
        machines = [
            machine("LM1", "A1", "08:00:00", 60),
            machine("LM2", "A2", "08:02:00", 62),
            machine("LM3", "A3", "08:10:00", 64),
            machine("LM4", "A4", "08:12:00", 66),
            machine("LM5", "A5", "08:20:00", 68),
            machine("LM6", "A6", "08:30:00", 70),
        ]
        calipers = [
            caliper("LC1", "B1", "08:00:20", -0.10),
            caliper("LC2", "B2", "08:02:20", -0.06),
            caliper("LC3", "B3", "08:10:20", 0.02),
            caliper("LC4", "B4", "08:12:20", 0.05),
            caliper("LC5", "B5", "08:20:20", 0.09),
            caliper("LC6", "B6", "08:40:00", 0.12),  # 与 LM6 时差 10 分钟，超窗 → 待核对
        ]
        return machines, calipers

    def test_join_and_analyze_excludes_pending(self):
        machines, calipers = self._ledgers()
        snapshot = build_snapshot(machines, calipers)
        joined, provenance = join_confident_pairs(machines, calipers, snapshot)
        # LC6 超窗，LM6 也无窗内候选 → 入算 5 件，两侧各 1 条待核对。
        self.assertEqual(snapshot["confident_count"], 5)
        self.assertEqual(snapshot["pending_count"], 2)
        self.assertEqual(len(joined), 5)
        self.assertEqual(len(provenance), 5)
        # 两侧样件号本就不同（A* vs B*），时间窗配对生成 AUTO- 合成件号。
        self.assertTrue(all(sid.startswith("AUTO-LM") for sid in provenance))

        result = analyze_snapshot(machines, calipers, snapshot, PARAMS)
        titles = [table["title"] for table in result["tables"]]
        self.assertIn("本次入算配对（流水号溯源）", titles)
        self.assertIn("待核对记录（未配上）", titles)
        # 总体 n 等于入算配对数，而非原始台账条数。
        overall = result["tables"][0]["rows"][0]
        self.assertEqual(overall["n"], 5)
        self.assertEqual(result["snapshot"]["confident_count"], 5)

    def test_auto_sample_id_when_ids_disagree(self):
        machines = [machine("LM1", "A1", "08:00:00", 60)]
        calipers = [caliper("LC1", "B9", "08:00:30", -0.10)]
        snapshot = build_snapshot(machines, calipers)
        joined, provenance = join_confident_pairs(machines, calipers, snapshot)
        self.assertEqual(joined[0]["sample_id"], "AUTO-LM1")
        self.assertEqual(provenance["AUTO-LM1"]["caliper_sample_id"], "B9")

    def test_supplement_repairs_and_grows_confident_set(self):
        machines, calipers = self._ledgers()
        # 移除迟到的 LC6，先配对：LM6 待核对。
        early_calipers = calipers[:5]
        first = build_snapshot(machines, early_calipers)
        self.assertEqual(first["confident_count"], 5)
        # 补入一条在窗内的卡尺记录，整组重配后 LM6 配上。
        late = caliper("LC7", "B7", "08:30:20", 0.13)
        second = build_snapshot(machines, early_calipers + [late])
        self.assertEqual(second["confident_count"], 6)
        self.assertEqual(second["pending_count"], 0)

    def test_anchored_rows_carry_original_sample_id(self):
        machines = [machine("LM1", "K-1", "08:00:00", 60)]
        calipers = [caliper("LC1", "K-1", "08:00:20", -0.10)]
        snapshot = build_snapshot(machines, calipers)
        joined, _ = join_confident_pairs(machines, calipers, snapshot)
        self.assertEqual(joined[0]["sample_id"], "K-1")
        self.assertEqual(snapshot["confident_pairs"][0]["match_kind"], "anchored")


if __name__ == "__main__":
    unittest.main(verbosity=2)
