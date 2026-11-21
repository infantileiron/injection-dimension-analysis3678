import hashlib
import json

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from src.domain.ledger_join import build_snapshot
from src.domain.matching import LedgerError
from src.models.ledger import LedgerBatch, MatchSnapshot


def _checksum(payload):
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def _latest_batch(db, name):
    return db.scalar(select(LedgerBatch).where(LedgerBatch.name == name)
                     .order_by(LedgerBatch.version.desc()).limit(1))


def create_batch(db, name, machine_filename, caliper_filename,
                 machine_rows, caliper_rows, window_seconds, actor):
    """新建双台账批次并生成首版配对快照。"""
    if _latest_batch(db, name):
        raise LedgerError(f"批次名称「{name}」已存在，请改用补录或更换名称。")
    return _persist(db, name, 1, None, machine_filename, caliper_filename,
                    machine_rows, caliper_rows, window_seconds, actor)


def supplement_batch(db, batch_id, machine_filename, caliper_filename,
                     machine_rows, caliper_rows, window_seconds, actor):
    """同批补录：合并两侧记录后整组重配，生成新版本与新快照。

    迟到记录按流水号去重合并（新记录覆盖同流水号的旧值），随后对完整
    台账重跑配对，因此不会漏掉补入的记录。
    """
    parent = db.get(LedgerBatch, batch_id)
    if not parent:
        raise LedgerError("找不到要补录的台账批次。")
    # 始终基于逻辑批次的最新版本行递增，避免从历史版本补录造成版本号冲突。
    latest = db.scalar(select(LedgerBatch).where(LedgerBatch.name == parent.name)
                       .order_by(LedgerBatch.version.desc()).limit(1))
    merged_machine = _merge_rows(latest.machine_rows, machine_rows)
    merged_caliper = _merge_rows(latest.caliper_rows, caliper_rows)
    return _persist(db, latest.name, latest.version + 1, latest.id,
                    machine_filename or latest.machine_filename,
                    caliper_filename or latest.caliper_filename,
                    merged_machine, merged_caliper, window_seconds, actor)


def _merge_rows(existing, incoming):
    merged = {row["serial"]: row for row in existing}
    for row in incoming:
        merged[row["serial"]] = row
    return list(merged.values())


def _persist(db, name, version, parent_id, machine_filename, caliper_filename,
             machine_rows, caliper_rows, window_seconds, actor):
    signature = _checksum([machine_rows, caliper_rows, window_seconds])
    batch = LedgerBatch(
        name=name, version=version, parent_batch_id=parent_id,
        machine_filename=machine_filename, caliper_filename=caliper_filename,
        machine_rows=machine_rows, caliper_rows=caliper_rows,
        machine_count=len(machine_rows), caliper_count=len(caliper_rows),
        window_seconds=window_seconds, checksum=signature, author=actor,
    )
    try:
        with db.begin_nested():
            db.add(batch)
            db.flush()
    except IntegrityError:
        raise LedgerError("该批次内容已存在，请勿重复导入。") from None

    result = build_snapshot(machine_rows, caliper_rows, window_seconds)
    snapshot = MatchSnapshot(
        ledger_batch_id=batch.id, version=version, window_seconds=window_seconds,
        result=result, confident_count=result["confident_count"],
        review_pair_count=result["review_pair_count"], pending_count=result["pending_count"],
        checksum=_checksum(result), author=actor,
    )
    db.add(snapshot)
    db.flush()
    return batch, snapshot, result


def list_batches(db):
    """每个逻辑批次（同名版本链）只返回最新版本行。"""
    latest_version = (
        select(LedgerBatch.name, func.max(LedgerBatch.version).label("max_version"))
        .group_by(LedgerBatch.name).subquery()
    )
    return db.scalars(
        select(LedgerBatch).join(
            latest_version,
            (LedgerBatch.name == latest_version.c.name)
            & (LedgerBatch.version == latest_version.c.max_version),
        ).order_by(LedgerBatch.id.desc()).limit(100)
    ).all()


def _version_chain_ids(db, batch):
    """同一逻辑批次（同名）的全部版本行主键。"""
    return list(db.scalars(
        select(LedgerBatch.id).where(LedgerBatch.name == batch.name)
    ))


def latest_snapshot(db, batch_id):
    """跨同名版本链取最新版本行及其最新配对快照。"""
    anchor = db.get(LedgerBatch, batch_id)
    if not anchor:
        return None, None
    batch = db.scalar(select(LedgerBatch).where(LedgerBatch.name == anchor.name)
                      .order_by(LedgerBatch.version.desc()).limit(1))
    ids = _version_chain_ids(db, batch)
    snapshot = db.scalar(
        select(MatchSnapshot).where(MatchSnapshot.ledger_batch_id.in_(ids))
        .order_by(MatchSnapshot.version.desc(), MatchSnapshot.id.desc()).limit(1)
    )
    return batch, snapshot


def snapshots_for_batch(db, batch_id):
    """返回逻辑批次的全部历史快照（按版本升序），供逐版回查。"""
    batch = db.get(LedgerBatch, batch_id)
    if not batch:
        return None, []
    ids = _version_chain_ids(db, batch)
    snapshots = db.scalars(
        select(MatchSnapshot).where(MatchSnapshot.ledger_batch_id.in_(ids))
        .order_by(MatchSnapshot.version.asc(), MatchSnapshot.id.asc())
    ).all()
    return batch, snapshots
