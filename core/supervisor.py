"""
顶层 Supervisor 总控 Agent（项目技术内核）
=========================================
五大核心能力：
  1. CoT 思维链复杂需求拆解（自然语言 → 四类约束）
  2. 多智能体多轮博弈协商（时间片冲突检测 → 迭代修改 → 加权均衡，最多 3 轮）
  3. 三级隔离记忆调度（全局共享 / Agent 私有 / 单次任务临时）
  4. 任务复盘 + 动态经验自进化（案例向量化入库，同类需求直接复用，越用越快）
  5. 多工具自主编排 + 失败重试

LangGraph 在企业版用于编排循环博弈状态机；此处用等价的显式状态机实现，
保留「节点 + 循环 + 条件跳转」的同构结构，逻辑完全一致且零额外依赖。
"""
import re
import datetime

from . import tools
from .database import (get_experience_store, list_plans, save_plan)
from .memory import GlobalMemory, ScratchMemory
from .agents.academic import AcademicAgent
from .agents.study_env import StudyEnvAgent
from .agents.logistics import LogisticsAgent
from .agents.policy import PolicyAgent

WEIGHTS = {"academic": 0.40, "env": 0.30, "budget": 0.20, "policy": 0.10}


class Supervisor:
    def __init__(self):
        self.academic = AcademicAgent()
        self.study_env = StudyEnvAgent()
        self.logistics = LogisticsAgent()
        self.policy = PolicyAgent()
        self.experience = get_experience_store()
        self.g = GlobalMemory.instance()

    # ----------------------------------------------- 能力1：CoT 需求拆解 ----
    def decompose(self, text):
        """思维链分步拆解，提取四类约束 + 关键参数。"""
        steps, constraints = [], {}

        # 预算
        m = re.search(r"(\d{3,5})\s*(?:元|块|/月|每月)?", text)
        budget = float(m.group(1)) if m and ("预算" in text or "吃饭" in text or "生活费" in text or "元" in text) else 1000.0
        constraints["budget"] = budget
        steps.append(f"① 预算约束：识别月度生活费/餐饮预算 ≈ {int(budget)} 元/月")

        # 学习强度
        intensity = "sprint" if any(k in text for k in ["冲刺", "高强度", "提分", "刷题", "期末"]) else "normal"
        daily_hours = 6.0 if intensity == "sprint" else 4.0
        constraints["daily_hours"] = daily_hours
        subjects = [s for s in ["高数", "高等数学", "英语", "数据结构", "线代", "线性代数", "物理", "政治"]
                    if s in text]
        steps.append(f"② 学习时长约束：强度={'冲刺' if intensity=='sprint' else '常规'}，"
                     f"每日可学 ≈ {daily_hours}h，重点科目：{('、'.join(subjects) or '系统自动研判')}")

        # 自习环境
        want_env = any(k in text for k in ["环境", "自习", "安静", "舒适", "自习室"])
        constraints["want_env"] = want_env
        steps.append(f"③ 自习环境约束：{'要求环境好/低噪低CO₂的自习时段' if want_env else '无特别要求，默认优选'}")

        # 校规
        care_policy = any(k in text for k in ["熄灯", "规定", "校规", "不能违反", "合规", "关闭"])
        constraints["care_policy"] = care_policy
        steps.append(f"④ 校规时间约束：{'需满足宿舍熄灯/自习室关闭等硬性规定' if care_policy else '默认套用全校统一校规'}")

        steps.append("→ 路由：下发需求至「学业 / 自习 / 后勤 / 政策」四大垂直 Agent，触发初始方案生成")
        return {"steps": steps, "constraints": constraints,
                "intensity": intensity, "subjects": subjects}

    # --------------------------- 能力4：动态经验库检索（自进化复用） ----
    def try_reuse(self, request):
        hits = self.experience.search(request, top_k=1, threshold=0.58)
        if hits:
            return hits[0]
        return None

    # ----------------------- 能力2：多轮博弈协商 + 工具编排主流程 ----
    def plan(self, student_id, request):
        log = {"request": request, "student_id": student_id}
        scratch = ScratchMemory()  # 能力3：单次任务临时记忆

        # —— 先查动态经验库，命中则跳过博弈（越用越快）——
        reuse = self.try_reuse(request)
        if reuse:
            final = reuse["meta"]["final_plan"]
            save_plan(student_id, request, final, rounds=0, reused=True,
                      created_at=_now())
            return {
                "reused": True, "match_score": reuse["score"],
                "cot": reuse["meta"].get("cot", {"steps": ["命中历史成熟案例，直接复用"]}),
                "rounds": [], "final_plan": final,
                "tool_calls": [{"tool": "experience_retrieval", "ok": True,
                                "detail": f"动态经验库匹配度 {reuse['score']}，跳过 3 轮博弈"}],
                "summary": f"⚡ 命中动态经验库历史案例（相似度 {reuse['score']}），"
                           f"直接复用成熟方案，响应提速。",
            }

        tool_calls = []

        # —— 能力1：CoT 拆解 ——
        cot = self.decompose(request)
        c = cot["constraints"]
        scratch.set("constraints", c)

        # —— 各 Agent 生成初始方案（含 NL2SQL 工具调用）——
        nl = tools.run_tool(tools.nl2sql_tool, f"{student_id} 学生各科成绩风险")
        tool_calls.append({"tool": "nl2sql", "ok": nl["ok"],
                           "detail": nl["result"]["summary"] if nl["ok"] else nl["error"],
                           "sql": nl["result"]["sql"] if nl["ok"] else None})

        state = {
            "academic": self.academic.analyze(student_id, c["daily_hours"]),
            "study_env": self.study_env.analyze(student_id, want_hours=4.0),
            "logistics": self.logistics.analyze(student_id, c["budget"]),
            "policy": self.policy.analyze(),
        }
        # CoT 识别出「冲刺」意图时，尊重用户诉求选冲刺型方案（更长学习时长 → 触发真实博弈冲突）
        if cot["intensity"] == "sprint":
            state["academic"]["selected"] = 1
            state["academic"]["narrative"] += "（CoT 识别到冲刺意图，已切换冲刺型方案待博弈校验）"

        rounds = []
        initial = _snapshot(state, "初始方案")
        initial["agents_narrative"] = {k: state[k].get("narrative", "") for k in state}

        # —— 能力2：最多 3 轮博弈 ——
        max_rounds = 3
        for rnd in range(1, max_rounds + 1):
            conf = tools.run_tool(tools.time_conflict_tool, state)
            tool_calls.append({"tool": "time_conflict", "ok": conf["ok"],
                               "detail": f"检出 {len(conf['result'])} 处冲突" if conf["ok"] else conf["error"]})
            conflicts = conf["result"] if conf["ok"] else []
            violations = self.policy.validate(state)

            round_log = {
                "round": rnd,
                "snapshot": _snapshot(state, f"第 {rnd} 轮"),
                "conflicts": conflicts,
                "violations": violations,
                "actions": [],
            }

            if not conflicts and not violations:
                round_log["actions"].append("✅ 本轮无冲突、无违规，博弈收敛。")
                rounds.append(round_log)
                break

            # 下发冲突给相关 Agent（认领），再用加权均衡工具统一调整
            for cf in conflicts:
                for ag in cf["agents"]:
                    agent_obj = getattr(self, ag, None)
                    if ag in state and hasattr(agent_obj, "revise"):
                        agent_obj.revise(state[ag], cf["detail"])

            bal = tools.run_tool(tools.weighted_balance_tool, state, conflicts, WEIGHTS)
            tool_calls.append({"tool": "weighted_balance", "ok": bal["ok"],
                               "detail": "已计算加权折中方案" if bal["ok"] else bal["error"]})
            if bal["ok"]:
                round_log["actions"] = bal["result"]["actions"]
                state = bal["result"]["state"]
            rounds.append(round_log)
        else:
            rounds[-1]["actions"].append(
                f"⚖ 达到最大 {max_rounds} 轮，仍有残余冲突，按权重"
                f"（学业{WEIGHTS['academic']}>环境{WEIGHTS['env']}>预算{WEIGHTS['budget']}"
                f">政策{WEIGHTS['policy']}）输出全局折中最优解。")

        # —— 甘特图工具 ——
        gantt = tools.run_tool(tools.gantt_tool, state)
        tool_calls.append({"tool": "gantt", "ok": gantt["ok"],
                           "detail": "已生成周规划甘特图" if gantt["ok"] else gantt["error"]})

        final_plan = self._compose_final(state, cot, gantt["result"] if gantt["ok"] else None)

        # —— 能力4：复盘 + 经验自进化入库 ——
        self._reflect_and_store(request, cot, rounds, final_plan)
        save_plan(student_id, request, final_plan, rounds=len(rounds), reused=False,
                  created_at=_now())

        scratch.clear()  # 单次任务临时记忆销毁

        return {
            "reused": False, "cot": cot, "initial": initial,
            "rounds": rounds, "final_plan": final_plan,
            "tool_calls": tool_calls, "weights": WEIGHTS,
            "summary": f"经 {len(rounds)} 轮多智能体博弈协商，输出全局均衡规划方案，"
                       f"案例已向量化存入动态经验库。",
        }

    # ----------------------------------------- 最终方案组装 ----
    def _compose_final(self, state, cot, gantt):
        aca = state["academic"]
        a_opt = aca["options"][aca["selected"]]
        env = state["study_env"]["options"][state["study_env"]["selected"]]
        logi = state["logistics"]
        return {
            "study": {
                "plan_name": a_opt["name"], "daily_hours": a_opt["daily_hours"],
                "risk_score": aca["risk_score"], "weak_subjects": aca["weak_subjects"],
                "blocks": a_opt["blocks"],
            },
            "study_room": {
                "floor": env["floor"], "start": env["start"], "end": env["end"],
                "env_score": env["env_score"], "crowd_index": env["crowd_index"],
            },
            "budget": {
                "monthly_budget": logi["monthly_budget"],
                "daily_meal_cap": logi["daily_meal_cap"],
                "saving_plan": logi["saving_plan"], "utility_tips": logi["utility_tips"],
            },
            "policy": state["policy"]["constraints"],
            "gantt": gantt,
            "env_curve": state["study_env"].get("curve", []),
            "consumption_breakdown": {
                "餐饮": logi["meal_total"], "水电": logi["utility_total"],
            },
        }

    # ------------------- 能力4：复盘流程 ----
    def _reflect_and_store(self, request, cot, rounds, final_plan):
        conflict_summary = "; ".join(
            cf["detail"] for r in rounds for cf in r.get("conflicts", []))
        case_summary = (f"博弈 {len(rounds)} 轮，冲突：{conflict_summary or '无'}。"
                        f"最终：{final_plan['study']['plan_name']}方案 "
                        f"{final_plan['study']['daily_hours']}h，自习 {final_plan['study_room']['floor']}，"
                        f"每日餐饮上限 {final_plan['budget']['daily_meal_cap']}元。")
        # 向量索引以「用户需求」为主（重复加权），保证同类需求高相似度命中复用；
        # 完整方案存 metadata。
        index_text = f"{request} {request} 需求约束：{cot['constraints']}"
        self.experience.add(index_text, meta={
            "request": request, "cot": cot, "final_plan": final_plan,
            "case_summary": case_summary, "created_at": _now()})

    # -------------------------------------- 数据中心 / 看板 ----
    def history(self, student_id=None):
        return list_plans(student_id)

    def policy_qa(self, question):
        return self.policy.ask(question)


def _snapshot(state, label):
    aca = state["academic"]; env = state["study_env"]
    return {
        "label": label,
        "academic": {
            "selected": aca["options"][aca["selected"]]["name"],
            "daily_hours": aca["options"][aca["selected"]]["daily_hours"],
            "risk_score": aca["risk_score"],
        },
        "study_env": {
            "floor": env["options"][env["selected"]]["floor"],
            "start": env["options"][env["selected"]]["start"],
            "end": env["options"][env["selected"]]["end"],
            "env_score": env["options"][env["selected"]]["env_score"],
        },
        "logistics": {"daily_meal_cap": state["logistics"]["daily_meal_cap"]},
    }


def _now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
