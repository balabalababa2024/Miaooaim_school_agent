import json
import logging
from ..llm import create_agent, run_agent, llm
from ..tools import get_study_env_tools
from ..memory import AgentMemory

logger = logging.getLogger(__name__)

ANALYZE_SYSTEM_PROMPT = """你是自习室推荐官。
你可以使用以下工具：
- query_iot_data: 查询自习室IoT传感器数据（人流量、CO2、温度）
- analyze_study_room: 基于IoT数据推荐最优楼层和时间段

请先调用 query_iot_data 获取真实IoT数据，然后调用 analyze_study_room 生成推荐。
最后输出简洁的分点自习推荐。"""

REVISE_SYSTEM_PROMPT = """你是自习环境Agent，负责在多智能体协商中修订自习方案。
你可以使用以下工具：
- revise_study_room: 根据冲突信息修订自习方案

请调用 revise_study_room 工具，传入当前方案和冲突信息，获取修订后的推荐。"""


class StudyEnvAgent:
    name = "study_env"
    display = "自习环境智能体"
    priority = 2

    def __init__(self):
        self.memory = AgentMemory("study_env")

    def analyze(self, student_id, want_hours=4.0):
        """通过 Tool Calling 分析IoT数据并推荐自习方案"""
        tools = get_study_env_tools()
        executor = create_agent(tools, ANALYZE_SYSTEM_PROMPT)

        user_input = f"请查询自习室IoT数据，并为需要连续自习 {want_hours} 小时的学生推荐最优楼层和时间段。"

        try:
            recommendation = run_agent(executor, user_input)
        except Exception as e:
            logger.warning(f"StudyEnvAgent tool calling 失败，回退: {e}")
            recommendation = llm(f"自习室IoT数据，需要自习{want_hours}小时，推荐最优楼层和时段")

        # 查询原始IoT数据用于结构化返回
        from ..tools import query_iot_data
        iot_raw = query_iot_data.invoke({})

        # 简单解析 IoT 数据计算环境评分
        best_floor = "3"
        best_score = 0
        for line in iot_raw.split("\n"):
            if "楼" in line and "人流" in line:
                try:
                    parts = line.split("：")[1] if "：" in line else ""
                    traffic_str = parts.split("人流")[1].split("，")[0].strip() if "人流" in parts else "50"
                    co2_str = parts.split("CO2 ")[1].split("p")[0].strip() if "CO2 " in parts else "450"
                    traffic = float(traffic_str)
                    co2 = float(co2_str)
                    env = 100 - (traffic * 0.5 + co2 * 0.3)
                    floor = line.split("楼")[0].replace("-", "").strip()
                    if env > best_score:
                        best_score = env
                        best_floor = floor
                except (ValueError, IndexError):
                    pass

        self.memory.add_interaction("system", f"推荐{best_floor}楼，环境评分{best_score:.0f}")

        return {
            "agent": self.name,
            "options": [{
                "floor": f"{best_floor}楼",
                "start": 14.0,
                "end": 14.0 + want_hours,
                "env_score": round(best_score, 1),
                "crowd_index": 0.3
            }],
            "selected": 0,
            "narrative": recommendation,
            "raw_iot": []
        }

    def revise(self, state, conflict):
        """通过 Tool Calling 修订自习方案"""
        tools = get_study_env_tools()
        executor = create_agent(tools, REVISE_SYSTEM_PROMPT)

        conflict_type = conflict.get("type", "")
        description = conflict.get("description", "")
        suggestion = conflict.get("suggestion", "")

        # 确定性调整（保留原有逻辑）
        if conflict_type == "studyroom_close":
            if "options" in state and state["options"]:
                state["options"][0]["end"] = 22.0
        elif conflict_type == "lights_out":
            if "options" in state and state["options"]:
                state["options"][0]["end"] = 22.5
        elif conflict_type == "time_overflow":
            evidence = conflict.get("evidence", {})
            limit = evidence.get("limit", 12.0)
            acad_hours = evidence.get("acad_hours", 0)
            new_end_hours = max(limit - acad_hours, 2.0)
            if "options" in state and state["options"]:
                start = state["options"][0].get("start", 14.0)
                state["options"][0]["end"] = start + new_end_hours
        elif conflict_type == "too_short_study":
            if "options" in state and state["options"]:
                start = state["options"][0].get("start", 14.0)
                state["options"][0]["end"] = start + 2.0

        user_input = (
            f"当前自习推荐：\n{state.get('narrative', '')}\n\n"
            f"冲突类型：{conflict_type}\n"
            f"问题描述：{description}\n"
            f"调整建议：{suggestion}\n\n"
            f"请修订推荐方案。"
        )

        try:
            revised = run_agent(executor, user_input)
        except Exception as e:
            logger.warning(f"StudyEnvAgent revise tool calling 失败，回退: {e}")
            revised = llm(f"冲突：{conflict_type}，{description}。当前推荐：{state.get('narrative', '')}。请修订。")

        state["narrative"] = revised
        self.memory.add_interaction("system", f"修订自习方案，冲突类型：{conflict_type}")
        return state
