"""
四大工具链（Agent 自主编排 + 失败重试）
=====================================
1. nl2sql_tool          自然语言 → SQL，查询学生成绩/自习/消费真实数据集并统计
2. time_conflict_tool   时间片切片算法，识别方案时间重叠 / 超熄灯 / 超预算冲突
3. weighted_balance_tool 冲突场景下按权重计算折中均衡方案
4. gantt_tool           生成周学习自习规划甘特图数据

每个工具都通过 run_tool() 调用，内置失败自动修正入参重试。
"""
from .database import get_conn


# ----------------------------------------------------- 工具统一调度 + 重试 ----
def run_tool(func, *args, retries=2, **kwargs):
    """工具统一入口：失败自动重试（演示「工具调用失败重试链」）。"""
    last_err = None
    for attempt in range(retries + 1):
        try:
            return {"ok": True, "attempt": attempt + 1, "result": func(*args, **kwargs)}
        except Exception as e:  # noqa: BLE001
            last_err = str(e)
    return {"ok": False, "attempt": retries + 1, "error": last_err, "result": None}


# ----------------------------------------------------------- 1. NL2SQL ----
def nl2sql_tool(query: str):
    """规则版 NL2SQL：把中文意图映射为 SQL 查询真实表（可替换为 LLM 版）。"""
    q = query.lower()
    conn = get_conn()
    try:
        if "挂科" in query or "fail" in q:
            sql = "SELECT name, COUNT(*) AS 挂科次数 FROM grades WHERE failed=1 GROUP BY student_id ORDER BY 挂科次数 DESC"
        elif "平均" in query and ("消费" in query or "花" in query):
            sql = "SELECT name, ROUND(SUM(amount),1) AS 月度消费 FROM consumption GROUP BY student_id ORDER BY 月度消费 DESC"
        elif "贵" in query or "高价" in query or "菜" in query:
            sql = "SELECT item AS 菜品, ROUND(AVG(amount),1) AS 单价, COUNT(*) AS 频次 FROM consumption WHERE category='食堂' GROUP BY item ORDER BY 频次 DESC LIMIT 6"
        elif "自习" in query or "co2" in q or "环境" in query:
            sql = "SELECT floor AS 自习室, hour AS 时段, traffic AS 人流量, co2 FROM iot ORDER BY co2 ASC LIMIT 8"
        elif "成绩" in query or "分数" in query or "风险" in query:
            sql = "SELECT name, subject AS 科目, ROUND(AVG(score),1) AS 均分 FROM grades GROUP BY student_id, subject ORDER BY 均分 ASC LIMIT 10"
        else:
            sql = "SELECT name, subject, score FROM grades LIMIT 10"
        rows = conn.execute(sql).fetchall()
        cols = rows[0].keys() if rows else []
        data = [dict(r) for r in rows]
        return {"sql": sql, "columns": list(cols), "rows": data,
                "summary": f"命中 {len(data)} 条记录"}
    finally:
        conn.close()


# --------------------------------------------- 2. 时间片切片冲突检测算法 ----
def time_conflict_tool(state: dict):
    """
    state 含各 Agent 当前选定方案。返回冲突清单。
    冲突类型：
      time_overlap  —— 复习所需时长无法塞进推荐自习时段（时间重叠/不足）
      policy_time   —— 自习/学习结束时间超出自习室关闭 22:30 或宿舍熄灯 23:00
      budget        —— 高强度方案推高每日餐饮开销，超出预算上限
    """
    conflicts = []
    aca = state["academic"]["options"][state["academic"]["selected"]]
    env = state["study_env"]["options"][state["study_env"]["selected"]]
    logi = state["logistics"]
    pol = state["policy"]["constraints"]

    # 冲突1：复习所需时长 vs 推荐自习时段可用时长
    # 允许最多 1h 回宿舍补学（熄灯前可承载）作为可接受余量，超出才算冲突。
    slot_len = round(env["end"] - env["start"], 1)
    HOME_TOLERANCE = 1.0
    if aca["daily_hours"] > slot_len + HOME_TOLERANCE + 0.01:
        conflicts.append({
            "type": "time_overlap", "agents": ["academic", "study_env"],
            "detail": f"复习计划需 {aca['daily_hours']}h/天，但推荐自习时段「{env['floor']} "
                      f"{_fmt(env['start'])}-{_fmt(env['end'])}」仅 {slot_len}h（含1h居家补学余量仍不足），时间冲突。",
        })

    # 冲突2：自习结束时间是否超出自习室关闭 / 宿舍熄灯
    study_room_close = pol["study_room_close"]
    lights_out = pol["lights_out"]
    if env["end"] > study_room_close + 0.01:
        conflicts.append({
            "type": "policy_time", "agents": ["study_env", "policy"],
            "detail": f"自习时段结束于 {_fmt(env['end'])}，超出自习室关闭时间 {_fmt(study_room_close)}，违反校规。",
        })
    # 居家补学：若自习装不下，剩余时长压到宿舍并可能超熄灯
    home_overflow = max(0.0, aca["daily_hours"] - slot_len)
    if home_overflow > 0:
        home_end = min(lights_out + 2, env["end"] + home_overflow)
        if home_end > lights_out + 0.01:
            conflicts.append({
                "type": "policy_time", "agents": ["academic", "policy"],
                "detail": f"自习装不下需回宿舍补学 {round(home_overflow,1)}h，预计学到 "
                          f"{_fmt(home_end)}，超出宿舍熄灯 {_fmt(lights_out)}。",
            })

    # 冲突3：高强度方案推高餐饮开销超预算
    intensity_factor = 1.0 + (aca["daily_hours"] - 3) * 0.12  # 学得越久越能吃
    projected_daily = round(logi["base_daily_meal"] * max(1.0, intensity_factor), 1)
    if projected_daily > logi["daily_meal_cap"] + 0.01:
        conflicts.append({
            "type": "budget", "agents": ["academic", "logistics"],
            "detail": f"{aca['name']}强度下预计每日餐饮 {projected_daily} 元，超出预算上限 "
                      f"{logi['daily_meal_cap']} 元/天。",
        })
    return conflicts


