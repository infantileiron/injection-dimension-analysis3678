X_OPTIONS = {
    "保压压力（MPa）": "hold_pressure_mpa",
    "熔体温度（℃）": "melt_temp_c",
    "冷却时间（s）": "cooling_seconds",
}
Y_OPTIONS = {
    "卡扣外宽偏差（mm）": "width_deviation_mm",
    "定位台阶高偏差（mm）": "height_deviation_mm",
}
STRATA_OPTIONS = {
    "模具 × 机台": ("die", "machine"),
    "树脂批次": ("resin_lot",),
}

SPEC = {
    "title": "注塑参数与尺寸偏差分析",
    "short_name": "molding-dimension-correlation",
    "subtitle": "核对保压、熔温和冷却时间与关键尺寸的层内关系，确定下一班怎么补测。",
    "organization": "岚川精密组件 · 成型工艺与量测室（模拟）",
    "workflow": (
        "岚川精密有 12 台注塑机，早班给电器卡扣供应商交件。巡检员按样件号把机台成型日志与"
        "量测台记录关联成 CSV；现行做法是在 Excel 里画总体散点图，再按模具和机台手抄子表。"
        "工作台复算总体与各层的秩相关，并保留样件号、量测日和设备、树脂批次。"
        "工艺工程师据此拟定补测，质量值班长审批后交下一班执行。"
    ),
    "pains": [
        "不同模具和机台的工艺窗口叠在一起，总体趋势可能与单条生产线的方向相反。",
        "机台记录的设定值和卡尺读数常重复，手抄排序容易漏掉并列秩次。",
        "换料后首检件少，相关性和补样缺口容易在交班时混为一谈，回查还要翻两份台账。",
    ],
    "steps": [
        "08:35 量测员在 IM-03 对模具 MJ-17 的卡扣取样，按 48.00 mm 外宽和 12.00 mm 台阶高记录有符号偏差。",
        "09:15 巡检员核对 IM-07 的 MJ-22 机台日志，检查 ABS-261118A/B 的标签与样件号是否一致。",
        "10:20 IM-11 用 MJ-31 加工完一轮，工艺员确认首末保压设定分别为 64 和 70 MPa。",
        "10:45 IM-05 的 MJ-44 新上模，仅有 4 条可配对的首检记录。",
        "11:05 巡检员上传 2026-11-18-卡扣首检与工艺联表.csv，核对 28 条样件来源。",
        "11:20 工艺员按模具 × 机台分层，用保压压力对卡扣外宽偏差复算，最低样本数设为 6。",
        "11:35 复核总体与三个可计算层的方向，切换树脂批次或熔体温度核查分层与常值影响。",
        "11:50 值班长核对补测清单和两端样件号，将同批两端抽样和首检缺口交下一班。",
    ],
    "methodology": [
        "输入是一件样件一行的机台日志与卡尺联表。偏差为实测尺寸减图纸名义值，保留正负和原始量测精度。",
        "对总体和每个层分别给 X、Y 升序排秩，相同值取所占名次的均值。以 R、S 表示两列秩，ρ = Σ[(R−R̄)(S−S̄)] / √(Σ(R−R̄)² × Σ(S−S̄)²)。",
        "最低样本数同时作用于总体和各层。样本不足或任一变量为常值时显示不可计算及原因。总体使用所有样件，包括未达门槛的层。",
        "按未舍入的 ρ 比较方向，|ρ| ≤ 10⁻¹² 记为零。仅当至少两个可计算层都与总体反向时报告可计算层一致反转；其余反向逐层标记。",
        "系数表、样件联表和补测清单可按层交叉核对。样件表展示此次选择的两列原值，以及各样件的总体秩、层内秩。",
        "补测缺口按门槛减当前样本数计算。排查反转时建议在已批准的工艺窗内固定其余条件，在所选参数低、高两端各补测至少 3 件。",
        "同一 CSV 和参数可复算。该分析用于确定补测与量具复核顺序；样本门槛是现场筛查口径，关联结果不能证明因果。",
    ],
    "sample_name": "2026-11-18-卡扣首检与工艺联表.csv",
    "default_dataset": "卡扣早班首检 · 2026-11-18",
    "entity": "首检样件",
    "run": "分层相关复算",
    "decision": "下一班补测决定",
    "action": "提交补测决定",
    "modes": ["按层补测", "复核量具或工艺日志", "按现行计划抽检"],
    "pages": ["成型交班", "样件量测联表", "分层秩次复算", "方向判读与补测"],
    "fields": [
        {"key": "sample_id", "label": "样件号", "type": "string", "required": True},
        {"key": "measured_on", "label": "量测日期", "type": "date", "required": True},
        {"key": "die", "label": "模具编号", "type": "string", "required": True},
        {"key": "machine", "label": "机台编号", "type": "string", "required": True},
        {"key": "resin_lot", "label": "树脂批次", "type": "string", "required": True},
        {"key": "hold_pressure_mpa", "label": "保压压力（MPa）", "type": "number", "required": True, "min": 0, "max": 250},
        {"key": "melt_temp_c", "label": "熔体温度（℃）", "type": "number", "required": True, "min": 80, "max": 450},
        {"key": "cooling_seconds", "label": "冷却时间（s）", "type": "number", "required": True, "min": 0.1, "max": 600},
        {"key": "width_deviation_mm", "label": "卡扣外宽偏差（mm）", "type": "number", "required": True, "min": -5, "max": 5},
        {"key": "height_deviation_mm", "label": "定位台阶高偏差（mm）", "type": "number", "required": True, "min": -5, "max": 5},
    ],
    "params": [
        {"key": "process_variable", "label": "工艺变量 X", "type": "select", "required": True,
         "options": list(X_OPTIONS), "default": "保压压力（MPa）"},
        {"key": "dimension_variable", "label": "尺寸变量 Y", "type": "select", "required": True,
         "options": list(Y_OPTIONS), "default": "卡扣外宽偏差（mm）"},
        {"key": "stratify_by", "label": "分层依据", "type": "select", "required": True,
         "options": list(STRATA_OPTIONS), "default": "模具 × 机台",
         "help": "模具 × 机台按组合分层；树脂批次可跨机台，按真实批号归层。"},
        {"key": "min_n", "label": "最低样本数 n", "type": "int", "required": True,
         "min": 3, "max": 10000, "default": 6, "help": "以唯一且完整的样件计数。"},
    ],
    "axes": "相关系数图按总体和分层展示 Spearman ρ；负值表示工艺值越高，偏差越趋向较低的有符号值。样本量图标出全部分层。",
}
