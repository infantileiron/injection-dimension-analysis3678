from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from src.constants.enums import Review

class Request(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')

class Credentials(Request):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)

class Upload(Request):
    name: str = Field(min_length=1, max_length=120)
    filename: str = Field(min_length=1, max_length=160)
    csv_text: str = Field(min_length=1, max_length=2_000_000)

class RunRequest(Request):
    dataset_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=120)
    params: dict = Field(default_factory=dict)

class ReviewRequest(Request):
    review: Review
    note: str = Field(min_length=1, max_length=500)
    decision: str = Field(default='', max_length=120)

class ScheduleRequest(RunRequest):
    recipient: str = Field(min_length=1, max_length=100)
    first_at: datetime
    repeat_daily: bool = False


class LedgerUpload(Request):
    name: str = Field(min_length=1, max_length=120)
    machine_filename: str = Field(min_length=1, max_length=160)
    caliper_filename: str = Field(min_length=1, max_length=160)
    machine_csv: str = Field(min_length=1, max_length=2_000_000)
    caliper_csv: str = Field(min_length=1, max_length=2_000_000)
    window_seconds: int = Field(default=300, ge=60, le=1800)


class LedgerSupplement(Request):
    machine_filename: str = Field(default="", max_length=160)
    caliper_filename: str = Field(default="", max_length=160)
    machine_csv: str = Field(default="", max_length=2_000_000)
    caliper_csv: str = Field(default="", max_length=2_000_000)
    window_seconds: int = Field(default=300, ge=60, le=1800)


class LedgerPreview(Request):
    machine_csv: str = Field(min_length=1, max_length=2_000_000)
    caliper_csv: str = Field(min_length=1, max_length=2_000_000)
    window_seconds: int = Field(default=300, ge=60, le=1800)


class SnapshotRunRequest(Request):
    snapshot_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=120)
    params: dict = Field(default_factory=dict)
