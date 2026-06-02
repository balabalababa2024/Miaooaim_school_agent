from ..llm import llm
from ..langchain_agent import query_iot_from_db
from ..memory import AgentMemory

class StudyEnvAgent:
    name = "study_env"
    display = "自习环境智能体"
    priority = 2

    def __init__(self):
        self.memory = AgentMemory("study_env")

    def analyze(self, student_id, want_hours=4.0):
        """IoT数据分析 → 自习推荐"""
        # 使用统一的数据查询函数
        iot_records = query_iot_from_db()

        context = "\n".join([
            f"{r['floor']}楼 {r['hour']}点 | 人流量：{r['traffic']} | CO2：{r['co2']} | 温度：{r['temp']}"
            for r in iot_records[:20]
        ])

        prompt = f"""
你是自习室推荐官。
自习室IoT实时数据：
{context}

学生需要连续自习 {want_hours} 小时。
请推荐**最优楼层、最佳时间段**，简洁分点。
"""
        recommendation = llm(prompt)

        # 环境评分：人流量低、CO2低 → 高分
        best = None
        max_env = 0
        for r in iot_records:
            env = 100 - (r["traffic"] * 0.5 + r["co2"] * 0.3)
            if env > max_env:
                max_env = env
                best = r

        # 记忆：保存推荐结果
        self.memory.add_interaction("system", f"推荐{best['floor'] if best else '?'}楼，环境评分{max_env:.0f}")

        return {
            "agent": self.name,
            "options": [{
                "floor": f"{best['floor']}楼" if best else "3楼",
                "start": 14.0,
                "end": 14.0 + want_hours,
                "env_score": round(max_env, 1),
                "crowd_index": round(best["traffic"] / 100, 2) if best else 0.3
            }],
            "selected": 0,
            "narrative": recommendation,
            "raw_iot": iot_records[:10]
        }

    def revise(self, state, conflict):
        """根据结构化冲突信息修订自习方案"""
        conflict_type = conflict.get("type", "")
        suggestion = conflict.get("suggestion", "请自行调整")
        description = conflict.get("description", "")

        if conflict_type == "studyroom_close":
            if "options" in state and state["options"]:
                state["options"][0]["end"] = 22.0
            suggestion = "将自习结束时间调整到22:00，确保在自习室22:30关门前离开"

        elif conflict_type == "lights_out":
            if "options" in state and state["options"]:
                state["options"][0]["end"] = 22.5
            suggestion = "将自习结束时间调整到22:30，确保23:00熄灯前回到宿舍"

        elif conflict_type == "time_overflow":
            evidence = conflict.get("evidence", {})
            limit = evidence.get("limit", 12.0)
            acad_hours = evidence.get("acad_hours", 0)
            new_end_hours = max(limit - acad_hours, 2.0)
            if "options" in state and state["options"]:
                start = state["options"][0].get("start", 14.0)
                state["options"][0]["end"] = start + new_end_hours
            suggestion = f"将自习时长缩短到 {new_end_hours:.1f}h"

        elif conflict_type == "too_short_study":
            if "options" in state and state["options"]:
                start = state["options"][0].get("start", 14.0)
                state["options"][0]["end"] = start + 2.0
            suggestion = "将自习时长延长到至少2小时"

        prompt = f"""
你是自习环境Agent。在多智能体协商中发现了以下冲突：

冲突类型：{conflict_type}
问题描述：{description}
调整建议：{suggestion}

你当前的自习推荐：
{state.get('narrative', '')}

请根据冲突信息修订你的推荐方案。要求：
1. 解决上述冲突
2. 结合IoT数据给出最优替代方案
3. 输出修订后的简洁分点推荐
"""
        state["narrative"] = llm(prompt)
        self.memory.add_interaction("system", f"修订自习方案，冲突类型：{conflict_type}")
        return state
