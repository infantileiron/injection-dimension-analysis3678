"""把配对快照中的稳定配对转换为秩相关分析可用的联表行。

只有 ``confident``（锚定或所有最优解共有的时间窗配对）才入算相关；
歧义与待核对记录不参与，仅在结果页列出供人工核对。
"""
from .matching import match_ledgers

# 联表行需要的全部字段（与 SPEC fields 的 key 对齐）。
JOIN_FIELDS = (
    "sample_id", "measured_on", "die", "machine", "resin_lot",
    "hold_pressure_mpa", "melt_temp_c", "cooling_seconds",
    "width_deviation_mm", "height_deviation_mm",
)
_MACHINE_X = ("hold_pressure_mpa", "melt_temp_c", "cooling_seconds")
_CALIPER_Y = ("width_deviation_mm", "height_deviation_mm")


def _row_lookup(rows):
    return {row["serial"]: row for row in rows}


def join_confident_pairs(machine_rows, caliper_rows, snapshot_result):
    """依据快照的稳定配对，拼装分析联表行与溯源映射。

    样件号对不上的时间窗配对会生成可追溯的合成样件号（保留机台流水号），
    并在 ``provenance`` 中同时记录两侧流水号、原始样件号与时差。
    """
    machines = _row_lookup(machine_rows)
    calipers = _row_lookup(caliper_rows)
    joined, provenance = [], {}
    for pair in snapshot_result["confident_pairs"]:
        machine = machines[pair["machine_serial"]]
        caliper = calipers[pair["caliper_serial"]]
        sample_id = machine["sample_id"]
        if machine["sample_id"] != caliper["sample_id"]:
            # 样件号不一致：以机台流水号生成确定的合成件号，避免与真实件号冲突。
            sample_id = f"AUTO-{machine['serial']}"
        row = {
            "sample_id": sample_id,
            "measured_on": machine["measured_on"],
            "die": machine["die"],
            "machine": machine["machine"],
            "resin_lot": machine["resin_lot"],
            **{key: machine[key] for key in _MACHINE_X},
            **{key: caliper[key] for key in _CALIPER_Y},
        }
        joined.append(row)
        provenance[sample_id] = {
            "sample_id": sample_id,
            "machine_serial": machine["serial"],
            "caliper_serial": caliper["serial"],
            "machine_sample_id": machine["sample_id"],
            "caliper_sample_id": caliper["sample_id"],
            "match_kind": pair["match_kind"],
            "delta_seconds": pair["delta_seconds"],
            "machine_ts": pair["machine_ts"],
            "caliper_ts": pair["caliper_ts"],
        }
    return joined, provenance


def build_snapshot(machine_rows, caliper_rows, window_seconds=300):
    """对当前版本的两本台账整组重配，返回配对结果。"""
    return match_ledgers(machine_rows, caliper_rows, window_seconds=window_seconds)
