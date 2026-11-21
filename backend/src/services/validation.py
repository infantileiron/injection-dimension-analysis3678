import csv
import io
import math
from datetime import date
from src.domain import analysis
from src.domain.ledger_spec import CALIPER_LEDGER_FIELDS, MACHINE_LEDGER_FIELDS
from src.domain.matching import parse_timestamp
from src.domain.spec import SPEC


def cell(field, raw):
    label, kind = field['label'], field['type']
    value = raw.strip() if isinstance(raw, str) else raw
    if value is None or value == '':
        if field.get('required', True):
            raise ValueError(f'{label}不能为空')
        return None
    try:
        if kind == 'int':
            if isinstance(value, bool) or (isinstance(value, float) and not value.is_integer()):
                raise ValueError
            value = int(value)
        elif kind == 'number':
            if isinstance(value, bool):
                raise ValueError
            value = float(value)
            if not math.isfinite(value):
                raise ValueError
        elif kind == 'date':
            value = date.fromisoformat(str(value)).isoformat()
        elif kind == 'timestamp':
            value = parse_timestamp(str(value)).isoformat(sep=' ')
        elif kind == 'bool':
            values = {'true': True, 'false': False, '1': True, '0': False, '是': True, '否': False}
            value = values[str(value).lower()]
        elif kind in {'select', 'string'}:
            if not isinstance(value, str) or len(value) > field.get('max_length', 300):
                raise ValueError
            if kind == 'select' and value not in field['options']:
                raise ValueError
    except (TypeError, ValueError, KeyError, OverflowError):
        raise ValueError(f'{label}格式不正确，请检查字段说明') from None
    if kind in {'int', 'number'}:
        if 'min' in field and value < field['min']:
            raise ValueError(f'{label}最小为 {field["min"]}')
        if 'max' in field and value > field['max']:
            raise ValueError(f'{label}最大为 {field["max"]}')
    return value


def parse_rows(text):
    reader = csv.DictReader(io.StringIO(text.removeprefix('\ufeff'), newline=''), strict=True)
    fields = SPEC['fields']
    keys = {field['key'] for field in fields}
    required = {field['key'] for field in fields if field.get('required', True)}
    rows = []
    try:
        headers = reader.fieldnames or []
        if not required <= set(headers) or not set(headers) <= keys or len(headers) != len(set(headers)):
            raise ValueError('CSV 表头与字段说明不符，请下载模板检查列名')
        for raw in reader:
            if len(rows) >= 5000:
                raise ValueError('一个数据批次最多导入 5000 行')
            try:
                if None in raw or any(value is None for value in raw.values()):
                    raise ValueError('工作表的列数与表头不一致')
                rows.append({field['key']: cell(field, raw.get(field['key'])) for field in fields})
            except ValueError as error:
                raise ValueError(f'CSV 第 {reader.line_num} 行 · {error}') from None
    except csv.Error:
        raise ValueError(f'CSV 第 {reader.line_num} 行附近格式不正确') from None
    if not rows:
        raise ValueError('CSV 至少需要一行有效数据')
    if hasattr(analysis, 'validate_rows'):
        analysis.validate_rows(rows)
    return rows


def normalize_params(params):
    fields = SPEC['params']
    if set(params) - {field['key'] for field in fields}:
        raise ValueError('存在未知运行参数，请重新打开工作面板')
    return {field['key']: cell(field, params.get(field['key'], field['default'])) for field in fields}


def _parse_ledger_side(text, fields, side_label):
    reader = csv.DictReader(io.StringIO(text.removeprefix('﻿'), newline=''), strict=True)
    keys = {field['key'] for field in fields}
    required = {field['key'] for field in fields if field.get('required', True)}
    rows = []
    try:
        headers = reader.fieldnames or []
        if not required <= set(headers) or not set(headers) <= keys or len(headers) != len(set(headers)):
            raise ValueError(f'{side_label}CSV 表头与字段说明不符，请下载台账模板检查列名')
        for raw in reader:
            if len(rows) >= 5000:
                raise ValueError('单本台账最多导入 5000 行')
            if None in raw or any(value is None for value in raw.values()):
                raise ValueError('工作表的列数与表头不一致')
            try:
                rows.append({field['key']: cell(field, raw.get(field['key'])) for field in fields})
            except ValueError as error:
                raise ValueError(f'{side_label}CSV 第 {reader.line_num} 行 · {error}') from None
    except csv.Error:
        raise ValueError(f'{side_label}CSV 第 {reader.line_num} 行附近格式不正确') from None
    if not rows:
        raise ValueError(f'{side_label}CSV 至少需要一行有效数据')
    return rows


def parse_ledger_side(text, side):
    """解析单本台账，side 取 'machine' 或 'caliper'。"""
    if side == 'machine':
        return _parse_ledger_side(text, MACHINE_LEDGER_FIELDS, '机台日志')
    return _parse_ledger_side(text, CALIPER_LEDGER_FIELDS, '卡尺记录')


def parse_ledgers(machine_text, caliper_text):
    """解析机台日志与卡尺记录两本台账，返回规范化后的两侧记录。"""
    machine_rows = parse_ledger_side(machine_text, 'machine')
    caliper_rows = parse_ledger_side(caliper_text, 'caliper')
    return machine_rows, caliper_rows
