from ..llm import llm
from ..langchain_agent import query_consumption_from_db
from ..memory import AgentMemory

class LogisticsAgent:
    name = "logistics"
    display = "校园后勤智能体"
    priority = 3

    def __init__(self):
        self.memory = AgentMemory("logistics")

    def analyze(self, student_id, monthly_budget=1200.0):
        """分析消费 → 生成预算方案"""
        # 使用统一的数据查询函数
        expenses = query_consumption_from_db(student_id)
        total_spent = sum(e["total"] for e in expenses)

        context = "\n".join([f"{e['category']}：{e['total']:.1f}元" for e in expenses])

        prompt = f"""
你是校园消费规划师。
学生月度消费明细：
{context}
总预算：{monthly_budget} 元，已消费：{total_spent:.1f}元。

请给出**简洁、可执行**的省钱与预算分配建议，分点。
"""
        advice = llm(prompt)

        daily_meal = round(monthly_budget * 0.7 / 30, 1)

        # 记忆：保存分析结果
        self.memory.add_interaction("system", f"消费分析：总预算{monthly_budget}，已花{total_spent:.0f}，日均餐费上限{daily_meal}")

        return {
            "agent": self.name,
            "monthly_budget": monthly_budget,
            "total_spent": total_spent,
            "daily_meal_cap": daily_meal,
            "saving_plan": advice,
            "expenses": expenses,
            "utility_tips": ["节约用水用电", "错峰消费"]
        }

    def revise(self, state, conflict):
        """根据结构化冲突信息修订预算方案"""
        conflict_type = conflict.get("type", "")
        suggestion = conflict.get("suggestion", "请自行调整")
        description = conflict.get("description", "")

        if conflict_type == "budget_overrun":
            evidence = conflict.get("evidence", {})
            budget = evidence.get("budget", 1000)
            spent = evidence.get("spent", 0)
            remaining = max(budget - spent, 0)
            days_left = 15
            new_daily = round(remaining * 0.7 / days_left, 1) if days_left > 0 else 10
            state["daily_meal_cap"] = new_daily
            suggestion = f"已超支，剩余 {remaining:.0f}元 需精打细算，日均餐费降至 {new_daily}元"

        prompt = f"""
你是后勤消费Agent。在多智能体协商中发现了以下冲突：

冲突类型：{conflict_type}
问题描述：{description}
调整建议：{suggestion}

你当前的预算方案：
{state.get('saving_plan', '')}

请根据冲突信息修订你的方案。要求：
1. 解决上述冲突
2. 给出具体的省钱策略
3. 输出修订后的简洁分点方案
"""
        state["saving_plan"] = llm(prompt)
        self.memory.add_interaction("system", f"修订预算，冲突类型：{conflict_type}")
        return state