# ----------------------------------------- 3. 加权均衡计算（折中算法） ----
def weighted_balance_tool(state: dict, conflicts: list, weights: dict):
    """
    权重：学业风险 > 环境舒适度 > 预算节省 > 政策柔性条款。
    在保学业优先的前提下，依次微调环境时段、压缩强度、放宽预算，输出折中方案。
    返回调整说明 + 新 state。
    """
    actions = []
    aca = state["academic"]
    env = state["study_env"]
    logi = state["logistics"]
    pol = state["policy"]["constraints"]

    for c in conflicts:
        if c["type"] == "time_overlap":
            # 优先换更长/更优的自习时段；不够则在学业权重内小幅压缩冲刺时长
            best = _pick_longest_slot(env)
            if best is not None and best != env["selected"]:
                env["selected"] = best
                actions.append(f"[环境×权重{weights['env']}] 改选时段更长的自习方案：{env['options'][best]['floor']}")
            sel = aca["options"][aca["selected"]]
            slot = env["options"][env["selected"]]
            slot_len = slot["end"] - slot["start"]
            if sel["daily_hours"] > slot_len:
                # 学业最高权重：仅压缩到「自习时段 + 1h 居家」可承载
                new_hours = round(min(sel["daily_hours"], slot_len + 1.0), 1)
                if new_hours != sel["daily_hours"]:
                    actions.append(f"[学业×权重{weights['academic']}] 复习时长 {sel['daily_hours']}h→{new_hours}h，"
                                   f"保留核心刷题、压缩重复练习。")
                    sel["daily_hours"] = new_hours
                    _rescale_blocks(sel)
        elif c["type"] == "policy_time":
            # 政策为刚性时间约束：自习时段整体前移
            slot = env["options"][env["selected"]]
            if slot["end"] > pol["study_room_close"]:
                shift = round(slot["end"] - pol["study_room_close"], 1)
                slot["start"] = round(slot["start"] - shift, 1)
                slot["end"] = round(slot["end"] - shift, 1)
                actions.append(f"[政策×权重{weights['policy']}] 自习时段整体前移 {shift}h 至 "
                               f"{_fmt(slot['start'])}-{_fmt(slot['end'])}，满足 22:30 关闭。")
        elif c["type"] == "budget":
            # 预算权重低于学业：先给省钱搭配，再适度上浮上限（柔性）
            logi["daily_meal_cap"] = round(logi["daily_meal_cap"] * 1.08, 1)
            actions.append(f"[预算×权重{weights['budget']}] 启用平价窗口搭配（白米饭+例汤+1荤1素），"
                           f"每日上限柔性上浮至 {logi['daily_meal_cap']} 元。")
    if not actions:
        actions.append("各方案已无冲突，无需均衡调整。")
    return {"actions": actions, "state": state}


# --------------------------------------------------- 4. 甘特图数据生成 ----
def gantt_tool(state: dict):
    """生成一周学习+自习规划甘特图数据（前端 Chart.js 渲染）。"""
    aca = state["academic"]["options"][state["academic"]["selected"]]
    env = state["study_env"]["options"][state["study_env"]["selected"]]
    days = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    bars = []
    for d in days:
        cur = env["start"]
        for blk in aca["blocks"]:
            seg = round(aca["daily_hours"] * blk["ratio"], 1)
            bars.append({"day": d, "subject": blk["subject"],
                         "start": round(cur, 1), "end": round(cur + seg, 1),
                         "floor": env["floor"]})
            cur += seg
    return {"days": days, "bars": bars,
            "slot": {"floor": env["floor"], "start": env["start"], "end": env["end"]}}


# ------------------------------------------------------------- helpers ----
def _fmt(h):
    hh = int(h)
    mm = int(round((h - hh) * 60))
    return f"{hh:02d}:{mm:02d}"


def _pick_longest_slot(env):
    lengths = [(o["end"] - o["start"], i) for i, o in enumerate(env["options"])]
    lengths.sort(reverse=True)
    return lengths[0][1] if lengths else None


def _rescale_blocks(option):
    """daily_hours 变化后，blocks 的 ratio 不变，hours 字段重算。"""
    for blk in option["blocks"]:
        blk["hours"] = round(option["daily_hours"] * blk["ratio"], 1)
