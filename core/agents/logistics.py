from ..llm import llm
from ..database import get_conn
from ..memory import AgentMemory

class LogisticsAgent:
    name = "logistics"
    display = "校园后勤智能体"
    priority = 3

    def __init__(self):
        self.memory = AgentMemory("logistics")

    def analyze(self, student_id, monthly_budget=1200.0):
        """分析消费 → 生成预算方案"""
        conn = get_conn()
        cursor = conn.cursor(dictionary=True)

        # 从 consumption 按类别统计总消费
        cursor.execute("""
            SELECT category, SUM(amount) AS total, COUNT(*) AS cnt
            FROM consumption
            WHERE student_id = %s
            GROUP BY category
        """, (student_id,))
        expenses = cursor.fetchall()
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

        conn.close()

        return {
            "agent": self.name,
            "monthly_budget": monthly_budget,
            "total_spent": total_spent,
            "daily_meal_cap": daily_meal,
            "saving_plan": advice,
            "expenses": expenses,
            "utility_tips": ["节约用水用电","错峰消费"]
        }

    def revise(self, state, feedback):
        prompt = f"""
根据反馈优化预算方案：
意见：{feedback}
原方案：{state['saving_plan']}
输出优化版。
"""
        state["saving_plan"] = llm(prompt)
        return state