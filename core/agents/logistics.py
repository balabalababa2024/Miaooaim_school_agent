import json
import logging
from ..llm import create_agent, run_agent, llm
from ..tools import get_logistics_tools
from ..memory import AgentMemory

logger = logging.getLogger(__name__)

ANALYZE_SYSTEM_PROMPT = """你是校园消费规划师。
你可以使用以下工具：
- query_consumption: 查询学生的真实消费数据
- analyze_budget_plan: 基于消费数据生成预算分配方案

请先调用 query_consumption 获取学生真实消费数据，然后调用 analyze_budget_plan 生成方案。
最后输出简洁的分点预算建议。"""

REVISE_SYSTEM_PROMPT = """你是后勤消费Agent，负责在多智能体协商中修订预算方案。
你可以使用以下工具：
- revise_budget_plan: 根据冲突信息修订消费预算方案

请调用 revise_budget_plan 工具，传入当前方案和冲突信息，获取修订后的方案。"""


class LogisticsAgent:
    name = "logistics"
    display = "校园后勤智能体"
    priority = 3

    def __init__(self):
        self.memory = AgentMemory("logistics")

    def analyze(self, student_id, monthly_budget=1200.0):
        """通过 Tool Calling 分析消费并生成预算方案"""
        tools = get_logistics_tools()
        executor = create_agent(tools, ANALYZE_SYSTEM_PROMPT)

        user_input = f"请查询学生 {student_id} 的消费数据，并生成月度预算 {monthly_budget} 元的分配方案。"

        try:
            advice = run_agent(executor, user_input)
        except Exception as e:
            logger.warning(f"LogisticsAgent tool calling 失败，回退: {e}")
            advice = llm(f"学生 {student_id}，预算{monthly_budget}元，生成消费建议")

        # 查询原始数据用于结构化返回
        from ..tools import query_consumption
        expenses_raw = query_consumption.invoke({"student_id": student_id})

        total_spent = 0
        for line in expenses_raw.split("\n"):
            if "合计：" in line:
                try:
                    total_spent = float(line.split("合计：")[1].replace("元", "").strip())
                except ValueError:
                    pass

        daily_meal = round(monthly_budget * 0.7 / 30, 1)
        self.memory.add_interaction("system", f"消费分析：总预算{monthly_budget}，已花{total_spent:.0f}，日均餐费上限{daily_meal}")

        return {
            "agent": self.name,
            "monthly_budget": monthly_budget,
            "total_spent": total_spent,
            "daily_meal_cap": daily_meal,
            "saving_plan": advice,
            "expenses": [],
            "utility_tips": ["节约用水用电", "错峰消费"]
        }

    def revise(self, state, conflict):
        """通过 Tool Calling 修订预算方案"""
        tools = get_logistics_tools()
        executor = create_agent(tools, REVISE_SYSTEM_PROMPT)

        conflict_type = conflict.get("type", "")
        description = conflict.get("description", "")
        suggestion = conflict.get("suggestion", "")

        # 预算超支时调整 daily_meal_cap
        if conflict_type == "budget_overrun":
            evidence = conflict.get("evidence", {})
            budget = evidence.get("budget", 1000)
            spent = evidence.get("spent", 0)
            remaining = max(budget - spent, 0)
            days_left = 15
            new_daily = round(remaining * 0.7 / days_left, 1) if days_left > 0 else 10
            state["daily_meal_cap"] = new_daily

        user_input = (
            f"当前预算方案：\n{state.get('saving_plan', '')}\n\n"
            f"冲突类型：{conflict_type}\n"
            f"问题描述：{description}\n"
            f"调整建议：{suggestion}\n\n"
            f"请修订方案。"
        )

        try:
            revised = run_agent(executor, user_input)
        except Exception as e:
            logger.warning(f"LogisticsAgent revise tool calling 失败，回退: {e}")
            revised = llm(f"冲突：{conflict_type}，{description}。当前方案：{state.get('saving_plan', '')}。请修订。")

        state["saving_plan"] = revised
        self.memory.add_interaction("system", f"修订预算，冲突类型：{conflict_type}")
        return state
