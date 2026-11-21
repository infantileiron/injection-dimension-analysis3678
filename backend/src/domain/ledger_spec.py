"""双台账字段规格。

机台成型日志承载工艺设定（X 列），卡尺量测记录承载尺寸偏差（Y 列）。
两侧共享流水号、样件号、量测日、模具、机台与时间戳；样件号对不上时
由 :mod:`src.domain.matching` 按时间窗配对。
"""
from .spec import X_OPTIONS, Y_OPTIONS

COMMON_LEDGER_FIELDS = [
    {"key": "serial", "label": "流水号", "type": "string", "required": True, "max_length": 60},
    {"key": "sample_id", "label": "样件号", "type": "string", "required": True, "max_length": 60},
    {"key": "measured_on", "label": "量测日期", "type": "date", "required": True},
    {"key": "die", "label": "模具编号", "type": "string", "required": True, "max_length": 60},
    {"key": "machine", "label": "机台编号", "type": "string", "required": True, "max_length": 60},
    {"key": "resin_lot", "label": "树脂批次", "type": "string", "required": True, "max_length": 60},
    {"key": "ts", "label": "记录时间", "type": "timestamp", "required": True},
]

MACHINE_LEDGER_FIELDS = COMMON_LEDGER_FIELDS + [
    {"key": key, "label": label, "type": "number", "required": True, "min": spec_min, "max": spec_max}
    for key, label, spec_min, spec_max in (
        ("hold_pressure_mpa", "保压压力（MPa）", 0, 250),
        ("melt_temp_c", "熔体温度（℃）", 80, 450),
        ("cooling_seconds", "冷却时间（s）", 0.1, 600),
    )
]

CALIPER_LEDGER_FIELDS = COMMON_LEDGER_FIELDS + [
    {"key": key, "label": label, "type": "number", "required": True, "min": spec_min, "max": spec_max}
    for key, label, spec_min, spec_max in (
        ("width_deviation_mm", "卡扣外宽偏差（mm）", -5, 5),
        ("height_deviation_mm", "定位台阶高偏差（mm）", -5, 5),
    )
]

LEDGER_SPEC = {
    "window_seconds": 300,
    "window_seconds_min": 60,
    "window_seconds_max": 1800,
    "machine": MACHINE_LEDGER_FIELDS,
    "caliper": CALIPER_LEDGER_FIELDS,
    "x_options": list(X_OPTIONS),
    "y_options": list(Y_OPTIONS),
}
