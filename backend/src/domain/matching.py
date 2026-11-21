"""双台账时间窗配对引擎。

机台成型日志与卡尺量测记录各有流水号，样件号可能对不上。本模块只依赖
Python 标准库，按「日期 × 模具 × 机台」分组，在时间窗内做一对一配对：

1. 样件号一致且同组的记录直接锚定（确定性配对）；锚定后仍校验时间窗，
   超窗的锚定不自动入算，转入待核对。
2. 其余记录在时间窗内建二分图，用最小费用最大流做字典序优化——
   先最大化配对件数，再最小化总时差（秒）。
3. 对最优解中的每条时间窗边逐一剔除后重算：剔除后无法保持同件数、
   同总时差的，说明它属于「所有最优解都有的配对」，计入相关分析；
   否则该配对存在并列最优的替代配法，这类边转待核对，
   只用稳定配对算相关。

补录（迟到记录）由服务层合并台账后调用 :func:`match_ledgers` 整组重配，
历史配对以不可变快照保留，因此已发分析可回查当时的配对。
"""
from collections import defaultdict
from datetime import datetime

WINDOW_SECONDS_DEFAULT = 300  # 五分钟
# 费用基数：任一可行配对的时差都小于该值，保证「件数」优先于「总时差」。
CARDINALITY_BASE = 10_000


class LedgerError(ValueError):
    """台账数据不满足配对前置条件。"""


def parse_timestamp(value):
    """解析 ``YYYY-MM-DD HH:MM:SS``（秒可省略）的时间字符串。"""
    if not isinstance(value, str) or not value.strip():
        raise LedgerError("时间戳不能为空，格式须为 YYYY-MM-DD HH:MM:SS。")
    text = value.strip()
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue
    raise LedgerError(f"时间戳「{value}」格式不正确，须为 YYYY-MM-DD HH:MM:SS。")


def _group_key(record):
    return record["measured_on"], record["die"], record["machine"]


LEDGER_KEYS = ("serial", "sample_id", "measured_on", "die", "machine", "ts")


def _validate(records, side):
    side_label = "机台日志" if side == "machine" else "卡尺记录"
    if not isinstance(records, (list, tuple)):
        raise LedgerError(f"{side_label}格式不正确，须为记录列表。")
    if not records:
        # 允许单侧台账暂缺（如补录前只有机台日志），整组转入待核对。
        return []
    seen_serial, seen_sample = set(), set()
    normalized = []
    for index, raw in enumerate(records, start=1):
        if not isinstance(raw, dict):
            raise LedgerError(f"{side_label}第 {index} 条记录格式不正确。")
        row = {}
        for key in LEDGER_KEYS:
            value = raw.get(key)
            if key == "ts":
                row["ts"] = parse_timestamp(value)
                continue
            if not isinstance(value, str) or not value.strip():
                raise LedgerError(f"{side_label}第 {index} 条记录缺少「{key}」。")
            row[key] = value.strip()
        if row["serial"] in seen_serial:
            raise LedgerError(f"{side_label}流水号「{row['serial']}」重复，请核对台账后再导入。")
        seen_serial.add(row["serial"])
        if row["sample_id"] in seen_sample:
            raise LedgerError(f"{side_label}样件号「{row['sample_id']}」重复，无法唯一锚定。")
        seen_sample.add(row["sample_id"])
        if row["ts"].date().isoformat() != row["measured_on"]:
            raise LedgerError(
                f"{side_label}流水号「{row['serial']}」的时间戳日期与量测日「{row['measured_on']}」不一致。"
            )
        normalized.append(row)
    return normalized


class _MinCostFlow:
    """邻接表最小费用最大流（Bellman-Ford 逐次最短路）。

    图规模为单组台账（现场一组至多几十条），用 Bellman-Ford 足以，
    且天然兼容残量网络中的反向负边，无需引入第三方库。每条边以
    ``[to, capacity, cost, reverse_index]`` 表示。
    """

    def __init__(self, size):
        self.size = size
        self.graph = [[] for _ in range(size)]

    def add_edge(self, u, v, capacity, cost):
        forward = [v, capacity, cost, len(self.graph[v])]
        backward = [u, 0, -cost, len(self.graph[u])]
        self.graph[u].append(forward)
        self.graph[v].append(backward)
        return forward

    def solve(self, source, sink):
        total_flow = total_cost = 0
        while True:
            dist = [None] * self.size
            previous = [None] * self.size
            dist[source] = 0
            for _ in range(self.size - 1):
                changed = False
                for u in range(self.size):
                    if dist[u] is None:
                        continue
                    for edge_index, edge in enumerate(self.graph[u]):
                        v, capacity, cost, _ = edge
                        if capacity > 0 and (dist[v] is None or dist[u] + cost < dist[v]):
                            dist[v] = dist[u] + cost
                            previous[v] = (u, edge_index)
                            changed = True
                if not changed:
                    break
            if previous[sink] is None:
                break
            node = sink
            while node != source:
                u, edge_index = previous[node]
                edge = self.graph[u][edge_index]
                edge[1] -= 1
                self.graph[node][edge[3]][1] += 1
                node = u
            total_flow += 1
            total_cost += dist[sink]
        return total_flow, total_cost


