# tools.py —— 全部 Tool / Function Schema 定义
# 使用 LangChain @tool 装饰器，自动为每个函数生成 JSON Schema
import json
import logging
from langchain_core.tools import tool
from .cache import cache_get, cache_set, _make_hash

logger = logging.getLogger(__name__)


# ===================== 数据查询工具（4个） =====================

@tool
def query_grades(student_id: str) -> str:
    """查询指定学生的所有科目成绩。返回科目名称、分数、是否挂科信息。"""
    cache_key = f"grades:{student_id}"
    cached_val = cache_get(cache_key)
    if cached_val is not None:
        return cached_val

    from .database import get_mysql_conn
    try:
        conn = get_mysql_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT subject, score, failed FROM grades WHERE student_id = %s",
            (student_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        if not rows:
            return "未查询到成绩数据"
        lines = []
        for r in rows:
            fail_tag = " [挂科]" if r.get("failed") == 1 else ""
            lines.append(f"- {r['subject']}：{r['score']}分{fail_tag}")
        result = "\n".join(lines)
        cache_set(cache_key, result, ttl=1800)
        return result
    except Exception as e:
        logger.error(f"查询成绩失败: {e}")
        return f"查询成绩失败: {e}"


@tool
def query_consumption(student_id: str) -> str:
    """查询指定学生的月度消费明细。返回各类别的消费总额和笔数。"""
    cache_key = f"consumption:{student_id}"
    cached_val = cache_get(cache_key)
    if cached_val is not None:
        return cached_val

    from .database import get_mysql_conn
    try:
        conn = get_mysql_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT category, SUM(amount) AS total, COUNT(*) AS cnt "
            "FROM consumption WHERE student_id = %s GROUP BY category",
            (student_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        if not rows:
            return "未查询到消费数据"
        lines = []
        total = 0
        for r in rows:
            lines.append(f"- {r['category']}：{r['total']:.1f}元（{r['cnt']}笔）")
            total += r['total']
        lines.append(f"合计：{total:.1f}元")
        result = "\n".join(lines)
        cache_set(cache_key, result, ttl=1800)
        return result
    except Exception as e:
        logger.error(f"查询消费失败: {e}")
        return f"查询消费失败: {e}"


@tool
def query_iot_data() -> str:
    """查询自习室IoT传感器数据。返回各楼层各时段的人流量、CO2浓度、温度。"""
    cache_key = "iot:all"
    cached_val = cache_get(cache_key)
    if cached_val is not None:
        return cached_val

    from .database import get_mysql_conn
    try:
        conn = get_mysql_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT floor, hour, traffic, co2, temp FROM iot ORDER BY floor, hour")
        rows = cursor.fetchall()
        conn.close()
        if not rows:
            return "未查询到IoT数据"
        lines = []
        for r in rows[:15]:
            lines.append(f"- {r['floor']}楼 {r['hour']}时：人流{r['traffic']}，CO2 {r['co2']}ppm，温度{r['temp']}°C")
        result = "\n".join(lines)
        cache_set(cache_key, result, ttl=600)
        return result
    except Exception as e:
        logger.error(f"查询IoT数据失败: {e}")
        return f"查询IoT数据失败: {e}"


@tool
def search_policy(query: str, top_k: int = 3) -> str:
    """根据关键词搜索校园政策校规。输入搜索关键词，返回相关校规条文。"""
    cache_key = f"policy:{_make_hash(query, top_k)}"
    cached_val = cache_get(cache_key)
    if cached_val is not None:
        return cached_val

    try:
        from .database import get_static_rule_store
        store = get_static_rule_store()
        hits = store.search(query, top_k=top_k)
        if not hits:
            return "未找到相关校规"
        result = "\n".join([f"- {h['text']}" for h in hits])
        cache_set(cache_key, result, ttl=86400)
        return result
    except Exception as e:
        logger.error(f"搜索校规失败: {e}")
        return f"搜索校规失败: {e}"


# ===================== Agent 分析工具（5个） =====================

@tool
def analyze_study_plan(student_id: str, daily_hours: float = 4.0, user_request: str = "") -> str:
    """分析学生成绩并生成学习提升计划。查询真实成绩数据，输出分点计划。user_request 为学生原始需求（最高优先级）。"""
    from .llm import llm as _llm
    grades_raw = query_grades.invoke({"student_id": student_id})

    request_block = ""
    if user_request:
        request_block = f"""
【最高优先级 — 学生原始需求】
{user_request}
以上需求必须被完整、严格地执行，不可偏离。数据仅作参考补充。
"""

    prompt = f"""你是专业学业规划师。
{request_block}
学生成绩数据（仅供参考，不可覆盖学生需求）：
{grades_raw}

要求每日学习 {daily_hours} 小时。
请生成一份**可执行、简洁、分点**的学习提升计划。
如果学生指定了科目或时间分配，必须严格遵守。"""
    return _llm(prompt)


@tool
def analyze_budget_plan(student_id: str, monthly_budget: float = 1200.0, user_request: str = "") -> str:
    """分析学生消费并生成预算分配方案。查询真实消费数据，输出分点建议。user_request 为学生原始需求（最高优先级）。"""
    from .llm import llm as _llm
    expenses_raw = query_consumption.invoke({"student_id": student_id})

    request_block = ""
    if user_request:
        request_block = f"""
【最高优先级 — 学生原始需求】
{user_request}
以上需求必须被完整、严格地执行，不可偏离。消费数据仅作参考补充。
"""

    prompt = f"""你是校园消费规划师。
{request_block}
学生月度消费数据（仅供参考，不可覆盖学生需求）：
{expenses_raw}
总预算：{monthly_budget} 元。

请给出**简洁、可执行**的省钱与预算分配建议，分点。
如果学生指定了预算分配方式或省钱目标，必须严格遵守。"""
    return _llm(prompt)


@tool
def analyze_study_room(student_id: str, want_hours: float = 4.0, user_request: str = "") -> str:
    """分析IoT数据并推荐最优自习楼层和时间段。查询真实IoT传感器数据。user_request 为学生原始需求（最高优先级）。"""
    from .llm import llm as _llm
    iot_raw = query_iot_data.invoke({})

    request_block = ""
    if user_request:
        request_block = f"""
【最高优先级 — 学生原始需求】
{user_request}
以上需求必须被完整、严格地执行，不可偏离。IoT数据仅作参考补充。
"""

    prompt = f"""你是自习室推荐官。
{request_block}
自习室IoT实时数据（仅供参考，不可覆盖学生需求）：
{iot_raw}

学生需要连续自习 {want_hours} 小时。
请推荐**最优楼层、最佳时间段**，简洁分点。
如果学生指定了楼层或时间段，必须严格遵守。"""
    return _llm(prompt)


@tool
def get_policy_constraints() -> str:
    """获取校园政策硬约束（自习室关门、熄灯、GPA门槛等）。返回JSON格式的约束参数。"""
    constraints = {
        "study_room_close": 22.5,
        "lights_out": 23.0,
        "scholarship_gpa": 85,
        "monthly_utility_cap": 150,
        "max_daily_study": 12.0,
        "min_daily_study": 1.0,
        "max_budget_ratio": 1.2,
    }
    return json.dumps(constraints, ensure_ascii=False)


@tool
def detect_conflicts(academic_state: str, logistics_state: str, env_state: str) -> str:
    """检测各Agent方案之间的冲突。输入三个Agent的状态JSON，返回冲突列表JSON。"""
    try:
        acad = json.loads(academic_state) if academic_state else {}
    except json.JSONDecodeError:
        acad = {}
    try:
        logi = json.loads(logistics_state) if logistics_state else {}
    except json.JSONDecodeError:
        logi = {}
    try:
        env = json.loads(env_state) if env_state else {}
    except json.JSONDecodeError:
        env = {}

    rules = {
        "study_room_close": 22.5,
        "lights_out": 23.0,
        "max_daily_study": 12.0,
        "max_budget_ratio": 1.2,
    }
    conflicts = []

    def _fmt_time(h):
        hours = int(h)
        mins = int((h - hours) * 60)
        return f"{hours:02d}:{mins:02d}"

    # 1. 自习室关门
    if env and "options" in env and env["options"]:
        end = env["options"][0].get("end", 0)
        if end > rules["study_room_close"]:
            conflicts.append({
                "severity": "HIGH", "between": ["study_env"],
                "type": "studyroom_close",
                "description": f"自习结束时间 {end:.1f}（{_fmt_time(end)}）超过自习室关门时间 22.5（22:30）",
                "evidence": {"end": end, "limit": rules["study_room_close"]},
                "suggestion": "请将自习结束时间调整到 22:30 之前"
            })

    # 2. 宿舍熄灯
    if env and "options" in env and env["options"]:
        end = env["options"][0].get("end", 0)
        if end > rules["lights_out"]:
            conflicts.append({
                "severity": "HIGH", "between": ["study_env"],
                "type": "lights_out",
                "description": f"自习结束时间 {end:.1f}（{_fmt_time(end)}）超过宿舍熄灯时间 23.0（23:00）",
                "evidence": {"end": end, "limit": rules["lights_out"]},
                "suggestion": "请确保在 23:00 前回到宿舍"
            })

    # 3. 每日学习时长超限
    acad_hours = 0
    if acad and "options" in acad and acad["options"]:
        acad_hours = acad["options"][0].get("daily_hours", 0)
    env_hours = 0
    if env and "options" in env and env["options"]:
        opt = env["options"][0]
        env_hours = opt.get("end", 0) - opt.get("start", 0)
    total_hours = acad_hours + env_hours
    if total_hours > rules["max_daily_study"]:
        conflicts.append({
            "severity": "HIGH", "between": ["academic", "study_env"],
            "type": "time_overflow",
            "description": f"学业 {acad_hours:.1f}h + 自习 {env_hours:.1f}h = {total_hours:.1f}h，超过上限 {rules['max_daily_study']}h",
            "evidence": {"acad_hours": acad_hours, "env_hours": env_hours, "total": total_hours, "limit": rules["max_daily_study"]},
            "suggestion": f"请将每日总学习时间控制在 {rules['max_daily_study']}h 以内"
        })

    # 4. 预算超支
    if logi:
        budget = logi.get("monthly_budget", 0)
        spent = logi.get("total_spent", 0)
        if budget > 0 and spent > budget * rules["max_budget_ratio"]:
            over_pct = (spent / budget - 1) * 100
            conflicts.append({
                "severity": "MID", "between": ["logistics"],
                "type": "budget_overrun",
                "description": f"已消费 {spent:.0f}元 超出预算 {budget:.0f}元（超支 {over_pct:.0f}%）",
                "evidence": {"spent": spent, "budget": budget, "ratio": spent / budget},
                "suggestion": f"请控制消费在预算 {budget:.0f}元 以内"
            })

    # 5. 挂科风险
    if acad:
        risk = acad.get("risk_score", 0)
        weak = acad.get("weak_subjects", [])
        if risk >= 2:
            conflicts.append({
                "severity": "MID", "between": ["academic"],
                "type": "low_gpa_risk",
                "description": f"当前有 {risk} 门挂科（{', '.join(weak)}），存在学业预警风险",
                "evidence": {"risk_score": risk, "weak_subjects": weak},
                "suggestion": "建议优先安排挂科科目的补习和复习时间"
            })

    # 6. 自习时长过短
    if env_hours > 0 and env_hours < 1.0:
        conflicts.append({
            "severity": "LOW", "between": ["study_env"],
            "type": "too_short_study",
            "description": f"自习时长仅 {env_hours:.1f}h，可能不足",
            "evidence": {"env_hours": env_hours},
            "suggestion": "建议自习时长至少 1.5 小时以上"
        })

    return json.dumps(conflicts, ensure_ascii=False)


# ===================== 参数解析工具（1个） =====================

@tool
def parse_planning_params(user_request: str) -> str:
    """从用户的自然语言请求中提取结构化规划参数。返回JSON格式的参数。"""
    from .llm import llm as _llm
    prompt = f"""从用户请求中提取结构化参数，返回JSON（不要输出其他内容）：

字段说明：
- budget: 月度预算（数字，默认1000）
- daily_hours: 每日学习小时数（数字，默认4）
- want_env: 是否需要好的自习环境（布尔值，默认true）
- care_policy: 是否关注校规合规（布尔值，默认true）
- intensity: 学习强度（"low"/"normal"/"high"，默认"normal"）
- subjects: 重点关注的科目（字符串数组，默认[]）

用户请求：{user_request}

请直接输出JSON，例如：
{{"budget": 1000, "daily_hours": 4, "want_env": true, "care_policy": true, "intensity": "normal", "subjects": []}}"""
    return _llm(prompt)


# ===================== 冲突修订工具（3个） =====================

@tool
def revise_study_plan(current_plan: str, conflict_type: str, conflict_desc: str) -> str:
    """根据冲突信息修订学业规划方案。输入当前方案和冲突描述，输出修订后的分点计划。"""
    from .llm import llm as _llm
    prompt = f"""你是学业规划Agent。在多智能体协商中发现了以下冲突：

冲突类型：{conflict_type}
问题描述：{conflict_desc}

你当前的学习计划：
{current_plan}

请根据冲突信息修订你的计划。要求：
1. 解决上述冲突
2. 保持学业效果最大化
3. 输出修订后的简洁分点计划"""
    return _llm(prompt)


@tool
def revise_budget_plan(current_plan: str, conflict_type: str, conflict_desc: str) -> str:
    """根据冲突信息修订消费预算方案。输入当前方案和冲突描述，输出修订后的分点方案。"""
    from .llm import llm as _llm
    prompt = f"""你是后勤消费Agent。在多智能体协商中发现了以下冲突：

冲突类型：{conflict_type}
问题描述：{conflict_desc}

你当前的预算方案：
{current_plan}

请根据冲突信息修订你的方案。要求：
1. 解决上述冲突
2. 给出具体的省钱策略
3. 输出修订后的简洁分点方案"""
    return _llm(prompt)


@tool
def revise_study_room(current_plan: str, conflict_type: str, conflict_desc: str) -> str:
    """根据冲突信息修订自习方案。输入当前方案和冲突描述，输出修订后的分点推荐。"""
    from .llm import llm as _llm
    prompt = f"""你是自习环境Agent。在多智能体协商中发现了以下冲突：

冲突类型：{conflict_type}
问题描述：{conflict_desc}

你当前的自习推荐：
{current_plan}

请根据冲突信息修订你的推荐方案。要求：
1. 解决上述冲突
2. 结合IoT数据给出最优替代方案
3. 输出修订后的简洁分点推荐"""
    return _llm(prompt)


# ===================== 工具列表导出 =====================

def get_data_query_tools():
    """获取数据查询类工具列表"""
    return [query_grades, query_consumption, query_iot_data, search_policy]

def get_academic_tools():
    """获取学业规划工具列表"""
    return [query_grades, analyze_study_plan, revise_study_plan]

def get_logistics_tools():
    """获取后勤消费工具列表"""
    return [query_consumption, analyze_budget_plan, revise_budget_plan]

def get_study_env_tools():
    """获取自习环境工具列表"""
    return [query_iot_data, analyze_study_room, revise_study_room]

def get_policy_tools():
    """获取政策合规工具列表"""
    return [get_policy_constraints, search_policy]

def get_orchestrator_tools():
    """获取编排层工具列表（Supervisor/MasterAgent 使用）"""
    return [parse_planning_params, detect_conflicts, search_policy,
            query_grades, query_consumption, query_iot_data]

def get_all_tools():
    """获取全部工具列表"""
    return [
        query_grades, query_consumption, query_iot_data, search_policy,
        analyze_study_plan, analyze_budget_plan, analyze_study_room,
        get_policy_constraints, detect_conflicts,
        parse_planning_params,
        revise_study_plan, revise_budget_plan, revise_study_room,
    ]
