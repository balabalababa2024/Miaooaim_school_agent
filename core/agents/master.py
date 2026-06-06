import json
import logging
from ..llm import create_agent, run_agent, llm
from ..database import get_mysql_conn
from ..tools import get_data_query_tools
from .academic import AcademicAgent
from .logistics import LogisticsAgent
from .study_env import StudyEnvAgent
from .policy import PolicyAgent

logger = logging.getLogger(__name__)

FINAL_REPORT_SYSTEM_PROMPT = """你是校园多智能体协同规划平台的综合规划助手。

你可以使用以下工具获取学生的真实数据：
- query_grades: 查询学生成绩
- query_consumption: 查询消费明细
- query_iot_data: 查询自习室环境数据
- search_policy: 搜索校园校规

请基于真实数据和多智能体协商结果，整合生成最终规划。输出要求：
1. 学业安排（3-5条，引用真实成绩数据）
2. 自习计划（3-5条，引用IoT环境数据）
3. 消费预算（3-5条，引用真实消费数据）
4. 合规提醒（3-5条，引用校规）
"""


class MasterAgent:
    """母智能体：多轮博弈协商调度、冲突裁决、最终综合"""

    MAX_ROUNDS = 3

    def __init__(self):
        self.academic = AcademicAgent()
        self.logistics = LogisticsAgent()
        self.study_env = StudyEnvAgent()
        self.policy = PolicyAgent()

    def negotiate(self, student_id, daily_hours=4.0, budget=1000.0,
                  want_env=True, care_policy=True, intensity="normal",
                  subjects=None, max_rounds=None, user_request=""):
        """
        多轮博弈协商主流程。user_request 为学生原始需求文本（最高优先级）。

        返回:
        {
            "rounds": [RoundLog, ...],
            "academic": final_acad_state,
            "logistics": final_logi_state,
            "study_env": final_env_state,
            "policy": policy_state,
            "consensus": bool,
            "total_rounds": int,
            "final_plan": str
        }
        """
        if max_rounds is None:
            max_rounds = self.MAX_ROUNDS

        round_logs = []

        # ========== 第1轮：各 Agent 独立提案（Tool Calling） ==========
        # 用户原始需求作为最高优先级传入各 Agent
        acad_state = self.academic.analyze(student_id, daily_hours, user_request=user_request)
        logi_state = self.logistics.analyze(student_id, budget, user_request=user_request)
        env_state = self.study_env.analyze(student_id, daily_hours, user_request=user_request)
        policy_state = self.policy.analyze()

        for round_num in range(1, max_rounds + 1):
            # 1) 快照各 Agent 当前方案
            proposals = self._snapshot_proposals(
                acad_state, env_state, logi_state, policy_state
            )

            # 2) PolicyAgent 检测冲突（纯 Python 确定性逻辑）
            conflicts = self.policy.validate(acad_state, logi_state, env_state)

            # 3) 无冲突 → 达成共识
            if not conflicts:
                round_logs.append({
                    "round": round_num,
                    "stage": "共识达成" if round_num > 1 else "独立提案",
                    "proposals": proposals,
                    "conflicts": [],
                    "resolutions": [],
                    "agent_rationale": {}
                })
                break

            # 4) 有冲突 → 分发给相关 Agent 修订（Tool Calling）
            resolutions = []
            rationale = {}

            for conflict in conflicts:
                affected = conflict.get("between", [])
                for agent_name in affected:
                    if agent_name == "academic":
                        before_hours = acad_state["options"][0].get("daily_hours", 0) if acad_state.get("options") else 0
                        acad_state = self.academic.revise(acad_state, conflict)
                        after_hours = acad_state["options"][0].get("daily_hours", 0) if acad_state.get("options") else 0
                        resolutions.append({
                            "conflict_type": conflict["type"],
                            "agent": "academic",
                            "action": conflict.get("suggestion", "调整学习计划"),
                            "before": {"daily_hours": before_hours},
                            "after": {"daily_hours": after_hours}
                        })
                        rationale["academic"] = f"针对「{conflict['type']}」冲突调整了学习方案"

                    elif agent_name == "study_env":
                        before_end = env_state["options"][0].get("end", 0) if env_state.get("options") else 0
                        env_state = self.study_env.revise(env_state, conflict)
                        after_end = env_state["options"][0].get("end", 0) if env_state.get("options") else 0
                        resolutions.append({
                            "conflict_type": conflict["type"],
                            "agent": "study_env",
                            "action": conflict.get("suggestion", "调整自习方案"),
                            "before": {"end": before_end},
                            "after": {"end": after_end}
                        })
                        rationale["study_env"] = f"针对「{conflict['type']}」冲突调整了自习时段"

                    elif agent_name == "logistics":
                        before_cap = logi_state.get("daily_meal_cap", 0)
                        logi_state = self.logistics.revise(logi_state, conflict)
                        after_cap = logi_state.get("daily_meal_cap", 0)
                        resolutions.append({
                            "conflict_type": conflict["type"],
                            "agent": "logistics",
                            "action": conflict.get("suggestion", "调整预算方案"),
                            "before": {"daily_meal_cap": before_cap},
                            "after": {"daily_meal_cap": after_cap}
                        })
                        rationale["logistics"] = f"针对「{conflict['type']}」冲突调整了消费预算"

            # 5) 记录本轮日志
            round_logs.append({
                "round": round_num,
                "stage": "协商修订" if round_num > 1 else "独立提案",
                "proposals": proposals,
                "conflicts": [self._format_conflict(c) for c in conflicts],
                "resolutions": resolutions,
                "agent_rationale": rationale
            })

        # 判断是否达成共识（最后一轮无冲突）
        consensus = len(round_logs) > 0 and len(round_logs[-1].get("conflicts", [])) == 0

        # ========== 生成最终综合方案（Tool Calling Agent） ==========
        final_report = self._generate_final_report(
            student_id, acad_state, logi_state, env_state, policy_state,
            round_logs, consensus
        )

        # 保存到 plan_history
        self._save_plan_history(student_id, final_report, round_logs)

        return {
            "rounds": round_logs,
            "academic": acad_state,
            "logistics": logi_state,
            "study_env": env_state,
            "policy": policy_state,
            "consensus": consensus,
            "total_rounds": len(round_logs),
            "final_plan": final_report
        }

    def negotiate_stream(self, student_id, daily_hours=4.0, budget=1000.0,
                         want_env=True, care_policy=True, intensity="normal",
                         subjects=None, max_rounds=None, user_request=""):
        """多轮博弈协商主流程（SSE 流式版本）。通过 yield 输出结构化事件。"""
        if max_rounds is None:
            max_rounds = self.MAX_ROUNDS

        round_logs = []

        # ========== 第1轮：各 Agent 独立提案 ==========
        agents_to_run = [
            ("academic", self.academic, {"student_id": student_id, "daily_hours": daily_hours, "user_request": user_request}),
            ("logistics", self.logistics, {"student_id": student_id, "monthly_budget": budget, "user_request": user_request}),
            ("study_env", self.study_env, {"student_id": student_id, "want_hours": daily_hours, "user_request": user_request}),
            ("policy", self.policy, {}),
        ]

        states = {}
        for agent_name, agent_obj, kwargs in agents_to_run:
            yield {"event": "agent_start", "data": {
                "agent": agent_name, "label": agent_obj.display
            }}
            if agent_name == "policy":
                states[agent_name] = agent_obj.analyze()
            else:
                states[agent_name] = agent_obj.analyze(**kwargs)
            state = states[agent_name]
            summary = ""
            if agent_name == "academic":
                opt = state.get("options", [{}])[0] if state.get("options") else {}
                summary = f"每日{opt.get('daily_hours', 0)}h，风险分{state.get('risk_score', 0)}，弱项：{', '.join(state.get('weak_subjects', [])) or '无'}"
            elif agent_name == "logistics":
                summary = f"预算{state.get('monthly_budget', 0)}元，已花{state.get('total_spent', 0):.0f}元，日均餐费上限{state.get('daily_meal_cap', 0)}元"
            elif agent_name == "study_env":
                opt = state.get("options", [{}])[0] if state.get("options") else {}
                summary = f"{opt.get('floor', '')} {opt.get('start', 0):.0f}:00-{opt.get('end', 0):.0f}:00，环境评分{opt.get('env_score', 0)}"
            elif agent_name == "policy":
                summary = state.get("narrative", "")[:100] or "校规约束已加载"
            yield {"event": "agent_complete", "data": {
                "agent": agent_name, "label": agent_obj.display, "summary": summary
            }}

        acad_state = states["academic"]
        logi_state = states["logistics"]
        env_state = states["study_env"]
        policy_state = states["policy"]

        for round_num in range(1, max_rounds + 1):
            stage = "独立提案" if round_num == 1 else "协商修订"
            yield {"event": "round_start", "data": {"round": round_num, "stage": stage}}

            proposals = self._snapshot_proposals(acad_state, env_state, logi_state, policy_state)
            yield {"event": "proposals", "data": proposals}

            conflicts = self.policy.validate(acad_state, logi_state, env_state)

            if not conflicts:
                yield {"event": "round_complete", "data": {
                    "round": round_num, "stage": "共识达成" if round_num > 1 else stage,
                    "conflicts": 0, "resolutions": 0
                }}
                round_logs.append({
                    "round": round_num,
                    "stage": "共识达成" if round_num > 1 else "独立提案",
                    "proposals": proposals, "conflicts": [], "resolutions": [],
                    "agent_rationale": {}
                })
                break

            formatted_conflicts = [self._format_conflict(c) for c in conflicts]
            yield {"event": "conflicts", "data": formatted_conflicts}

            resolutions = []
            rationale = {}

            for conflict in conflicts:
                affected = conflict.get("between", [])
                for agent_name in affected:
                    yield {"event": "revision_start", "data": {
                        "agent": agent_name, "conflict_type": conflict["type"]
                    }}

                    if agent_name == "academic":
                        before_hours = acad_state["options"][0].get("daily_hours", 0) if acad_state.get("options") else 0
                        acad_state = self.academic.revise(acad_state, conflict)
                        after_hours = acad_state["options"][0].get("daily_hours", 0) if acad_state.get("options") else 0
                        res = {"conflict_type": conflict["type"], "agent": "academic",
                               "action": conflict.get("suggestion", "调整学习计划"),
                               "before": {"daily_hours": before_hours}, "after": {"daily_hours": after_hours}}
                        resolutions.append(res)
                        rationale["academic"] = f"针对「{conflict['type']}」冲突调整了学习方案"
                    elif agent_name == "study_env":
                        before_end = env_state["options"][0].get("end", 0) if env_state.get("options") else 0
                        env_state = self.study_env.revise(env_state, conflict)
                        after_end = env_state["options"][0].get("end", 0) if env_state.get("options") else 0
                        res = {"conflict_type": conflict["type"], "agent": "study_env",
                               "action": conflict.get("suggestion", "调整自习方案"),
                               "before": {"end": before_end}, "after": {"end": after_end}}
                        resolutions.append(res)
                        rationale["study_env"] = f"针对「{conflict['type']}」冲突调整了自习时段"
                    elif agent_name == "logistics":
                        before_cap = logi_state.get("daily_meal_cap", 0)
                        logi_state = self.logistics.revise(logi_state, conflict)
                        after_cap = logi_state.get("daily_meal_cap", 0)
                        res = {"conflict_type": conflict["type"], "agent": "logistics",
                               "action": conflict.get("suggestion", "调整预算方案"),
                               "before": {"daily_meal_cap": before_cap}, "after": {"daily_meal_cap": after_cap}}
                        resolutions.append(res)
                        rationale["logistics"] = f"针对「{conflict['type']}」冲突调整了消费预算"

                    yield {"event": "revision_complete", "data": {
                        "agent": agent_name, "conflict_type": conflict["type"],
                        "before": res["before"], "after": res["after"]
                    }}

            round_logs.append({
                "round": round_num, "stage": stage,
                "proposals": proposals,
                "conflicts": formatted_conflicts,
                "resolutions": resolutions,
                "agent_rationale": rationale
            })
            yield {"event": "round_complete", "data": {
                "round": round_num, "stage": stage,
                "conflicts": len(conflicts), "resolutions": len(resolutions)
            }}

        consensus = len(round_logs) > 0 and len(round_logs[-1].get("conflicts", [])) == 0
        yield {"event": "consensus", "data": {"consensus": consensus, "total_rounds": len(round_logs)}}

        # 生成最终报告
        yield {"event": "report_start", "data": {}}
        final_report = self._generate_final_report(
            student_id, acad_state, logi_state, env_state, policy_state, round_logs, consensus
        )
        yield {"event": "report_complete", "data": {"summary": final_report[:200]}}
        self._save_plan_history(student_id, final_report, round_logs)

        # 最终完整结果
        yield {"event": "plan", "data": {
            "rounds": round_logs,
            "academic": acad_state,
            "logistics": logi_state,
            "study_env": env_state,
            "policy": policy_state,
            "consensus": consensus,
            "total_rounds": len(round_logs),
            "final_plan": final_report
        }}

    def _snapshot_proposals(self, acad, env, logi, policy):
        """快照各 Agent 当前方案的核心数据"""
        snap = {}

        if acad:
            opt = acad.get("options", [{}])[0] if acad.get("options") else {}
            snap["academic"] = {
                "summary": acad.get("narrative", "")[:200],
                "daily_hours": opt.get("daily_hours", 0),
                "risk_score": acad.get("risk_score", 0),
                "weak_subjects": acad.get("weak_subjects", [])
            }

        if env:
            opt = env.get("options", [{}])[0] if env.get("options") else {}
            snap["study_env"] = {
                "summary": env.get("narrative", "")[:200],
                "floor": opt.get("floor", ""),
                "start": opt.get("start", 0),
                "end": opt.get("end", 0),
                "env_score": opt.get("env_score", 0)
            }

        if logi:
            snap["logistics"] = {
                "summary": logi.get("saving_plan", "")[:200],
                "monthly_budget": logi.get("monthly_budget", 0),
                "total_spent": logi.get("total_spent", 0),
                "daily_meal_cap": logi.get("daily_meal_cap", 0)
            }

        if policy:
            snap["policy"] = {
                "summary": policy.get("narrative", "")[:200],
                "constraints": policy.get("constraints", {})
            }

        return snap

    def _format_conflict(self, conflict):
        """将冲突格式化为前端可展示的结构"""
        return {
            "severity": conflict.get("severity", "MID"),
            "between": conflict.get("between", []),
            "type": conflict.get("type", ""),
            "description": conflict.get("description", ""),
            "suggestion": conflict.get("suggestion", "")
        }

    def _generate_final_report(self, student_id, acad, logi, env, policy,
                                round_logs, consensus):
        """
        使用 Tool Calling Agent 生成最终整合规划。
        Agent 可调用工具查询真实数据（成绩、消费、IoT、校规），实现数据驱动的规划。
        """
        # 收集协商过程摘要
        negotiation_summary = []
        for rl in round_logs:
            round_num = rl["round"]
            conflicts = rl.get("conflicts", [])
            resolutions = rl.get("resolutions", [])
            if conflicts:
                conflict_desc = "; ".join([c["description"][:60] for c in conflicts])
                negotiation_summary.append(f"第{round_num}轮发现冲突：{conflict_desc}")
            if resolutions:
                resolve_desc = "; ".join([r["action"][:60] for r in resolutions])
                negotiation_summary.append(f"第{round_num}轮协商调整：{resolve_desc}")
            if not conflicts:
                negotiation_summary.append(f"第{round_num}轮：达成共识")

        neg_text = "\n".join(negotiation_summary) if negotiation_summary else "无协商记录"
        consensus_text = "已达成共识" if consensus else "未完全达成共识，以下为最大均衡方案"

        prompt = f"""经过多智能体博弈协商，以下是各Agent的方案汇总。请调用工具查询学生的真实数据（成绩、消费、环境），整合生成最终规划。

协商状态：{consensus_text}
协商过程：
{neg_text}

【学业Agent方案】
{acad.get('narrative', '无')[:500]}

【自习Agent方案】
{env.get('narrative', '无')[:500]}

【消费Agent方案】
{logi.get('saving_plan', '无')[:500]}

【合规约束】
{policy.get('narrative', '无')[:300]}

请使用工具查询该学生的真实数据，然后整合以上方案，输出完整规划：
1. 学业安排（3-5条，引用真实成绩数据）
2. 自习计划（3-5条，引用IoT环境数据）
3. 消费预算（3-5条，引用真实消费数据）
4. 合规提醒（3-5条，引用校规）
"""

        # 使用 Tool Calling Agent（可调用工具获取真实数据）
        try:
            tools = get_data_query_tools()
            executor = create_agent(tools, FINAL_REPORT_SYSTEM_PROMPT)
            report = run_agent(executor, prompt)
            if report and not report.startswith("规划生成失败"):
                self.academic.memory.save_summary(report[:200])
                return report
        except Exception as e:
            logger.warning(f"Tool Calling Agent 执行失败，回退到基础LLM: {e}")

        # 回退：直接调用 LLM（不使用工具）
        return llm(prompt)

    def _save_plan_history(self, student_id, plan, round_logs):
        """保存到 plan_history 表"""
        try:
            conn = get_mysql_conn()
            cursor = conn.cursor()
            conflict_summary = []
            for rl in round_logs:
                for c in rl.get("conflicts", []):
                    conflict_summary.append(
                        f"第{rl['round']}轮 [{c['severity']}] {c['description']}"
                    )
            conflict_log = "\n".join(conflict_summary) if conflict_summary else "无冲突"

            round_count = len(round_logs)
            request_summary = f"多智能体博弈规划（{round_count}轮协商）"

            cursor.execute("""
                INSERT INTO plan_history (student_id, request, plan, conflict_log, create_time)
                VALUES (%s, %s, %s, %s, NOW())
            """, (student_id, request_summary, plan, conflict_log))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[MasterAgent] 保存规划历史失败: {e}")
