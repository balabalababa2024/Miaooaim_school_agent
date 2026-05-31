from ..llm import llm
from ..database import get_conn
from .academic import AcademicAgent
from .logistics import LogisticsAgent
from .study_env import StudyEnvAgent
from .policy import PolicyAgent

class MasterAgent:
    """母智能体：调度、总结、冲突处理、优先级裁决"""

    def __init__(self):
        self.academic = AcademicAgent()
        self.logistics = LogisticsAgent()
        self.study_env = StudyEnvAgent()
        self.policy = PolicyAgent()

    def run_all(self, student_id, daily_study_hours=4.0, monthly_budget=1200.0):
        """
        一次性运行所有子Agent → 汇总 → 冲突检测 → 最终方案
        """
        # ========== 1. 并行/顺序执行所有子Agent ==========
        acad_state = self.academic.analyze(student_id, daily_study_hours)
        logi_state = self.logistics.analyze(student_id, monthly_budget)
        env_state = self.study_env.analyze(student_id, daily_study_hours)
        policy_state = self.policy.analyze()

        # ========== 2. 政策合规检查（冲突检测） ==========
        conflicts = self.policy.validate(acad_state, logi_state, env_state)

        # ========== 3. 优先级处理（高优先级覆盖低优先级） ==========
        self.resolve_conflicts(conflicts, acad_state, logi_state, env_state)

        # ========== 4. 大模型生成最终总结 ==========
        final_report = self.generate_final_report(
            student_id, acad_state, logi_state, env_state, conflicts
        )

        # ========== 5. 保存到 plan_history 表 ==========
        self.save_plan_history(student_id, final_report, conflicts)

        return {
            "student_id": student_id,
            "academic": acad_state,
            "logistics": logi_state,
            "study_env": env_state,
            "policy": policy_state,
            "conflicts": conflicts,
            "final_plan": final_report
        }

    def resolve_conflicts(self, conflicts, acad, logi, env):
        """优先级：学业(4) > 消费(3) > 环境(2) > 政策(1)"""
        for c in conflicts:
            agent = c["agent"]
            level = c["level"]
            msg = c["msg"]

            if agent == "study_env" and level == "HIGH":
                # 自习时间违规 → 强制调整
                opt = env["options"][0]
                opt["end"] = 22.5
                env["narrative"] = f"【已调整】{msg}\n" + env["narrative"]

            if agent == "academic" and level == "MID":
                acad["options"][0]["daily_hours"] = 8.0
                acad["narrative"] = f"【已调整】{msg}\n" + acad["narrative"]

    def generate_final_report(self, student_id, acad, logi, env, conflicts):
        """调用大模型生成最终整合规划"""
        conflict_text = "\n".join([c["msg"] for c in conflicts]) or "无冲突"

        prompt = f"""
你是校园全能规划助手，请整合以下信息，生成一份**完整、简洁、可执行**的学生一日/一月规划方案。

学生ID：{student_id}

【学业规划】
{acad['narrative']}

【消费预算】
{logi['saving_plan']}

【自习环境】
{env['narrative']}

【冲突与调整】
{conflict_text}

请输出：最终综合规划（分模块：学业、消费、自习）。
"""
        return llm(prompt)

    def save_plan_history(self, student_id, plan, conflicts):
        """保存到 plan_history 表"""
        conn = get_conn()
        cursor = conn.cursor()
        conflict_log = "\n".join([c["msg"] for c in conflicts]) if conflicts else "无"

        cursor.execute("""
            INSERT INTO plan_history (student_id, request, plan, conflict_log, create_time)
            VALUES (%s, %s, %s, %s, NOW())
        """, (
            student_id,
            "生成综合校园规划",
            plan,
            conflict_log
        ))
        conn.commit()
        conn.close()