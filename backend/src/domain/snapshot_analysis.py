"""基于配对快照的秩相关分析。

稳定配对拼成联表后复用 :func:`src.domain.analysis.analyze`，再把本次
入算配对（含两侧流水号、时差）与待核对记录作为附加表写入结果，使结果页
能同时呈现参与相关计算的配对和需要人工核对的歧义/迟到记录。
"""
from .analysis import _table, analyze
from .ledger_join import join_confident_pairs


def _pair_columns():
    return [
        ("sample_id", "入算样件号"), ("match_kind", "配对方式"),
        ("machine_serial", "机台流水号"), ("caliper_serial", "卡尺流水号"),
        ("machine_sample_id", "机台账样件号"), ("caliper_sample_id", "卡尺台账样件号"),
        ("machine_ts", "机台记录时间"), ("caliper_ts", "卡尺记录时间"),
        ("delta_seconds", "时差（秒）"),
    ]


def _kind_label(kind):
    return {"anchored": "样件号锚定", "time_window": "五分钟窗配对"}.get(kind, kind)


def analyze_snapshot(machine_rows, caliper_rows, snapshot_result, params):
    joined, provenance = join_confident_pairs(machine_rows, caliper_rows, snapshot_result)
    result = analyze(joined, params)

    pair_rows = []
    for sample_id, info in sorted(provenance.items()):
        pair_rows.append({
            "sample_id": sample_id,
            "match_kind": _kind_label(info["match_kind"]),
            "machine_serial": info["machine_serial"],
            "caliper_serial": info["caliper_serial"],
            "machine_sample_id": info["machine_sample_id"],
            "caliper_sample_id": info["caliper_sample_id"],
            "machine_ts": info["machine_ts"],
            "caliper_ts": info["caliper_ts"],
            "delta_seconds": info["delta_seconds"],
        })

    review_rows = [{
        "machine_serial": pair["machine_serial"], "caliper_serial": pair["caliper_serial"],
        "machine_sample_id": pair["machine_sample_id"], "caliper_sample_id": pair["caliper_sample_id"],
        "delta_seconds": pair["delta_seconds"], "review_reason": pair["review_reason"],
        "status": pair["status"],
    } for pair in snapshot_result["review_pairs"]]

    pending_rows = [{
        "side": "机台日志" if item["side"] == "machine" else "卡尺记录",
        "serial": item["serial"], "sample_id": item["sample_id"],
        "measured_on": item["measured_on"], "die": item["die"], "machine": item["machine"],
        "ts": item["ts"], "review_reason": item["review_reason"],
    } for item in snapshot_result["pending_records"]]

    result["snapshot"] = {
        "snapshot_id": snapshot_result.get("snapshot_id"),
        "window_seconds": snapshot_result["window_seconds"],
        "group_count": snapshot_result["group_count"],
        "confident_count": snapshot_result["confident_count"],
        "review_pair_count": snapshot_result["review_pair_count"],
        "pending_count": snapshot_result["pending_count"],
    }
    result["metrics"].insert(1, {
        "label": "本次入算配对", "value": snapshot_result["confident_count"],
        "detail": f"时间窗 {snapshot_result['window_seconds']} 秒",
    })
    result["tables"].append(_table("本次入算配对（流水号溯源）", _pair_columns(), pair_rows))
    result["tables"].append(_table("待核对配对（并列最优或超窗锚定）", [
        ("machine_serial", "机台流水号"), ("caliper_serial", "卡尺流水号"),
        ("machine_sample_id", "机台账样件号"), ("caliper_sample_id", "卡尺台账样件号"),
        ("delta_seconds", "时差（秒）"), ("review_reason", "待核对原因"),
    ], review_rows))
    result["tables"].append(_table("待核对记录（未配上）", [
        ("side", "台账"), ("serial", "流水号"), ("sample_id", "样件号"),
        ("measured_on", "量测日期"), ("die", "模具"), ("machine", "机台"),
        ("ts", "记录时间"), ("review_reason", "待核对原因"),
    ], pending_rows))
    return result
