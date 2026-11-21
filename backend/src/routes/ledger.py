from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from src.config.database import connection
from src.constants.enums import Role
from src.controllers.auth import allow, current
from src.domain.ledger_join import build_snapshot
from src.domain.ledger_spec import LEDGER_SPEC
from src.domain.matching import LedgerError
from src.models.identity import User
from src.models.jobs import Run
from src.models.ledger import LedgerBatch, MatchSnapshot
from src.schemas.requests import (
    LedgerPreview, LedgerSupplement, LedgerUpload, SnapshotRunRequest,
)
from src.services.audit import record
from src.services import ledger as ledger_service
from src.services.datasets import ledger_sample, ledger_template
from src.services.validation import normalize_params, parse_ledger_side, parse_ledgers
from src.utils import ledger_views, views
from src.utils.wakeup import wake

router = APIRouter(prefix="/ledgers")


def _batch_or_404(db, batch_id):
    item = db.get(LedgerBatch, batch_id)
    if not item:
        raise HTTPException(404, "找不到该台账批次")
    return item


@router.get("/spec")
def spec(actor: User = Depends(current)):
    return LEDGER_SPEC


@router.get("/template/{side}")
def template(side: str, actor: User = Depends(current)):
    if side not in ("machine", "caliper"):
        raise HTTPException(404, "模板类型须为 machine 或 caliper。")
    filename = f"{'机台成型日志' if side == 'machine' else '卡尺量测记录'}-模板.csv"
    return Response(ledger_template(side), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"})


@router.get("/sample/{side}")
def sample(side: str, actor: User = Depends(current)):
    if side not in ("machine", "caliper"):
        raise HTTPException(404, "样例类型须为 machine 或 caliper。")
    filename = f"{'机台成型日志' if side == 'machine' else '卡尺量测记录'}-演示样例.csv"
    return Response(ledger_sample(side), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"})


@router.post("/preview", status_code=200)
def preview(body: LedgerPreview, actor: User = Depends(allow(Role.ADMIN, Role.ANALYST))):
    """不落库的配对预检，供上传前查看入算与待核对情况。"""
    machine_rows, caliper_rows = parse_ledgers(body.machine_csv, body.caliper_csv)
    result = build_snapshot(machine_rows, caliper_rows, body.window_seconds)
    return _summary(result)


@router.get("")
def index(db: Session = Depends(connection), actor: User = Depends(current)):
    out = []
    for item in ledger_service.list_batches(db):
        _, snap = ledger_service.latest_snapshot(db, item.id)
        out.append(ledger_views.ledger_batch(item, snap))
    return out


@router.post("", status_code=201)
def upload(body: LedgerUpload, db: Session = Depends(connection),
           actor: User = Depends(allow(Role.ADMIN, Role.ANALYST))):
    machine_rows, caliper_rows = parse_ledgers(body.machine_csv, body.caliper_csv)
    try:
        batch, snapshot, result = ledger_service.create_batch(
            db, body.name, body.machine_filename, body.caliper_filename,
            machine_rows, caliper_rows, body.window_seconds, actor.username,
        )
        record(db, actor.username, "ledger.imported", batch.id,
               snapshot_id=snapshot.id, confident=result["confident_count"])
        db.commit()
    except LedgerError as error:
        db.rollback()
        raise HTTPException(409, str(error)) from None
    return {**ledger_views.ledger_batch(batch, snapshot),
            "snapshot": ledger_views.snapshot(snapshot), "summary": _summary(result)}


@router.post("/{batch_id}/supplement", status_code=201)
def supplement(batch_id: int, body: LedgerSupplement, db: Session = Depends(connection),
               actor: User = Depends(allow(Role.ADMIN, Role.ANALYST))):
    _batch_or_404(db, batch_id)
    if not body.machine_csv and not body.caliper_csv:
        raise HTTPException(422, "请至少上传一本台账的补录记录。")
    machine_rows = parse_ledger_side(body.machine_csv, "machine") if body.machine_csv else []
    caliper_rows = parse_ledger_side(body.caliper_csv, "caliper") if body.caliper_csv else []
    try:
        batch, snapshot, result = ledger_service.supplement_batch(
            db, batch_id, body.machine_filename, body.caliper_filename,
            machine_rows, caliper_rows, body.window_seconds, actor.username,
        )
        record(db, actor.username, "ledger.supplemented", batch.id,
               version=batch.version, snapshot_id=snapshot.id,
               confident=result["confident_count"], pending=result["pending_count"])
        db.commit()
    except LedgerError as error:
        db.rollback()
        raise HTTPException(409, str(error)) from None
    return {**ledger_views.ledger_batch(batch, snapshot),
            "snapshot": ledger_views.snapshot(snapshot), "summary": _summary(result)}


@router.get("/{batch_id}")
def detail(batch_id: int, db: Session = Depends(connection), actor: User = Depends(current)):
    batch, snapshots = ledger_service.snapshots_for_batch(db, batch_id)
    if not batch:
        raise HTTPException(404, "找不到该台账批次")
    latest = snapshots[-1] if snapshots else None
    return {**ledger_views.ledger_batch(batch, latest),
            "versions": [ledger_views.snapshot(item) for item in snapshots]}


@router.get("/snapshots/{snapshot_id}")
def snapshot_detail(snapshot_id: int, db: Session = Depends(connection),
                    actor: User = Depends(current)):
    item = db.get(MatchSnapshot, snapshot_id)
    if not item:
        raise HTTPException(404, "找不到该配对快照")
    return ledger_views.snapshot(item)


@router.post("/snapshots/{snapshot_id}/runs", status_code=202)
def start_snapshot_run(snapshot_id: int, body: SnapshotRunRequest,
                       db: Session = Depends(connection),
                       actor: User = Depends(allow(Role.ADMIN, Role.ANALYST))):
    snapshot = db.get(MatchSnapshot, snapshot_id)
    if not snapshot:
        raise HTTPException(404, "找不到该配对快照")
    if body.snapshot_id != snapshot_id:
        raise HTTPException(422, "请求体与路径中的快照不一致。")
    item = Run(name=body.name, snapshot_id=snapshot_id,
               params=normalize_params(body.params), author=actor.username)
    db.add(item)
    db.flush()
    record(db, actor.username, "analysis.queued", item.id, snapshot_id=snapshot_id)
    db.commit()
    wake()
    return views.run(item, detail=True)


def _summary(result):
    return {
        "window_seconds": result["window_seconds"],
        "group_count": result["group_count"],
        "machine_total": result["machine_total"],
        "caliper_total": result["caliper_total"],
        "confident_count": result["confident_count"],
        "review_pair_count": result["review_pair_count"],
        "pending_count": result["pending_count"],
        "confident_pairs": result["confident_pairs"],
        "review_pairs": result["review_pairs"],
        "pending_records": result["pending_records"],
        "groups": result["groups"],
    }
