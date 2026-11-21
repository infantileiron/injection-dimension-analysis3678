"""双台账演示数据：从同一组样件拆出机台日志与卡尺记录，故意打乱部分
样件号并加入迟到/超窗记录，用于演示五分钟窗配对与待核对。"""
from datetime import datetime, timedelta

_BASE = datetime(2026, 11, 18, 8, 0, 0)


def _stamp(minutes, seconds=0):
    return (_BASE + timedelta(minutes=minutes, seconds=seconds)).strftime("%Y-%m-%d %H:%M:%S")


def demo_ledgers():
    """返回 (machine_rows, caliper_rows)，时间均在同一日期、同模具机台分组内。"""
    # (机台流水号, 卡尺流水号, 分钟偏移, 保压, 熔温, 冷却, 外宽偏差, 台阶高偏差, 树脂批次)
    samples = [
        ("LM-01", "LC-01", 0, 60, 228, 15.0, -0.10, -0.03, "ABS-261118A"),
        ("LM-02", "LC-02", 2, 62, 229, 15.5, -0.06, -0.02, "ABS-261118A"),
        ("LM-03", "LC-03", 4, 64, 230, 16.0, 0.01, -0.01, "ABS-261118B"),
        ("LM-04", "LC-04", 6, 66, 231, 16.5, 0.04, 0.01, "ABS-261118B"),
        ("LM-05", "LC-05", 8, 68, 232, 17.0, 0.08, 0.02, "ABS-261118A"),
    ]
    machine_rows, caliper_rows = [], []
    for index, (ms, cs, minute, pressure, melt, cooling, width, height, lot) in enumerate(samples):
        day = "2026-11-18"
        # 机台账样件号用 K 系列；卡尺台账前两件故意改成对不上的编号。
        machine_sample = f"K261118-03-{index + 1:02d}"
        caliper_sample = machine_sample if index >= 2 else f"Q261118-03-{index + 1:02d}"
        machine_rows.append({
            "serial": ms, "sample_id": machine_sample, "measured_on": day,
            "die": "MJ-17", "machine": "IM-03", "resin_lot": lot, "ts": _stamp(minute),
            "hold_pressure_mpa": float(pressure), "melt_temp_c": float(melt),
            "cooling_seconds": float(cooling),
        })
        # 卡尺比机台晚 20 秒，仍在五分钟窗内。
        caliper_rows.append({
            "serial": cs, "sample_id": caliper_sample, "measured_on": day,
            "die": "MJ-17", "machine": "IM-03", "resin_lot": lot,
            "ts": _stamp(minute, 20),
            "width_deviation_mm": float(width), "height_deviation_mm": float(height),
        })
    # 一条迟到且超窗的卡尺：与任何机台记录都超过五分钟，转待核对。
    caliper_rows.append({
        "serial": "LC-99", "sample_id": "K261118-03-99", "measured_on": "2026-11-18",
        "die": "MJ-17", "machine": "IM-03", "resin_lot": "ABS-261118A",
        "ts": _stamp(40), "width_deviation_mm": 0.12, "height_deviation_mm": 0.03,
    })

    # 另一副模具/机台：两条机台与两条卡尺完全等距，两种完美配法同件数同总时差，
    # 触发并列最优 → 这些配对不被所有最优解共有，整组转待核对，不入算相关。
    tie_minute = 30
    for offset, (ms, cs) in enumerate((("LM-21", "LC-21"), ("LM-22", "LC-22"))):
        machine_rows.append({
            "serial": ms, "sample_id": f"K261118-07-{offset + 1:02d}", "measured_on": "2026-11-18",
            "die": "MJ-22", "machine": "IM-07", "resin_lot": "ABS-261118B",
            "ts": _stamp(tie_minute), "hold_pressure_mpa": 53.0, "melt_temp_c": 233.0,
            "cooling_seconds": 17.0,
        })
        caliper_rows.append({
            "serial": cs, "sample_id": f"Q261118-07-{offset + 1:02d}", "measured_on": "2026-11-18",
            "die": "MJ-22", "machine": "IM-07", "resin_lot": "ABS-261118B",
            "ts": _stamp(tie_minute, 20), "width_deviation_mm": 0.02 + 0.01 * offset,
            "height_deviation_mm": 0.01,
        })
    return machine_rows, caliper_rows
