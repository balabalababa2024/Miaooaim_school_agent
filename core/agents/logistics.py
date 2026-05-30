from ..llm import llm
from ..database import get_conn
from ..memory import AgentMemory

class LogisticsAgent:
    name = "logistics"
    display = "校园后勤智能体"

    def __init__(self):
        self.memory = AgentMemory("logistics")

    def analyze(self, student_id, monthly_budget=1000.0):
        conn = get_conn()
        expenses = conn.execute("""
            SELECT category, SUM(amount) as total
            FROM consumption WHERE student_id=? GROUP BY category
        """, (student_id,)).fetchall()
        conn.close()

        context = "\n".join([f"{e['category']}：{e['total']}元" for e in expenses])

        prompt = f"""
学生月度消费：
{context}
总预算 {monthly_budget} 元。
生成合理省钱建议，简洁。
"""
        advice = llm(prompt)

        return {
            "monthly_budget": monthly_budget,
            "daily_meal_cap": round(monthly_budget / 30, 1),
            "saving_plan": advice,
            "utility_tips": ["节约水电"],
            "meal_total": 800,
            "utility_total": 120
        }

    def revise(self, state, feedback):
        state["saving_plan"] = llm(f"优化预算方案：{feedback}\n原方案：{state['saving_plan']}")