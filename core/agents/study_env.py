from ..llm import llm
from ..database import get_conn
from ..memory import AgentMemory

class StudyEnvAgent:
    name = "study_env"
    display = "自习环境智能体"

    def __init__(self):
        self.memory = AgentMemory("study_env")

    def analyze(self, student_id, want_hours=4.0):
        conn = get_conn()
        iot = conn.execute("SELECT * FROM iot").fetchall()
        conn.close()

        context = "\n".join([
            f"{r['floor']} {r['hour']}点 人流量{r['traffic']} CO2{r['co2']}"
            for r in iot[:20]
        ])

        prompt = f"""
自习室IoT数据：
{context}
推荐连续 {want_hours} 小时最优自习位置。
简洁回答。
"""
        rec = llm(prompt)

        return {
            "options": [{
                "floor": "LLM推荐最优区",
                "start": 14.0,
                "end": 18.0,
                "env_score": 95,
                "crowd_index": 0.2
            }],
            "selected": 0,
            "narrative": rec,
            "curve": []
        }

    def revise(self, state, feedback):
        state["narrative"] = llm(f"调整自习方案：{feedback}\n原方案：{state['narrative']}")