import csv
import hashlib
import io
import json
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from src.domain.demo import demo_rows
from src.domain.ledger_spec import CALIPER_LEDGER_FIELDS, MACHINE_LEDGER_FIELDS
from src.domain.spec import SPEC
from src.models.source import Dataset


def checksum(rows):
    raw = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def save(db, name, filename, rows, actor):
    signature = checksum(rows)
    lookup = select(Dataset).where(Dataset.name == name, Dataset.checksum == signature)
    existing = db.scalar(lookup)
    if existing:
        return existing, False
    dataset = Dataset(name=name, filename=filename, checksum=signature, rows=rows,
                      row_count=len(rows), author=actor)
    try:
        with db.begin_nested():
            db.add(dataset)
            db.flush()
    except IntegrityError:
        existing = db.scalar(lookup.with_for_update())
        if existing:
            return existing, False
        raise
    return dataset, True


def template():
    fields = [field['key'] for field in SPEC['fields']]
    buffer = io.StringIO(newline='')
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction='ignore')
    writer.writeheader()
    # The complete representative dataset also works as a reproducible import fixture.
    writer.writerows(demo_rows())
    return '\ufeff' + buffer.getvalue()


def ledger_template(side):
    """\u751f\u6210\u673a\u53f0\u65e5\u5fd7\u6216\u5361\u5c3a\u8bb0\u5f55\u7684\u7a7a\u6a21\u677f\uff08\u4ec5\u8868\u5934\uff0c\u82f1\u6587 key\uff09\u3002"""
    fields = MACHINE_LEDGER_FIELDS if side == 'machine' else CALIPER_LEDGER_FIELDS
    header = [field['key'] for field in fields]
    buffer = io.StringIO(newline='')
    writer = csv.writer(buffer)
    writer.writerow(header)
    return '\ufeff' + buffer.getvalue()


def ledger_sample(side):
    """\u751f\u6210\u5e26\u6f14\u793a\u6570\u636e\u7684\u53f0\u8d26 CSV\uff0c\u542b\u6837\u4ef6\u53f7\u5bf9\u4e0d\u4e0a\u4e0e\u8d85\u7a97\u8fdf\u5230\u8bb0\u5f55\u3002"""
    from src.domain.demo_ledger import demo_ledgers
    machine_rows, caliper_rows = demo_ledgers()
    rows = machine_rows if side == 'machine' else caliper_rows
    fields = MACHINE_LEDGER_FIELDS if side == 'machine' else CALIPER_LEDGER_FIELDS
    header = [field['key'] for field in fields]
    buffer = io.StringIO(newline='')
    writer = csv.DictWriter(buffer, fieldnames=header, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(rows)
    return '\ufeff' + buffer.getvalue()
