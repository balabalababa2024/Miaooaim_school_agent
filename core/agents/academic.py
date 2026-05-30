"""
学业风险分析 Agent
==================
读取学生历史成绩时序 → 计算学业综合风险分、标记薄弱科目 →
生成「保守型 / 冲刺型」两套带时间约束的复习方案，参与全局博弈。
"""
import statistics
from ..database import get_conn
from ..memory import AgentMemory


class AcademicAgent:
    name = "academic"
    display = "学业风险分析 Agent"

    def __init__(self):
        self.memory = AgentMemory("academic")  # 私有记忆：历史成绩波动

    def analyze(self, student_id, daily_hours_budget=6.0):
        conn = get_conn()
        rows = [dict(r) for r in conn.execute(
            "SELECT subject, score, attendance, failed, difficulty, credit "
            "FROM grades WHERE student_id=?", (student_id,)).fetchall()]
        conn.close()

        subjects = {}
        for r in rows:
            subjects.setdefault(r["subject"], []).append(r)

        weak, subj_risk = [], {}
        for subj, recs in subjects.items():
            scores = [x["score"] for x in recs]
            avg = statistics.mean(scores)
            vol = statistics.pstdev(scores)
            fails = sum(x["failed"] for x in recs)
            diff = recs[0]["difficulty"]
            attend = statistics.mean(x["attendance"] for x in recs)
            # 风险分：低分 + 高波动 + 挂科 + 高难度 + 低出勤，归一到 0-100
            risk = (max(0, 75 - avg) * 1.2 + vol * 1.5 + fails * 18
                    + diff * 20 + (1 - attend) * 25)
            risk = round(min(100, risk), 1)
            subj_risk[subj] = {"avg": round(avg, 1), "volatility": round(vol, 1),
                               "fails": fails, "difficulty": diff, "risk": risk}
            if risk >= 45 or avg < 65:
                weak.append(subj)

        weak.sort(key=lambda s: subj_risk[s]["risk"], reverse=True)
        overall = round(min(100, statistics.mean(v["risk"] for v in subj_risk.values())), 1)
        self.memory.set(f"{student_id}_risk_history",
                        (self.memory.get(f"{student_id}_risk_history", []) + [overall])[-10:])

        # 薄弱科目优先分配时间权重
        focus = weak[:3] if weak else sorted(subj_risk, key=lambda s: subj_risk[s]["avg"])[:3]
        ratios = self._ratios(focus, subj_risk)

        conservative = self._build_option("保守型", min(3.5, daily_hours_budget),
                                          "low", focus, ratios)
        sprint = self._build_option("冲刺型", daily_hours_budget, "high", focus, ratios)

        return {
            "agent": self.name, "display": self.display,
            "risk_score": overall, "subject_risk": subj_risk,
            "weak_subjects": weak,
            "options": [conservative, sprint],
            "selected": 1 if overall >= 55 else 0,  # 高风险默认冲刺
            "narrative": f"综合学业风险分 {overall}，薄弱科目：{('、'.join(weak) or '无')}。"
                         f"风险偏高，默认推荐{'冲刺型' if overall >= 55 else '保守型'}方案。",
        }

    def _ratios(self, focus, subj_risk):
        weights = [subj_risk[s]["risk"] for s in focus]
        total = sum(weights) or 1
        return [round(w / total, 2) for w in weights]

    def _build_option(self, name, hours, intensity, focus, ratios):
        blocks = [{"subject": s, "ratio": r, "hours": round(hours * r, 1)}
                  for s, r in zip(focus, ratios)]
        return {"name": name, "intensity": intensity, "daily_hours": round(hours, 1),
                "blocks": blocks,
                "desc": ("低强度稳基础，重点巩固" if intensity == "low"
                         else "高强度刷题提分，主攻") + "：" + "、".join(focus)}

    def revise(self, proposal, conflict_feedback):
        """收到冲突反馈后，Agent 基于自身约束迭代（这里记录认领，实际调整由均衡工具统一执行）。"""
        proposal.setdefault("revisions", []).append(conflict_feedback)
        return proposal
