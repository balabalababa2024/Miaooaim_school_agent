import json
import datetime
from core.llm import llm
from . import tools
from .database import get_experience_store, save_plan, get_static_rule_store
from .memory import GlobalMemory, ScratchMemory
from .agents.academic import AcademicAgent
from .agents.study_env import StudyEnvAgent
from .agents.logistics import LogisticsAgent
from .agents.policy import PolicyAgent

WEIGHTS = {"academic":0.4,"env":0.3,"budget":0.2,"policy":0.1}

class Supervisor:
    def __init__(self):
        self.academic = AcademicAgent()
        self.study_env = StudyEnvAgent()
        self.logistics = LogisticsAgent()
        self.policy = PolicyAgent()
        self.experience = get_experience_store()
        self.g = GlobalMemory.instance()

    # ===================== 校规 QA（接口需要的方法）=====================
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

    def decompose(self, text):
        prompt = f"""
从用户请求提取JSON：
budget, daily_hours, want_env, care_policy, intensity, subjects
请求：{text}
"""
        try:
            return json.loads(llm(prompt))
        except:
            return {"budget":1000,"daily_hours":4,"want_env":True,"care_policy":True}

    def plan(self, student_id, request):
        scratch = ScratchMemory()
        cot = self.decompose(request)
        c = cot

        state = {
            "academic": self.academic.analyze(student_id, c["daily_hours"]),
            "study_env": self.study_env.analyze(student_id, 4),
            "logistics": self.logistics.analyze(student_id, c["budget"]),
            "policy": self.policy.analyze()
        }

        for _ in range(2):
            conflicts = tools.time_conflict_tool(state)
            if not conflicts: break
            tools.weighted_balance_tool(state, conflicts, WEIGHTS)

        final = {
            "study_plan": state["academic"]["narrative"],
            "environment": state["study_env"]["narrative"],
            "budget": state["logistics"]["saving_plan"],
            "policy": state["policy"]["constraints"]
        }

        self.experience.add(request, meta={"final": final})
        save_plan(student_id, request, final, 2, False, _now())
        scratch.clear()

        return {
            "cot": cot,
            "final_plan": final,
            "summary": "LLM多智能体已完成规划"
        }

def _now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")