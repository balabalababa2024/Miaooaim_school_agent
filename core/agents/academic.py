import json
import logging
from ..llm import create_agent, run_agent, llm
from ..tools import get_academic_tools
from ..memory import AgentMemory

logger = logging.getLogger(__name__)

ANALYZE_SYSTEM_PROMPT = """你是专业学业规划师。
你可以使用以下工具：
- query_grades: 查询学生的真实成绩数据
- analyze_study_plan: 基于成绩数据生成学习提升计划

核心原则：学生的原始需求是最高优先级，数据仅作参考。
请先调用 query_grades 获取学生真实成绩，然后调用 analyze_study_plan 生成计划。
最后输出简洁的分点学习计划。"""

REVISE_SYSTEM_PROMPT = """你是学业规划Agent，负责在多智能体协商中修订学习计划。
你可以使用以下工具：
- revise_study_plan: 根据冲突信息修订学业规划方案

请调用 revise_study_plan 工具，传入当前方案和冲突信息，获取修订后的计划。"""


class AcademicAgent:
    name = "academic"
    display = "学业规划智能体"
    priority = 4

    def __init__(self):
        self.memory = AgentMemory("academic")

    def analyze(self, student_id, daily_hours=4.0, user_request=""):
        """通过 Tool Calling 分析成绩并生成学习计划。user_request 为学生原始需求（最高优先级）。"""
        tools = get_academic_tools()
        executor = create_agent(tools, ANALYZE_SYSTEM_PROMPT)

        request_hint = f"\n\n【学生原始需求（最高优先级，必须严格遵守）】\n{user_request}" if user_request else ""
        user_input = f"请查询学生 {student_id} 的成绩，并生成每日学习 {daily_hours} 小时的提升计划。{request_hint}"

        try:
            plan = run_agent(executor, user_input)
        except Exception as e:
            logger.warning(f"AcademicAgent tool calling 失败，回退: {e}")
            plan = llm(f"学生成绩：{student_id}，每日学习{daily_hours}小时，生成学习计划")

        # 为了保留结构化数据（risk_score等），仍需查询原始成绩
        from ..tools import query_grades
        grades_raw = query_grades.invoke({"student_id": student_id})

        # 解析成绩计算风险分
        subject_map = {}
        for line in grades_raw.split("\n"):
            if line.startswith("- ") and "：" in line:
                parts = line[2:].split("：")
                if len(parts) >= 2:
                    sub = parts[0]
                    score_str = parts[1].replace("分", "").replace(" [挂科]", "").strip()
                    try:
                        score = float(score_str)
                    except ValueError:
                        score = 0
                    has_fail = "[挂科]" in line
                    if sub not in subject_map:
                        subject_map[sub] = {"scores": [], "failed": False}
                    subject_map[sub]["scores"].append(score)
                    if has_fail:
                        subject_map[sub]["failed"] = True

        grades = []
        for sub, item in subject_map.items():
            avg = sum(item["scores"]) / len(item["scores"]) if item["scores"] else 0
            grades.append({"subject": sub, "avg_score": avg, "has_fail": item["failed"]})

        risk_score = sum(1 for g in grades if g["has_fail"])
        weak_subjects = [g["subject"] for g in grades if g["has_fail"]]

        self.memory.add_interaction("system", f"分析完成：{len(grades)}个科目，风险分{risk_score}")

        return {
            "agent": self.name,
            "options": [{
                "name": "智能学习方案",
                "daily_hours": daily_hours,
                "blocks": [{"subject": g["subject"], "ratio": 0.25} for g in grades]
            }],
            "selected": 0,
            "risk_score": risk_score,
            "weak_subjects": weak_subjects,
            "narrative": plan,
            "raw_data": grades
        }

    def revise(self, state, conflict):
        """通过 Tool Calling 修订学习计划"""
        tools = get_academic_tools()
        executor = create_agent(tools, REVISE_SYSTEM_PROMPT)

        conflict_type = conflict.get("type", "")
        description = conflict.get("description", "")
        suggestion = conflict.get("suggestion", "")

        user_input = (
            f"当前学习计划：\n{state.get('narrative', '')}\n\n"
            f"冲突类型：{conflict_type}\n"
            f"问题描述：{description}\n"
            f"调整建议：{suggestion}\n\n"
            f"请修订计划。"
        )

        try:
            revised = run_agent(executor, user_input)
        except Exception as e:
            logger.warning(f"AcademicAgent revise tool calling 失败，回退: {e}")
            revised = llm(f"冲突：{conflict_type}，{description}。当前计划：{state.get('narrative', '')}。请修订。")

        state["narrative"] = revised
        self.memory.add_interaction("system", f"修订计划，冲突类型：{conflict_type}")
        return state
