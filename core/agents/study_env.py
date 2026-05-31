from ..llm import llm
from ..database import get_conn
from ..memory import AgentMemory

class StudyEnvAgent:
    name = "study_env"
    display = "自习环境智能体"
    priority = 2

    def __init__(self):
        self.memory = AgentMemory("study_env")

    def analyze(self, student_id, want_hours=4.0):
        """IoT数据分析 → 自习推荐"""
        conn = get_conn()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM iot ORDER BY floor, hour")
        iot_records = cursor.fetchall()
        conn.close()

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

    def revise(self, state, feedback):
        prompt = f"""
根据需求调整自习推荐：
反馈：{feedback}
原推荐：{state['narrative']}
输出更合适的方案。
"""
        state["narrative"] = llm(prompt)
        return state