from ..llm import llm
from ..database import get_conn
from ..memory import AgentMemory

class AcademicAgent:
    name = "academic"
    display = "学业规划智能体"

    def __init__(self):
        self.memory = AgentMemory("academic")

    def analyze(self, student_id, daily_hours=4.0):
        conn = get_conn()
        grades = conn.execute("""
            SELECT subject, AVG(score) as avg_score, MAX(failed) as has_fail
            FROM grades WHERE student_id=? GROUP BY subject
        """, (student_id,)).fetchall()
        conn.close()

        context = "\n".join([
            f"{g['subject']}：均分{g['avg_score']:.1f}，挂科：{g['has_fail']}"
            for g in grades
        ])

        prompt = f"""
你是学业规划师。
学生成绩：
{context}
要求每日学习 {daily_hours} 小时。
生成一份可执行的学习计划，简洁，分点。
"""
        plan = llm(prompt)

        return {
            "options": [{
                "name": "LLM智能方案",
                "daily_hours": daily_hours,
                "blocks": [{"subject": "综合", "ratio": 1.0}]
            }],
            "selected": 0,
            "risk_score": sum(1 for g in grades if g['has_fail']),
            "weak_subjects": [g['subject'] for g in grades if g['has_fail']],
            "narrative": plan
        }

    def revise(self, state, feedback):
        state["narrative"] = llm(f"优化学习计划：{feedback}\n原计划：{state['narrative']}")