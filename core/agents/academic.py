from ..llm import llm
from ..database import get_conn
from ..memory import AgentMemory

class AcademicAgent:
    name = "academic"
    display = "学业规划智能体"
    priority = 4  # 优先级最高（学业>消费>环境>政策）

    def __init__(self):
        self.memory = AgentMemory("academic")

    def analyze(self, student_id, daily_hours=4.0):
        """分析成绩 → 生成学习计划"""
        conn = get_conn()
        cursor = conn.cursor(dictionary=True)

        # 从 grades 表获取该学生所有科目成绩
        cursor.execute("""
            SELECT subject, score, failed
            FROM grades
            WHERE student_id = %s
        """, (student_id,))
        grades_list = cursor.fetchall()

        # 科目均分 & 挂科统计
        subject_map = {}
        for g in grades_list:
            sub = g["subject"]
            if sub not in subject_map:
                subject_map[sub] = {"scores": [], "failed": 0}
            subject_map[sub]["scores"].append(g["score"])
            if g["failed"] == 1:
                subject_map[sub]["failed"] = 1

        grades = []
        for sub, item in subject_map.items():
            avg = sum(item["scores"]) / len(item["scores"])
            grades.append({
                "subject": sub,
                "avg_score": avg,
                "has_fail": item["failed"]
            })

        conn.close()

        # 构建大模型上下文
        context_lines = [
            f"科目：{g['subject']}，均分：{g['avg_score']:.1f}，是否挂科：{'是' if g['has_fail'] else '否'}"
            for g in grades
        ]
        context = "\n".join(context_lines)

        prompt = f"""
你是专业学业规划师。
学生成绩如下：
{context}

要求每日学习 {daily_hours} 小时。
请生成一份**可执行、简洁、分点**的学习提升计划，重点优先提升挂科/低分科目。
"""
        plan = llm(prompt)

        # 风险分 = 挂科数量
        risk_score = sum(1 for g in grades if g["has_fail"])
        weak_subjects = [g["subject"] for g in grades if g["has_fail"]]

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

    def revise(self, state, feedback):
        """根据反馈修订学习计划"""
        prompt = f"""
请根据用户反馈优化学习计划：
用户反馈：{feedback}
原计划：{state['narrative']}
输出优化后的简洁分点版本。
"""
        state["narrative"] = llm(prompt)
        return state