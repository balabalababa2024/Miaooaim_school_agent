"""
校园后勤消费 Agent
==================
读取食堂月度消费 + 宿舍水电账单 → 统计月均开销、高频高价菜品 →
按用户月度预算生成省钱就餐搭配 + 水电节能建议（带每日餐饮上限约束）。
"""
from ..database import get_conn
from ..memory import AgentMemory


class LogisticsAgent:
    name = "logistics"
    display = "校园后勤消费 Agent"

    def __init__(self):
        self.memory = AgentMemory("logistics")  # 私有记忆：历史消费习惯

    def analyze(self, student_id, monthly_budget=1000.0):
        conn = get_conn()
        meals = [dict(r) for r in conn.execute(
            "SELECT item, amount FROM consumption WHERE student_id=? AND category='食堂'",
            (student_id,)).fetchall()]
        utility = [dict(r) for r in conn.execute(
            "SELECT item, amount FROM consumption WHERE student_id=? AND category='水电'",
            (student_id,)).fetchall()]
        conn.close()

        meal_total = round(sum(m["amount"] for m in meals), 1)
        utility_total = round(sum(u["amount"] for u in utility), 1)
        monthly_total = round(meal_total + utility_total, 1)
        base_daily_meal = round(meal_total / 30, 1)

        # 高频高价菜品
        freq = {}
        for m in meals:
            d = freq.setdefault(m["item"], {"count": 0, "price": m["amount"]})
            d["count"] += 1
        top_dishes = sorted(
            [{"item": k, **v} for k, v in freq.items()],
            key=lambda x: (-x["price"], -x["count"]))[:4]

        meal_budget = round(monthly_budget * 0.85, 1)  # 预算 85% 给餐饮
        daily_meal_cap = round(meal_budget / 30, 1)

        saving_plan = self._saving_plan(top_dishes, daily_meal_cap)
        utility_tips = self._utility_tips(utility_total)

        self.memory.set(f"{student_id}_avg_daily_meal", base_daily_meal)

        return {
            "agent": self.name, "display": self.display,
            "monthly_total": monthly_total, "meal_total": meal_total,
            "utility_total": utility_total, "base_daily_meal": base_daily_meal,
            "monthly_budget": monthly_budget, "daily_meal_cap": daily_meal_cap,
            "top_dishes": top_dishes, "saving_plan": saving_plan,
            "utility_tips": utility_tips,
            "narrative": f"月度总开销 {monthly_total} 元（餐饮 {meal_total}/水电 {utility_total}）。"
                         f"按预算 {monthly_budget} 元，每日餐饮上限 {daily_meal_cap} 元。",
        }

    def _saving_plan(self, top_dishes, cap):
        plan = ["早餐：煎饼果子 6 元 / 包子豆浆，控制在 6 元内",
                "午餐：1 荤(番茄炒蛋盖饭 9 元) + 免费例汤 + 白米饭 1 元",
                "晚餐：青菜豆腐 5 元 + 白米饭 1 元，搭配平价窗口"]
        if cap < 25:
            plan.append("⚠ 预算偏紧：每周最多 1 次麻辣香锅/红烧肉等高价菜，其余走平价窗口。")
        else:
            plan.append("预算充裕：可保留 2-3 次喜爱的红烧肉/黄焖鸡，注意荤素均衡。")
        return plan

    def _utility_tips(self, utility_total):
        tips = ["人走断电：离寝关闭显示器、台灯、充电器，杜绝待机耗电。",
                "合理用空调：夏季设 26℃、配合风扇，单次不超过 4 小时。",
                "集中用水：洗漱集中时段，避免长流水。"]
        if utility_total > 130:
            tips.insert(0, f"⚠ 本月水电 {utility_total} 元已超人均建议 130 元，需重点节约。")
        return tips

    def revise(self, proposal, conflict_feedback):
        proposal.setdefault("revisions", []).append(conflict_feedback)
        return proposal
