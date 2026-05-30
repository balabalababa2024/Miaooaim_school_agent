"""
校园政策咨询 Agent（辅助 RAG 模块）
==================================
依托 static_rule 静态政策向量库检索校规 → 提取硬性约束（自习室关闭时间、熄灯时间、
奖学金成绩门槛）下发给其他 Agent → 对所有规划方案做合规校验，过滤违规方案。
"""
from ..database import get_static_rule_store, seed_static_rules
from ..memory import GlobalMemory


class PolicyAgent:
    name = "policy"
    display = "校园政策咨询 Agent"

    def __init__(self):
        seed_static_rules()
        self.store = get_static_rule_store()
        self.g = GlobalMemory.instance()

    def constraints(self):
        """从全局共享记忆下发硬性约束规则。"""
        return {
            "study_room_close": self.g.get("study_room_open")[1],  # 22.5
            "lights_out": self.g.get("dorm_lights_out"),           # 23.0
            "scholarship_gpa": self.g.get("scholarship_gpa_threshold"),
            "utility_cap": self.g.get("recommended_utility_cap"),
        }

    def analyze(self):
        cons = self.constraints()
        return {
            "agent": self.name, "display": self.display,
            "constraints": cons,
            "narrative": f"已下发硬性约束：自习室 {_fmt(cons['study_room_close'])} 关闭、"
                         f"宿舍 {_fmt(cons['lights_out'])} 熄灯、奖学金成绩门槛 {cons['scholarship_gpa']} 分。",
        }

    def validate(self, state):
        """合规校验：返回违规清单（供 Supervisor 过滤/驱动修改）。"""
        cons = state["policy"]["constraints"]
        env = state["study_env"]["options"][state["study_env"]["selected"]]
        violations = []
        if env["end"] > cons["study_room_close"] + 0.01:
            violations.append(f"自习方案结束 {_fmt(env['end'])} 超出自习室关闭时间。")
        return violations

    def ask(self, question, top_k=3):
        """政策问答（RAG 检索）。"""
        hits = self.store.search(question, top_k=top_k, threshold=0.05)
        if not hits:
            return {"answer": "未在政策库中检索到相关条款，请咨询学院辅导员。", "sources": []}
        answer = hits[0]["meta"].get("content", hits[0]["text"])
        return {
            "answer": answer,
            "sources": [{"section": h["meta"].get("section", ""),
                         "content": h["meta"].get("content", h["text"]),
                         "score": h["score"]} for h in hits],
        }


def _fmt(h):
    hh = int(h)
    mm = int(round((h - hh) * 60))
    return f"{hh:02d}:{mm:02d}"
