"""FastAPI 冒烟测试：验证应用装配、路由注册与台账接口行为（SQLite + Redis 桩）。"""
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

_DB_PATH = Path(tempfile.mkdtemp(prefix="smoke-db-")) / "smoke.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH}"
os.environ.setdefault("JWT_SECRET", "smoke-secret")
os.environ.setdefault("ARTIFACT_DIR", tempfile.mkdtemp(prefix="artifacts-"))
os.environ.setdefault("SEED_DEMO", "false")
os.environ.setdefault("REDIS_URL", "redis://localhost:6399/0")

# 在导入应用前用内存桩替换 redis，避免依赖真实 broker。
redis_stub = types.ModuleType("redis")


class _RedisError(Exception):
    pass


class _FakeRedis:
    @classmethod
    def from_url(cls, *args, **kwargs):
        return cls()

    def __init__(self, *args, **kwargs):
        self._items = {}

    def pipeline(self):
        outer = self

        class _Pipe:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
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

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
import src.config.database as database  # noqa: E402

# 保留应用 lifespan 实际使用的模块级 engine（指向同一内存库），并统一其 Session。
engine = database.engine
database.Session = sessionmaker(engine, expire_on_commit=False, future=True)

from fastapi.testclient import TestClient  # noqa: E402
from src.config.database import Base  # noqa: E402
from src.main import app  # noqa: E402
from src.models import identity, jobs, ledger, source  # noqa: E402,F401
from src.utils.security import hash_password, token  # noqa: E402
from src.models.identity import User  # noqa: E402
from src.config.database import Session  # noqa: E402

MACHINE_CSV = (
    "serial,sample_id,measured_on,die,machine,resin_lot,ts,"
    "hold_pressure_mpa,melt_temp_c,cooling_seconds\n"
    "LM1,A1,2026-11-18,MJ-17,IM-03,ABS-A,2026-11-18 08:00:00,64,230,16\n"
    "LM2,A2,2026-11-18,MJ-17,IM-03,ABS-A,2026-11-18 08:02:00,66,231,17\n"
)
CALIPER_CSV = (
    "serial,sample_id,measured_on,die,machine,resin_lot,ts,"
    "width_deviation_mm,height_deviation_mm\n"
    "LC1,B1,2026-11-18,MJ-17,IM-03,ABS-A,2026-11-18 08:00:20,-0.10,-0.02\n"
    "LC2,B2,2026-11-18,MJ-17,IM-03,ABS-A,2026-11-18 08:02:20,0.02,0.01\n"
)


class ApiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(engine)
        with Session.begin() as db:
            db.add(User(username="analyst", role="analyst",
                        password_hash=hash_password("analyst-demo-2611")))
        cls.client = TestClient(app)
        cls.headers = {"Authorization": f"Bearer {token('analyst', 'analyst')}"}

    def test_routes_registered(self):
        paths = {route.path for route in app.routes}
        for expected in ("/ledgers", "/ledgers/spec", "/ledgers/template/{side}",
                         "/ledgers/snapshots/{snapshot_id}/runs"):
            self.assertIn(expected, paths)

    def test_spec_requires_auth(self):
        self.assertEqual(self.client.get("/ledgers/spec").status_code, 401)

    def test_full_ledger_flow(self):
        resp = self.client.post("/ledgers", headers=self.headers, json={
            "name": "冒烟批次", "machine_filename": "m.csv", "caliper_filename": "c.csv",
            "machine_csv": MACHINE_CSV, "caliper_csv": CALIPER_CSV, "window_seconds": 300})
        self.assertEqual(resp.status_code, 201, resp.text)
        body = resp.json()
        self.assertEqual(body["confident_count"], 2)
        self.assertEqual(body["pending_count"], 0)
        batch_id = body["id"]
        snapshot_id = body["snapshot"]["id"]

        # 详情含两个历史版本入口（当前一版）。
        detail = self.client.get(f"/ledgers/{batch_id}", headers=self.headers).json()
        self.assertEqual(len(detail["versions"]), 1)

        # 基于快照发起复算。
        run = self.client.post(f"/ledgers/snapshots/{snapshot_id}/runs", headers=self.headers, json={
            "snapshot_id": snapshot_id, "name": "冒烟复算",
            "params": {"process_variable": "保压压力（MPa）",
                       "dimension_variable": "卡扣外宽偏差（mm）",
                       "stratify_by": "模具 × 机台", "min_n": 3}})
        self.assertEqual(run.status_code, 202, run.text)
        self.assertEqual(run.json()["snapshot_id"], snapshot_id)

        # 补录一本空增量之外的新卡尺，触发整组重配。
        extra = (
            "serial,sample_id,measured_on,die,machine,resin_lot,ts,"
            "width_deviation_mm,height_deviation_mm\n"
            "LC3,B3,2026-11-18,MJ-17,IM-03,ABS-A,2026-11-18 08:10:20,0.05,0.02\n"
        )
        sup = self.client.post(f"/ledgers/{batch_id}/supplement", headers=self.headers, json={
            "caliper_csv": extra, "caliper_filename": "c2.csv", "window_seconds": 300})
        self.assertEqual(sup.status_code, 201, sup.text)
        self.assertEqual(sup.json()["version"], 2)

        # 逻辑批次列表只显示最新版本。
        listing = self.client.get("/ledgers", headers=self.headers).json()
        mine = [item for item in listing if item["name"] == "冒烟批次"]
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0]["version"], 2)

    def test_template_download(self):
        resp = self.client.get("/ledgers/template/machine", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("hold_pressure_mpa", resp.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