def _build_network(machines, calipers, edges, window_seconds):
    """构造配对网络，返回网络与 (i,j) → 正向边引用 的映射。

    源点 → 机台 → 卡尺 → 汇点。配对边费用 = 基数 − (窗口 − 时差)，
    固定流量下最小费用等价于最小化总时差；流量每增 1 节省一个基数，
    因此件数优先级严格高于总时差。
    """
    left_count, right_count = len(machines), len(calipers)
    left_start, right_start = 1, 1 + left_count
    source, sink = 0, right_start + right_count
    network = _MinCostFlow(sink + 1)
    for i in range(left_count):
        network.add_edge(source, left_start + i, 1, 0)
    for j in range(right_count):
        network.add_edge(right_start + j, sink, 1, 0)
    refs = {}
    for i, j, delta in edges:
        cost = CARDINALITY_BASE - (window_seconds - delta)
        refs[(i, j)] = network.add_edge(left_start + i, right_start + j, 1, cost)
    return network, source, sink, refs


def _solve(machines, calipers, edges, window_seconds, forbidden=None):
    network, source, sink, refs = _build_network(machines, calipers, edges, window_seconds)
    if forbidden:
        for key in forbidden:
            refs[key][1] = 0  # 禁用该正向边
    flow, cost = network.solve(source, sink)
    chosen = set()
    left_count = len(machines)
    for (i, j), edge in refs.items():
        if edge[1] == 0:  # 容量被用尽 → 该配对被最优解选用
            chosen.add((i, j))
    return flow, cost, chosen


def _candidate_edges(machines, calipers, window_seconds):
    edges = []
    for i, machine in enumerate(machines):
        for j, caliper in enumerate(calipers):
            delta = abs((machine["ts"] - caliper["ts"]).total_seconds())
            if delta <= window_seconds:
                edges.append((i, j, int(delta)))
    return edges


def _pair_payload(machine, caliper, delta_seconds, kind, status):
    return {
        "machine_serial": machine["serial"],
        "caliper_serial": caliper["serial"],
        "machine_sample_id": machine["sample_id"],
        "caliper_sample_id": caliper["sample_id"],
        "sample_id": machine["sample_id"],
        "measured_on": machine["measured_on"],
        "die": machine["die"],
        "machine": machine["machine"],
        "machine_ts": machine["ts"].isoformat(),
        "caliper_ts": caliper["ts"].isoformat(),
        "delta_seconds": delta_seconds,
        "match_kind": kind,
        "status": status,
    }


def _review_payload(record, side):
    return {
        "side": side,
        "serial": record["serial"],
        "sample_id": record["sample_id"],
        "measured_on": record["measured_on"],
        "die": record["die"],
        "machine": record["machine"],
        "ts": record["ts"].isoformat(),
    }


