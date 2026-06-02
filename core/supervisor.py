import json
import datetime
from core.llm import llm
from .database import get_experience_store, get_static_rule_store
from .memory import GlobalMemory, ScratchMemory
from core.agents.master import MasterAgent


WEIGHTS = {"academic": 0.4, "env": 0.3, "budget": 0.2, "policy": 0.1}


class Supervisor:
    def __init__(self):
        self.experience = get_experience_store()
        self.g = GlobalMemory.instance()
        self.master = MasterAgent()

    # ===================== 校规 QA =====================
    def policy_qa(self, query):
        store = get_static_rule_store()
        docs = store.search(query, top_k=3)

        context = "\n".join([f"· {d['text']}" for d in docs])
        prompt = f"""
你是校园政策助手，请根据校规回答。
校规：
{context}
问题：{query}
回答：
"""
        answer = llm(prompt)
        return {
            "question": query,
            "answer": answer,
            "refs": docs
        }

    # ===================== CoT 需求拆解 =====================
    def decompose(self, text):
        prompt = f"""
从用户请求中提取结构化参数，返回JSON（不要输出其他内容）：

字段说明：
- budget: 月度预算（数字，默认1000）
- daily_hours: 每日学习小时数（数字，默认4）
- want_env: 是否需要好的自习环境（布尔值，默认true）
- care_policy: 是否关注校规合规（布尔值，默认true）
- intensity: 学习强度（"low"/"normal"/"high"，默认"normal"）
- subjects: 重点关注的科目（字符串数组，默认[]）

用户请求：{text}

请直接输出JSON，例如：
{{"budget": 1000, "daily_hours": 4, "want_env": true, "care_policy": true, "intensity": "normal", "subjects": []}}
"""
        try:
            raw = llm(prompt)
            # 尝试提取JSON部分
            if "{" in raw and "}" in raw:
                json_str = raw[raw.index("{"):raw.rindex("}") + 1]
                return json.loads(json_str)
            return json.loads(raw)
        except Exception:
            return {
                "budget": 1000,
                "daily_hours": 4,
                "want_env": True,
                "care_policy": True,
                "intensity": "normal",
                "subjects": []
            }

    # ===================== 主规划入口 =====================
    def plan(self, student_id, request):
        scratch = ScratchMemory()
        cot = self.decompose(request)

        daily_hours = cot.get("daily_hours", 4.0)
        budget = cot.get("budget", 1000.0)
        want_env = cot.get("want_env", True)
        care_policy = cot.get("care_policy", True)
        intensity = cot.get("intensity", "normal")
        subjects = cot.get("subjects", [])

        # 调用 MasterAgent 多轮博弈协商
        result = self.master.negotiate(
            student_id=student_id,
            daily_hours=daily_hours,
            budget=budget,
            want_env=want_env,
            care_policy=care_policy,
            intensity=intensity,
            subjects=subjects
        )

        # 提取协商结果
        acad_state = result["academic"]
        logi_state = result["logistics"]
        env_state = result["study_env"]
        policy_state = result["policy"]
        rounds = result["rounds"]
        consensus = result["consensus"]
        final_report = result["final_plan"]

        # 存入经验库
        try:
            self.experience.add(
                request,
                meta={"final": final_report, "consensus": consensus,
                       "rounds": len(rounds)}
            )
        except Exception as e:
            print(f"[Supervisor] 保存经验失败: {e}")

        scratch.clear()

        return {
            "cot": cot,
            "rounds": rounds,
            "consensus": consensus,
            "total_rounds": len(rounds),
            "final_plan": {
                "study": acad_state.get("narrative", ""),
                "env": env_state.get("narrative", ""),
                "consume": logi_state.get("saving_plan", ""),
                "policy": policy_state.get("narrative", ""),
                "summary": final_report
            },
            "summary": f"多智能体博弈协商完成，共{len(rounds)}轮，"
                       f"{'已达成共识' if consensus else '未完全达成共识'}"
        }


def _now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
