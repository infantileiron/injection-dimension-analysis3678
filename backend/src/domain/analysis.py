from collections import defaultdict
from datetime import date
from math import fsum, isfinite, sqrt

from .spec import SPEC, STRATA_OPTIONS, X_OPTIONS, Y_OPTIONS


ZERO_TOLERANCE = 1e-12


def _validated_rows(rows):
    if not isinstance(rows, (list, tuple)) or not rows:
        raise ValueError("样件联表为空或格式不正确，请导入包含至少一条样件的 CSV。")
    normalized = []
    seen = set()
    for index, raw in enumerate(rows, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"第 {index} 条样件的格式不正确，请检查 CSV 列。")
        row = {}
        for field in SPEC["fields"]:
            key, label, kind = field["key"], field["label"], field["type"]
            value = raw.get(key)
            if kind in ("string", "date"):
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"第 {index} 条样件缺少「{label}」，请补填后导入。")
                value = value.strip()
                if kind == "date":
                    try:
                        if date.fromisoformat(value).isoformat() != value:
                            raise ValueError
                    except ValueError:
                        raise ValueError(f"第 {index} 条样件的「{label}」须为有效的 YYYY-MM-DD 日期。") from None
            else:
                lower, upper = field["min"], field["max"]
                if type(value) not in (int, float) or not lower <= value <= upper or not isfinite(value):
                    raise ValueError(
                        f"第 {index} 条样件（{row['sample_id']}）的「{label}」须为 {lower:g} 至 {upper:g} 的有限数值，请核对单位和原表。"
                    )
            row[key] = value
        sample_id = row["sample_id"]
        if sample_id in seen:
            raise ValueError(f"第 {index} 条样件的样件号「{sample_id}」重复，请核对联表并保留一条记录。")
        seen.add(sample_id)
        normalized.append(row)
    return normalized


def validate_rows(rows):
    _validated_rows(rows)


def _validated_params(params):
    if not isinstance(params, dict):
        raise ValueError("复算参数格式不正确，请重新选择变量、分层依据和最低样本数。")
    values = {}
    for field in SPEC["params"]:
        key, label = field["key"], field["label"]
        value = params.get(key, field["default"])
        if field["type"] == "select":
            if value not in field["options"]:
                raise ValueError(f"「{label}」无效，请从 {'、'.join(field['options'])} 中选择。")
        else:
            lower, upper = field["min"], field["max"]
            if type(value) is not int or not lower <= value <= upper:
                raise ValueError(f"「{label}」须为 {lower} 至 {upper} 的整数。")
        values[key] = value
    return values


def _average_ranks(values):
    ordered = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    start = 0
    while start < len(ordered):
        stop = start + 1
        while stop < len(ordered) and values[ordered[start]] == values[ordered[stop]]:
            stop += 1
        rank = (start + 1 + stop) / 2
        for position in range(start, stop):
            ranks[ordered[position]] = rank
        start = stop
    return ranks


def _estimate(rows, x_key, y_key, minimum):
    x = [row[x_key] for row in rows]
    y = [row[y_key] for row in rows]
    x_ranks = _average_ranks(x)
    y_ranks = _average_ranks(y)
    count = len(rows)
    missing = max(0, minimum - count)
    x_varies, y_varies = min(x) != max(x), min(y) != max(y)
    constant_axes = "、".join(axis for axis, varies in (("X", x_varies), ("Y", y_varies)) if not varies)
    reasons = []
    if missing:
        reasons.append(f"样本不足，缺 {missing} 件")
    if constant_axes:
        reasons.append(f"{constant_axes} 为常值")

    rho = None
    if not reasons:
        rank_mean = (count + 1) / 2
        dx = [rank - rank_mean for rank in x_ranks]
        dy = [rank - rank_mean for rank in y_ranks]
        numerator = fsum(a * b for a, b in zip(dx, dy))
        denominator = sqrt(fsum(a * a for a in dx) * fsum(b * b for b in dy))
        rho = max(-1.0, min(1.0, numerator / denominator))
    return rho, reasons, dict(zip((row["sample_id"] for row in rows), zip(x_ranks, y_ranks)))


def _direction(rho):
    if rho is None:
        return None
    if abs(rho) <= ZERO_TOLERANCE:
        return 0
    return 1 if rho > 0 else -1


