from ..llm import llm
from ..langchain_agent import query_grades_from_db
from ..memory import AgentMemory

class AcademicAgent:
    name = "academic"
    display = "学业规划智能体"
    priority = 4  # 优先级最高（学业>消费>环境>政策）

    def __init__(self):
        self.memory = AgentMemory("academic")

    def analyze(self, student_id, daily_hours=4.0):
        """分析成绩 → 生成学习计划"""
        # 使用统一的数据查询函数
        grades_list = query_grades_from_db(student_id)

        # 科目均分 & 挂科统计
        subject_map = {}
        for g in grades_list:
            sub = g["subject"]
            if sub not in subject_map:
                subject_map[sub] = {"scores": [], "failed": 0}
            subject_map[sub]["scores"].append(g["score"])
            if g["failed"] == 1:
                subject_map[sub]["failed"] = 1

        grades = []
        for sub, item in subject_map.items():
            avg = sum(item["scores"]) / len(item["scores"])
            grades.append({
                "subject": sub,
                "avg_score": avg,
                "has_fail": item["failed"]
            })

        # 构建大模型上下文
        context_lines = [
            f"科目：{g['subject']}，均分：{g['avg_score']:.1f}，是否挂科：{'是' if g['has_fail'] else '否'}"
            for g in grades
        ]
        context = "\n".join(context_lines)

        prompt = f"""
你是专业学业规划师。
学生成绩如下：
{context}

要求每日学习 {daily_hours} 小时。
请生成一份**可执行、简洁、分点**的学习提升计划，重点优先提升挂科/低分科目。
"""
        plan = llm(prompt)

        # 记忆：保存分析结果
        self.memory.add_interaction("system", f"分析完成：{len(grades)}个科目，风险分{sum(1 for g in grades if g['has_fail'])}")

        # 风险分 = 挂科数量
        risk_score = sum(1 for g in grades if g["has_fail"])
        weak_subjects = [g["subject"] for g in grades if g["has_fail"]]

        return {
            "agent": self.name,
            "options": [{
                "name": "智能学习方案",
                "daily_hours": daily_hours,
                "blocks": [{"subject": g["subject"], "ratio": 0.25} for g in grades]
            }],
            "selected": 0,
            "risk_score": risk_score,
            "weak_subjects": weak_subjects,
            "narrative": plan,
            "raw_data": grades
        }

    def revise(self, state, conflict):
        """根据结构化冲突信息修订学习计划"""
        conflict_type = conflict.get("type", "")
        suggestion = conflict.get("suggestion", "请自行调整")
        description = conflict.get("description", "")

        if conflict_type == "time_overflow":
            evidence = conflict.get("evidence", {})
            limit = evidence.get("limit", 12.0)
            env_hours = evidence.get("env_hours", 0)
            new_hours = max(limit - env_hours, 3.0)
            if "options" in state and state["options"]:
                state["options"][0]["daily_hours"] = round(new_hours, 1)
            suggestion = f"将每日学习时长从 {evidence.get('acad_hours', '?')}h 降至 {new_hours:.1f}h"

        if conflict_type == "low_gpa_risk":
            weak = conflict.get("evidence", {}).get("weak_subjects", [])
            suggestion = f"请在计划中优先安排以下挂科科目的补习时间：{', '.join(weak)}"

        prompt = f"""
你是学业规划Agent。在多智能体协商中发现了以下冲突：

冲突类型：{conflict_type}
问题描述：{description}
调整建议：{suggestion}

你当前的学习计划：
{state.get('narrative', '')}

请根据冲突信息修订你的计划。要求：
1. 解决上述冲突
2. 保持学业效果最大化
3. 输出修订后的简洁分点计划
"""
        state["narrative"] = llm(prompt)
        self.memory.add_interaction("system", f"修订计划，冲突类型：{conflict_type}")
        return state
