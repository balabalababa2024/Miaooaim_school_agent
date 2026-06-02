import json
from ..llm import llm
from ..database import get_mysql_conn
from .academic import AcademicAgent
from .logistics import LogisticsAgent
from .study_env import StudyEnvAgent
from .policy import PolicyAgent

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
                  subjects=None, max_rounds=None):
        """
        多轮博弈协商主流程。

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

        # ========== 第1轮：各 Agent 独立提案 ==========
        acad_state = self.academic.analyze(student_id, daily_hours)
        logi_state = self.logistics.analyze(student_id, budget)
        env_state = self.study_env.analyze(student_id, daily_hours)
        policy_state = self.policy.analyze()

        for round_num in range(1, max_rounds + 1):
            # 1) 快照各 Agent 当前方案
            proposals = self._snapshot_proposals(
                acad_state, env_state, logi_state, policy_state
            )

            # 2) PolicyAgent 检测冲突
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

            # 4) 有冲突 → 分发给相关 Agent 修订
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

        # ========== 生成最终综合方案 ==========
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
        """调用大模型生成最终整合规划"""
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
                negotiation_summary.append(f"第{round_num}轮：达成共识 ✓")

        neg_text = "\n".join(negotiation_summary) if negotiation_summary else "无协商记录"

        consensus_text = "已达成共识" if consensus else "未完全达成共识，以下为最大均衡方案"

        prompt = f"""
你是校园全能规划助手。经过多智能体博弈协商，以下是最终结果。

协商状态：{consensus_text}

协商过程：
{neg_text}

【学业规划Agent方案】
{acad.get('narrative', '无')}

【自习环境Agent方案】
{env.get('narrative', '无')}

【后勤消费Agent方案】
{logi.get('saving_plan', '无')}

【政策合规约束】
{policy.get('narrative', '无')}

请整合以上所有方案，生成一份**完整、可执行**的学生规划方案。
要求分模块输出：学业安排、自习计划、消费预算、合规提醒。
每个模块3-5条具体可执行的要点。
"""
        return llm(prompt)

    def _save_plan_history(self, student_id, plan, round_logs):
        """保存到 plan_history 表"""
        try:
            conn = get_mysql_conn()
            cursor = conn.cursor()
            # 将协商日志摘要作为 conflict_log 存储
            conflict_summary = []
            for rl in round_logs:
                for c in rl.get("conflicts", []):
                    conflict_summary.append(
                        f"第{rl['round']}轮 [{c['severity']}] {c['description']}"
                    )
            conflict_log = "\n".join(conflict_summary) if conflict_summary else "无冲突"

            # 将完整协商日志存入 request 字段（作为上下文）
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