def _display_rho(rho):
    if rho is None:
        return "—"
    if _direction(rho) == 0:
        return 0.0
    return float(f"{rho:.8g}")


def _group_label(keys):
    if len(keys) == 1:
        return keys[0]
    return f"{keys[0]} / {keys[1]}"


def _sample_plan(label, rows, x_key, minimum, direction, pooled_direction, is_reversed, stratify_by):
    count = len(rows)
    x_values = [row[x_key] for row in rows]
    low, high = min(x_values), max(x_values)
    fixed = "固定树脂批次及其他工艺设定" if stratify_by == "模具 × 机台" else "固定同一模具、机台和其他工艺设定"
    if count < minimum:
        gap = minimum - count
        priority = "优先补足样本"
        action = f"至少补 {gap} 件达到 n={minimum}。{fixed}，在已批准的工艺窗内让累计样件覆盖 X 的低、高两端。"
    elif direction is None:
        priority = "先复核常值"
        action = "核对 X 日志的设定值、Y 量具的分辨率及原始读数。确认记录有效后，按批准的窗口补录有覆盖度的样件。"
    elif is_reversed or (pooled_direction == 0 and direction):
        priority = "复测反向层" if is_reversed else "复测层内趋势"
        action = f"{fixed}，在已批准的工艺窗内选定 X 的低、高两个测点，各补测至少 3 件，按层复算。"
    else:
        priority = "维持常规抽检"
        action = f"{fixed}，按现行计划记录样件。遇换模、换机或换批时单独留档。"
    return {
        "stratum": label,
        "priority": priority,
        "missing_n": max(0, minimum - count),
        "observed_x": f"{low:g} ～ {high:g}" if low != high else f"{low:g}（单点）",
        "low_sample": next(row["sample_id"] for row in rows if row[x_key] == low),
        "high_sample": next(row["sample_id"] for row in rows if row[x_key] == high),
        "action": action,
    }


def _table(title, columns, rows):
    return {"title": title, "columns": [{"key": key, "label": label} for key, label in columns], "rows": rows}


