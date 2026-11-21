"""Worker 执行链路测试：快照任务从领单到产出结果与导出。"""
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
for _vendor in (Path("/tmp/pylibs"),):
    if _vendor.is_dir() and str(_vendor) not in sys.path:
        sys.path.append(str(_vendor))

_DB_PATH = Path(tempfile.mkdtemp(prefix="worker-db-")) / "worker.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH}"
os.environ.setdefault("JWT_SECRET", "worker-secret")
os.environ["ARTIFACT_DIR"] = tempfile.mkdtemp(prefix="worker-artifacts-")
os.environ.setdefault("SEED_DEMO", "false")
os.environ.setdefault("REDIS_URL", "redis://localhost:6399/0")

redis_stub = types.ModuleType("redis")


class _RedisError(Exception):
    pass


class _FakeRedis:
    @classmethod
    def from_url(cls, *a, **k):
        return cls()

    def pipeline(self):
        class _Pipe:
            def __enter__(self):
                return self

            def __exit__(self, *e):
                return False

            def lpush(self, *a):
                return self

            def ltrim(self, *a):
                return self

            def execute(self):
                return []

        return _Pipe()

    def ping(self):
        return True

    def brpop(self, *a, **k):
        return None

    def eval(self, *a, **k):
        return 1


redis_stub.Redis = _FakeRedis
redis_stub.RedisError = _RedisError
sys.modules["redis"] = redis_stub

from sqlalchemy.orm import sessionmaker  # noqa: E402
import src.config.database as database  # noqa: E402

database.Session = sessionmaker(database.engine, expire_on_commit=False, future=True)

from src.config.database import Base  # noqa: E402
from src.models import identity, jobs, ledger, source  # noqa: E402,F401
from src.services import ledger as ledger_service  # noqa: E402
from src.services.execution import claim, execute  # noqa: E402
from src.models.jobs import Run  # noqa: E402
from src.constants.enums import Status  # noqa: E402

DAY = "2026-11-18"
PARAMS = {"process_variable": "保压压力（MPa）", "dimension_variable": "卡扣外宽偏差（mm）",
          "stratify_by": "模具 × 机台", "min_n": 3}


def machine(serial, sample, hhmmss, pressure):
    return {"serial": serial, "sample_id": sample, "measured_on": DAY, "die": "MJ-17",
            "machine": "IM-03", "resin_lot": "ABS-A", "ts": f"{DAY} {hhmmss}",
            "hold_pressure_mpa": float(pressure), "melt_temp_c": 230.0, "cooling_seconds": 16.0}


def caliper(serial, sample, hhmmss, width):
    return {"serial": serial, "sample_id": sample, "measured_on": DAY, "die": "MJ-17",
            "machine": "IM-03", "resin_lot": "ABS-A", "ts": f"{DAY} {hhmmss}",
            "width_deviation_mm": float(width), "height_deviation_mm": 0.0}


class WorkerExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(database.engine)

    def test_claim_and_execute_snapshot_run(self):
        machines = [machine("M1", "A1", "08:00:00", 60), machine("M2", "A2", "08:02:00", 62),
                    machine("M3", "A3", "08:04:00", 64)]
        calipers = [caliper("C1", "B1", "08:00:20", -0.10), caliper("C2", "B2", "08:02:20", -0.02),
                    caliper("C3", "B3", "08:04:20", 0.05)]
        with database.Session.begin() as db:
            batch, snapshot, _ = ledger_service.create_batch(
                db, "worker批次", "m.csv", "c.csv", machines, calipers, 300, "analyst")
            run = Run(name="worker复算", snapshot_id=snapshot.id, params=PARAMS, author="analyst")
            db.add(run)
            db.flush()
            run_id = run.id

        lease = claim()
        self.assertIsNotNone(lease)
        self.assertEqual(lease[0], run_id)
        self.assertTrue(lease[4])  # from_snapshot 标记
        execute(lease)

        with database.Session() as db:
            done = db.get(Run, run_id)
            self.assertEqual(done.status, Status.COMPLETE)
            self.assertIsNone(done.error)
            self.assertTrue(done.export_file)
            titles = [table["title"] for table in done.result["tables"]]
            self.assertIn("本次入算配对（流水号溯源）", titles)
            self.assertIn("待核对记录（未配上）", titles)
            self.assertEqual(done.result["snapshot"]["confident_count"], 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
