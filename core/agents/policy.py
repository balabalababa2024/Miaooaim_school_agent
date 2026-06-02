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
            "study_room_close": 22.5,       # 自习室关门时间
            "lights_out": 23.0,             # 宿舍熄灯时间
            "scholarship_gpa": 85,          # 奖学金GPA门槛
            "monthly_utility_cap": 150,     # 月度水电费上限
            "max_daily_study": 12.0,        # 每日学习上限
            "min_daily_study": 1.0,         # 每日学习下限
            "max_budget_ratio": 1.2,        # 预算超支容忍比例
        }

    def analyze(self):
        return {
            "agent": self.name,
            "constraints": self.get_constraints(),
            "narrative": "已加载校园政策与硬约束：自习室22:30关门、宿舍23:00熄灯、"
                         "奖学金GPA门槛85分、月度水电费上限150元。"
        }

    def validate(self, academic_state, logistics_state, env_state):
        """
        增强版冲突检测，返回结构化冲突列表。
        每个冲突包含: severity, between, type, description, evidence, suggestion
        """
        rules = self.get_constraints()
        conflicts = []

        # --- 1. 自习室关门检查 ---
        if env_state and "options" in env_state and env_state["options"]:
            end = env_state["options"][0].get("end", 0)
            if end > rules["study_room_close"]:
                conflicts.append({
                    "severity": "HIGH",
                    "between": ["study_env"],
                    "type": "studyroom_close",
                    "description": f"自习结束时间 {end:.1f}（{self._fmt_time(end)}）"
                                   f"超过自习室关门时间 {rules['study_room_close']}（22:30）",
                    "evidence": {"end": end, "limit": rules["study_room_close"]},
                    "suggestion": f"请将自习结束时间调整到 {rules['study_room_close']}（22:30）之前"
                })

        # --- 2. 宿舍熄灯检查 ---
        if env_state and "options" in env_state and env_state["options"]:
            end = env_state["options"][0].get("end", 0)
            if end > rules["lights_out"]:
                conflicts.append({
                    "severity": "HIGH",
                    "between": ["study_env"],
                    "type": "lights_out",
                    "description": f"自习结束时间 {end:.1f}（{self._fmt_time(end)}）"
                                   f"超过宿舍熄灯时间 {rules['lights_out']}（23:00）",
                    "evidence": {"end": end, "limit": rules["lights_out"]},
                    "suggestion": f"请确保在 {rules['lights_out']}（23:00）前回到宿舍"
                })

        # --- 3. 每日学习时长超限 ---
        acad_hours = 0
        if academic_state and "options" in academic_state and academic_state["options"]:
            acad_hours = academic_state["options"][0].get("daily_hours", 0)

        env_hours = 0
        if env_state and "options" in env_state and env_state["options"]:
            opt = env_state["options"][0]
            env_hours = opt.get("end", 0) - opt.get("start", 0)

        total_hours = acad_hours + env_hours
        if total_hours > rules["max_daily_study"]:
            conflicts.append({
                "severity": "HIGH",
                "between": ["academic", "study_env"],
                "type": "time_overflow",
                "description": f"学业学习 {acad_hours:.1f}h + 自习 {env_hours:.1f}h = "
                               f"总计 {total_hours:.1f}h，超过每日上限 {rules['max_daily_study']}h",
                "evidence": {"acad_hours": acad_hours, "env_hours": env_hours,
                             "total": total_hours, "limit": rules["max_daily_study"]},
                "suggestion": f"请将每日总学习时间控制在 {rules['max_daily_study']}h 以内"
            })

        # --- 4. 预算超支检查 ---
        if logistics_state:
            budget = logistics_state.get("monthly_budget", 0)
            spent = logistics_state.get("total_spent", 0)
            if budget > 0 and spent > budget * rules["max_budget_ratio"]:
                over_pct = (spent / budget - 1) * 100
                conflicts.append({
                    "severity": "MID",
                    "between": ["logistics"],
                    "type": "budget_overrun",
                    "description": f"已消费 {spent:.0f}元 超出预算 {budget:.0f}元 "
                                   f"（超支 {over_pct:.0f}%）",
                    "evidence": {"spent": spent, "budget": budget,
                                 "ratio": spent / budget},
                    "suggestion": f"请控制消费在预算 {budget:.0f}元 以内"
                })

        # --- 5. 挂科风险预警 ---
        if academic_state:
            risk = academic_state.get("risk_score", 0)
            weak = academic_state.get("weak_subjects", [])
            if risk >= 2:
                conflicts.append({
                    "severity": "MID",
                    "between": ["academic"],
                    "type": "low_gpa_risk",
                    "description": f"当前有 {risk} 门挂科（{', '.join(weak)}），"
                                   f"存在学业预警风险",
                    "evidence": {"risk_score": risk, "weak_subjects": weak},
                    "suggestion": "建议优先安排挂科科目的补习和复习时间"
                })

        # --- 6. 自习时长合理性 ---
        if env_hours > 0 and env_hours < 1.0:
            conflicts.append({
                "severity": "LOW",
                "between": ["study_env"],
                "type": "too_short_study",
                "description": f"自习时长仅 {env_hours:.1f}h，可能不足以完成学习任务",
                "evidence": {"env_hours": env_hours},
                "suggestion": "建议自习时长至少 1.5 小时以上"
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

    @staticmethod
    def _fmt_time(hour_float):
        """将小数时间转为 HH:MM 格式，如 22.5 → '22:30'"""
        h = int(hour_float)
        m = int((hour_float - h) * 60)
        return f"{h:02d}:{m:02d}"
