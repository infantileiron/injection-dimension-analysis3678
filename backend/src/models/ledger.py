from datetime import datetime
from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from src.config.database import Base
from src.utils.time import now


class LedgerBatch(Base):
    """双台账批次：机台成型日志与卡尺量测记录的原始留档。

    每次补录生成一条新版本，原始记录以 JSON 不可变保存；配对在
    :class:`MatchSnapshot` 中留痕，因此已发分析可回查当时的配对。
    """

    __tablename__ = "ledger_batches"
    __table_args__ = (UniqueConstraint("name", "version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    version: Mapped[int] = mapped_column(default=1)
    parent_batch_id: Mapped[int | None] = mapped_column(ForeignKey("ledger_batches.id"))
    machine_filename: Mapped[str] = mapped_column(String(160))
    caliper_filename: Mapped[str] = mapped_column(String(160))
    machine_rows: Mapped[list] = mapped_column(JSON)
    caliper_rows: Mapped[list] = mapped_column(JSON)
    machine_count: Mapped[int]
    caliper_count: Mapped[int]
    window_seconds: Mapped[int] = mapped_column(default=300)
    checksum: Mapped[str] = mapped_column(String(64))
    author: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=now)


class MatchSnapshot(Base):
    """某次配对的不可变快照，承载入算配对、待核对记录与分组明细。"""

    __tablename__ = "match_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    ledger_batch_id: Mapped[int] = mapped_column(ForeignKey("ledger_batches.id"), index=True)
    version: Mapped[int]
    window_seconds: Mapped[int]
    result: Mapped[dict] = mapped_column(JSON)
    confident_count: Mapped[int]
    review_pair_count: Mapped[int]
    pending_count: Mapped[int]
    checksum: Mapped[str] = mapped_column(String(64))
    author: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=now)
