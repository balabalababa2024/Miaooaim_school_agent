"""
自习环境研判 Agent
==================
读取自习室人流量/CO₂/温湿度时序传感数据 → 计算各时段环境舒适度、拥挤指数 →
生成 3 套不同时段选址方案（带时长/楼层/环境评分约束），参与时间冲突校验。
"""
from ..database import get_conn
from ..memory import AgentMemory


class StudyEnvAgent:
    name = "study_env"
    display = "自习环境研判 Agent"

    def __init__(self):
        self.memory = AgentMemory("study_env")  # 私有记忆：用户偏好楼层

    def analyze(self, student_id, want_hours=4.0, prefer_floor=None):
        conn = get_conn()
        rows = [dict(r) for r in conn.execute("SELECT * FROM iot").fetchall()]
        conn.close()

        scored = []
        for r in rows:
            comfort = self._comfort(r)
            scored.append({**r, "comfort": comfort})

        # 按楼层聚合出连续优质时段，挑 3 个不同时段的窗口
        windows = self._best_windows(scored, want_hours)
        prefer = prefer_floor or self.memory.get(f"{student_id}_prefer_floor")
        if prefer:
            windows.sort(key=lambda w: (w["floor"] != prefer, -w["env_score"]))
        else:
            windows.sort(key=lambda w: -w["env_score"])

        options = windows[:3]
        for i, o in enumerate(options):
            o["name"] = f"方案{i+1}"
        # 记忆首选楼层
        if options:
            self.memory.set(f"{student_id}_prefer_floor", options[0]["floor"])

        return {
            "agent": self.name, "display": self.display,
            "options": options, "selected": 0,
            "curve": self._env_curve(scored),
            "narrative": f"研判 {len(rows)} 条 IoT 传感记录，"
                         f"推荐时段：{options[0]['floor']} "
                         f"{_fmt(options[0]['start'])}-{_fmt(options[0]['end'])}"
                         f"（环境分 {options[0]['env_score']}）。" if options else "无可用时段。",
        }

    def _comfort(self, r):
        # CO2 越低越好(<800优)、人流越少越好、温度接近24最佳
        co2_score = max(0, 100 - max(0, r["co2"] - 600) / 8)
        crowd_score = (1 - r["occupancy"]) * 100
        temp_score = 100 - abs(r["temperature"] - 24) * 8
        return round(0.45 * co2_score + 0.35 * crowd_score + 0.2 * temp_score, 1)

    def _best_windows(self, scored, want_hours):
        by_floor = {}
        for r in scored:
            by_floor.setdefault(r["floor"], []).append(r)
        wins = []
        span = max(2, int(round(want_hours)))
        for floor, recs in by_floor.items():
            recs.sort(key=lambda x: x["hour"])
            for i in range(len(recs) - span + 1):
                seg = recs[i:i + span]
                if seg[-1]["hour"] - seg[0]["hour"] != span - 1:
                    continue
                env_score = round(sum(s["comfort"] for s in seg) / span, 1)
                crowd = round(sum(s["occupancy"] for s in seg) / span, 2)
                wins.append({
                    "floor": floor, "start": float(seg[0]["hour"]),
                    "end": float(seg[-1]["hour"] + 1), "duration": float(span),
                    "env_score": env_score, "crowd_index": crowd,
                    "avg_co2": int(sum(s["co2"] for s in seg) / span),
                })
        # 同楼层只保留最优窗口，保证 3 个方案时段/楼层有差异
        best_per_floor = {}
        for w in sorted(wins, key=lambda x: -x["env_score"]):
            if w["floor"] not in best_per_floor:
                best_per_floor[w["floor"]] = w
        return list(best_per_floor.values())

    def _env_curve(self, scored):
        """返回各时段平均舒适度曲线（用于前端折线图）。"""
        by_hour = {}
        for r in scored:
            by_hour.setdefault(r["hour"], []).append(r["comfort"])
        return [{"hour": h, "comfort": round(sum(v) / len(v), 1)}
                for h, v in sorted(by_hour.items())]

    def revise(self, proposal, conflict_feedback):
        proposal.setdefault("revisions", []).append(conflict_feedback)
        return proposal


def _fmt(h):
    return f"{int(h):02d}:00"
