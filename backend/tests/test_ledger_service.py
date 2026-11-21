"""服务层集成测试：用 SQLite 内存库验证建批、补录重配、快照与执行链路。"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
# 本地无预装 SQLAlchemy 时，允许通过隔离目录提供（CI/Docker 内无需此段）。
for _vendor in (Path("/tmp/pylibs"),):
    if _vendor.is_dir() and str(_vendor) not in sys.path:
        sys.path.append(str(_vendor))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-secret")
_ARTIFACT_DIR = tempfile.mkdtemp(prefix="artifacts-")
os.environ.setdefault("ARTIFACT_DIR", _ARTIFACT_DIR)

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

import src.config.database as database  # noqa: E402
engine = create_engine("sqlite:///:memory:", future=True)
database.engine = engine
database.Session = sessionmaker(engine, expire_on_commit=False, future=True)

from src.config.database import Base  # noqa: E402
from src.models import identity, jobs, ledger, source  # noqa: E402,F401
from src.services import ledger as ledger_service  # noqa: E402
from src.domain.snapshot_analysis import analyze_snapshot  # noqa: E402

DAY = "2026-11-18"
RESIN = "ABS-261118A"
PARAMS = {"process_variable": "保压压力（MPa）", "dimension_variable": "卡扣外宽偏差（mm）",
          "stratify_by": "模具 × 机台", "min_n": 3}


def machine(serial, sample, hhmmss, pressure):
    return {"serial": serial, "sample_id": sample, "measured_on": DAY, "die": "MJ-17",
            "machine": "IM-03", "resin_lot": RESIN, "ts": f"{DAY} {hhmmss}",
            "hold_pressure_mpa": float(pressure), "melt_temp_c": 230.0, "cooling_seconds": 16.0}


def caliper(serial, sample, hhmmss, width):
    return {"serial": serial, "sample_id": sample, "measured_on": DAY, "die": "MJ-17",
            "machine": "IM-03", "resin_lot": RESIN, "ts": f"{DAY} {hhmmss}",
            "width_deviation_mm": float(width), "height_deviation_mm": 0.0}


class LedgerServiceIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(engine)

    def test_create_supplement_snapshot_and_analyze(self):
        machines = [machine("M1", "A1", "08:00:00", 60), machine("M2", "A2", "08:02:00", 62),
                    machine("M3", "A3", "08:04:00", 64)]
        calipers = [caliper("C1", "B1", "08:00:20", -0.10), caliper("C2", "B2", "08:02:20", -0.02)]
        with database.Session.begin() as db:
            batch, snapshot, result = ledger_service.create_batch(
                db, "早班双台账-01", "m.csv", "c.csv", machines, calipers, 300, "analyst")
            batch_id, first_snapshot_id = batch.id, snapshot.id
        # 首版：M3 无卡尺候选，入算 2、待核对 1。
        self.assertEqual(result["confident_count"], 2)
        self.assertEqual(result["pending_count"], 1)
        self.assertTrue(snapshot.checksum)

        # 补录迟到卡尺，整组重配。
        late = [caliper("C3", "B3", "08:04:20", 0.05)]
        with database.Session.begin() as db:
            batch2, snapshot2, result2 = ledger_service.supplement_batch(
                db, batch_id, "", "c2.csv", [], late, 300, "analyst")
        self.assertEqual(batch2.version, 2)
        self.assertEqual(batch2.parent_batch_id, batch_id)
        self.assertEqual(result2["confident_count"], 3)
        self.assertEqual(result2["pending_count"], 0)
        self.assertNotEqual(snapshot2.id, first_snapshot_id)

        # 历史快照仍可回查且不被新版本覆盖。
        with database.Session() as db:
            old = db.get(ledger.MatchSnapshot, first_snapshot_id)
            self.assertEqual(old.result["confident_count"], 2)
            batch, latest = ledger_service.latest_snapshot(db, batch_id)
            self.assertEqual(latest.id, snapshot2.id)
            self.assertEqual(batch.machine_count, 3)
            self.assertEqual(batch.caliper_count, 3)

        # 基于最新快照执行分析，结果含入算/待核对表。
        analysis = analyze_snapshot(batch2.machine_rows, batch2.caliper_rows,
                                    snapshot2.result, PARAMS)
        self.assertEqual(analysis["tables"][0]["rows"][0]["n"], 3)
        titles = [t["title"] for t in analysis["tables"]]
        self.assertIn("本次入算配对（流水号溯源）", titles)

    def test_duplicate_batch_name_rejected(self):
        machines = [machine("D1", "A1", "09:00:00", 60)]
        calipers = [caliper("E1", "B1", "09:00:20", -0.05)]
        with database.Session.begin() as db:
            ledger_service.create_batch(db, "重名批次", "m.csv", "c.csv",
                                        machines, calipers, 300, "analyst")
        with self.assertRaises(ledger_service.LedgerError):
            with database.Session.begin() as db:
                ledger_service.create_batch(db, "重名批次", "m.csv", "c.csv",
                                            machines, calipers, 300, "analyst")


if __name__ == "__main__":
    unittest.main(verbosity=2)