def analyze(rows, params):
    rows = _validated_rows(rows)
    values = _validated_params(params)
    x_label, y_label = values["process_variable"], values["dimension_variable"]
    x_key, y_key = X_OPTIONS[x_label], Y_OPTIONS[y_label]
    stratify_by, minimum = values["stratify_by"], values["min_n"]
    stratify_keys = STRATA_OPTIONS[stratify_by]
    groups = defaultdict(list)
    for row in sorted(rows, key=lambda row: (row["measured_on"], row["sample_id"])):
        groups[tuple(row[key] for key in stratify_keys)].append(row)

    pooled_rho, pooled_reasons, pooled_ranks = _estimate(rows, x_key, y_key, minimum)
    pooled_direction = _direction(pooled_rho)
    directions = {1: "正向", -1: "负向", 0: "零相关", None: "不可计算"}
    coefficient_rows = [{
        "stratum": "总体", "n": len(rows), "rho": _display_rho(pooled_rho),
        "direction": directions[pooled_direction], "comparison": "总体基准", "detail": "。".join(pooled_reasons) or "全部样件",
    }]
    source_rows, sampling_rows, rho_series, size_series = [], [], [], []
    if pooled_rho is not None:
        rho_series.append({"label": "总体", "value": _display_rho(pooled_rho)})
    reversed_count = available_count = 0
    for keys, group in sorted(groups.items()):
        label = _group_label(keys)
        rho, reasons, group_ranks = _estimate(group, x_key, y_key, minimum)
        direction = _direction(rho)
        is_reversed = bool(direction and pooled_direction and direction == -pooled_direction)
        if rho is not None:
            available_count += 1
            rho_series.append({"label": label, "value": _display_rho(rho)})
        if is_reversed:
            reversed_count += 1
            comparison = "与总体反向"
        elif direction is None or pooled_direction is None:
            comparison = "无法比较"
        elif direction == 0 or pooled_direction == 0:
            comparison = "存在零相关"
        else:
            comparison = "与总体同向"
        coefficient_rows.append({
            "stratum": label, "n": len(group), "rho": _display_rho(rho), "direction": directions[direction],
            "comparison": comparison, "detail": "。".join(reasons) or "符合计算门槛",
        })
        size_series.append({"label": label, "value": len(group)})
        sampling_rows.append(_sample_plan(
            label, group, x_key, minimum, direction, pooled_direction, is_reversed, stratify_by,
        ))
        for row in group:
            sample_id = row["sample_id"]
            x_rank, y_rank = pooled_ranks[sample_id]
            group_x_rank, group_y_rank = group_ranks[sample_id]
            source_rows.append({
                "stratum": label, "sample_id": sample_id, "measured_on": row["measured_on"],
                "die": row["die"], "machine": row["machine"], "resin_lot": row["resin_lot"],
                "x": row[x_key], "y": row[y_key], "pooled_x_rank": x_rank, "pooled_y_rank": y_rank,
                "group_x_rank": group_x_rank, "group_y_rank": group_y_rank,
            })

    unavailable_count = len(groups) - available_count
    if pooled_rho is None:
        headline = "总体相关不可计算，先核对样本量或常值列"
    elif reversed_count >= 2 and reversed_count == available_count:
        headline = f"总体{directions[pooled_direction]}，{reversed_count} 个可计算层全部反转为{directions[-pooled_direction]}"
    elif reversed_count:
        headline = f"总体{directions[pooled_direction]}，有 {reversed_count} 个可计算层与总体反向"
    elif not available_count:
        headline = "总体已有系数，各层仍需补样或复核常值"
    elif pooled_direction == 0:
        headline = "总体秩相关为零，交班时按层查看方向"
    else:
        headline = "可比较的分层未出现方向反转"

    note = f"{x_label} × {y_label}，按{stratify_by}分层，最低 n={minimum}。总体纳入全部 {len(rows)} 件。"
    if unavailable_count:
        note += f" {unavailable_count} 个层不可计算，原因列在系数表。"
    if stratify_by == "树脂批次":
        note += " 同一批料可横跨多副模具和多台机台，可切换分层依据核对设备差异。"
    note += " ρ 用于安排补测和复核，调参或放行仍依照现行工艺审批。"
    priority_order = {"优先补足样本": 0, "先复核常值": 1, "复测反向层": 2, "复测层内趋势": 2, "维持常规抽检": 3}
    sampling_rows.sort(key=lambda plan: (priority_order[plan["priority"]], -plan["missing_n"], plan["stratum"]))

    charts = []
    if rho_series:
        charts.append({"title": "总体与各层 Spearman ρ", "kind": "bar", "series": rho_series})
    charts.append({"title": "各层样件数", "kind": "bar", "series": size_series})
    has_layer_signal = any(plan["priority"] == "复测层内趋势" for plan in sampling_rows)
    return {
        "state": "warning" if pooled_rho is None or unavailable_count or reversed_count or has_layer_signal else "ok",
        "headline": headline,
        "note": note,
        "metrics": [
            {"label": "总体 Spearman ρ", "value": _display_rho(pooled_rho), "detail": directions[pooled_direction]},
            {"label": "可计算层", "value": f"{available_count} / {len(groups)}", "detail": f"最低 n={minimum}"},
            {"label": "反向层", "value": reversed_count if pooled_direction in (-1, 1) and available_count else "—"},
            {"label": "补足门槛缺口", "value": sum(plan["missing_n"] for plan in sampling_rows), "detail": "按层加总，单位为件"},
        ],
        "tables": [
            _table("总体与分层系数", [
                ("stratum", "总体 / 分层"), ("n", "样件数 n"), ("rho", "Spearman ρ"),
                ("direction", "方向"), ("comparison", "相对总体"), ("detail", "计算说明"),
            ], coefficient_rows),
            _table("下一班补测清单", [
                ("stratum", "分层"), ("priority", "处置"), ("missing_n", "离门槛差几件"),
                ("observed_x", f"已测范围 · {x_label}"), ("low_sample", "低端样件号"),
                ("high_sample", "高端样件号"), ("action", "下一班动作"),
            ], sampling_rows),
            _table("样件来源与排秩明细", [
                ("stratum", "分层"), ("sample_id", "样件号"), ("measured_on", "量测日期"), ("die", "模具"),
                ("machine", "机台"), ("resin_lot", "树脂批次"), ("x", x_label), ("y", y_label),
                ("pooled_x_rank", "总体 X 秩"), ("pooled_y_rank", "总体 Y 秩"),
                ("group_x_rank", "层内 X 秩"), ("group_y_rank", "层内 Y 秩"),
            ], source_rows),
        ],
        "charts": charts,
    }
