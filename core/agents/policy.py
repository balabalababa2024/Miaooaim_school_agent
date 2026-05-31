from ..llm import llm
from ..memory import GlobalMemory
from ..database import get_static_rule_store

class PolicyAgent:
    name = "policy"
    display = "政策合规智能体"
    priority = 1

    def __init__(self):
        self.g = GlobalMemory.instance()
        self.rule_store = get_static_rule_store()

    def get_constraints(self):
        return {
            "study_room_close": 22.5,
            "lights_out": 23.0,
            "scholarship_gpa": 85,
            "monthly_utility_cap": 150,
            "max_daily_study": 12.0,
            "min_daily_study": 1.0
        }

    def analyze(self):
        return {
            "agent": self.name,
            "constraints": self.get_constraints(),
            "narrative": "已加载校园政策与硬约束"
        }

    def validate(self, academic_state, logistics_state, env_state):
        rules = self.get_constraints()
        conflicts = []
        if env_state and "options" in env_state:
            end = env_state["options"][0]["end"]
            if end > rules["study_room_close"]:
                conflicts.append({
                    "agent": "study_env", "level": "HIGH",
                    "msg": f"自习结束时间 {end} 超过闭馆时间 22:30"
                })
        if academic_state:
            h = academic_state["options"][0]["daily_hours"]
            if h > rules["max_daily_study"]:
                conflicts.append({
                    "agent": "academic", "level": "MID",
                    "msg": f"学习时长 {h} 小时过长，建议≤12小时"
                })
        return conflicts

    def ask(self, question):
        hits = self.rule_store.search(question, top_k=3)
        if not hits:
            return {"answer": "未查询到相关校规"}
        context = "\n".join([h["text"] for h in hits])
        answer = llm(f"校规：{context}\n问题：{question}\n直接回答")
        return {
            "answer": answer,
            "sources": [h["text"] for h in hits]
        }