def _match_group(group_key, machines, calipers, window_seconds):
    """对单个分组执行锚定 + 时间窗最优配对。"""
    date_value, die, machine_no = group_key
    confident_pairs, review_pairs = [], []
    used_machine, used_caliper = set(), set()

    caliper_index = {item["sample_id"]: index for index, item in enumerate(calipers)}
    for i, machine in enumerate(machines):
        j = caliper_index.get(machine["sample_id"])
        if j is None:
            continue
        caliper = calipers[j]
        delta = int(abs((machine["ts"] - caliper["ts"]).total_seconds()))
        if delta <= window_seconds:
            confident_pairs.append(_pair_payload(machine, caliper, delta, "anchored", "confident"))
        else:
            # 样件号一致但时差超窗：流水号/时间至少一处可疑，不自动入算。
            pair = _pair_payload(machine, caliper, delta, "anchored", "anchor_over_window")
            pair["review_reason"] = "样件号一致但时差超出五分钟窗"
            review_pairs.append(pair)
        used_machine.add(i)
        used_caliper.add(j)

    free_machines = [item for index, item in enumerate(machines) if index not in used_machine]
    free_calipers = [item for index, item in enumerate(calipers) if index not in used_caliper]
    edges = _candidate_edges(free_machines, free_calipers, window_seconds)
    pending_machine, pending_caliper = list(free_machines), list(free_calipers)

    if edges:
        flow, cost, chosen = _solve(free_machines, free_calipers, edges, window_seconds)
        # 逐一剔除最优解中的边，判断是否为所有最优解共有。
        for i, j in sorted(chosen):
            reduced_flow, reduced_cost, _ = _solve(
                free_machines, free_calipers, edges, window_seconds, forbidden={(i, j)}
            )
            delta = int(abs((free_machines[i]["ts"] - free_calipers[j]["ts"]).total_seconds()))
            if reduced_flow < flow or reduced_cost > cost:
                confident_pairs.append(
                    _pair_payload(free_machines[i], free_calipers[j], delta, "time_window", "confident")
                )
            else:
                pair = _pair_payload(free_machines[i], free_calipers[j], delta, "time_window", "ambiguous")
                pair["review_reason"] = "存在并列最优配法，配对不唯一"
                review_pairs.append(pair)
        matched_machine = {i for i, _ in chosen}
        matched_caliper = {j for _, j in chosen}
        pending_machine = [item for index, item in enumerate(free_machines) if index not in matched_machine]
        pending_caliper = [item for index, item in enumerate(free_calipers) if index not in matched_caliper]

    confident_pairs.sort(key=lambda item: (item["machine_ts"], item["machine_serial"]))
    review_pairs.sort(key=lambda item: (item["machine_ts"], item["machine_serial"]))

    return {
        "group_key": {"measured_on": date_value, "die": die, "machine": machine_no},
        "machine_count": len(machines),
        "caliper_count": len(calipers),
        "confident_pairs": confident_pairs,
        "review_pairs": review_pairs,
        "unmatched_machine": [_review_payload(item, "machine") for item in pending_machine],
        "unmatched_caliper": [_review_payload(item, "caliper") for item in pending_caliper],
        "window_seconds": window_seconds,
    }


def match_ledgers(machine_rows, caliper_rows, window_seconds=WINDOW_SECONDS_DEFAULT):
    """配对入口：校验、分组、逐组配对，汇总整批结果。

    返回稳定配对（``confident_pairs``，入算相关）、歧义与超窗锚定
    （``review_pairs``）、两侧未配上的待核对记录（``pending_records``）
    以及分组明细，供结果页与回查使用。
    """
    if not isinstance(window_seconds, int) or not 60 <= window_seconds <= 1800:
        raise LedgerError("时间窗须为 60 至 1800 秒之间的整数。")
    machines = _validate(machine_rows, "machine")
    calipers = _validate(caliper_rows, "caliper")
    if not machines and not calipers:
        raise LedgerError("机台日志与卡尺记录均为空，无法配对。")

    machine_groups, caliper_groups = defaultdict(list), defaultdict(list)
    for record in machines:
        machine_groups[_group_key(record)].append(record)
    for record in calipers:
        caliper_groups[_group_key(record)].append(record)

    groups = []
    for key in sorted(set(machine_groups) | set(caliper_groups)):
        group_machines = sorted(machine_groups.get(key, []), key=lambda item: item["ts"])
        group_calipers = sorted(caliper_groups.get(key, []), key=lambda item: item["ts"])
        groups.append(_match_group(key, group_machines, group_calipers, window_seconds))

    confident_pairs, review_pairs, pending = [], [], []
    for group in groups:
        confident_pairs.extend(group["confident_pairs"])
        review_pairs.extend(group["review_pairs"])
        for item in group["unmatched_machine"] + group["unmatched_caliper"]:
            item["review_reason"] = "五分钟窗内无一对一候选"
            pending.append(item)

    return {
        "window_seconds": window_seconds,
        "group_count": len(groups),
        "machine_total": len(machines),
        "caliper_total": len(calipers),
        "confident_count": len(confident_pairs),
        "review_pair_count": len(review_pairs),
        "pending_count": len(pending),
        "confident_pairs": confident_pairs,
        "review_pairs": review_pairs,
        "pending_records": pending,
        "groups": groups,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
