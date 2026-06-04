import json
import datetime
import logging
from .llm import create_agent, run_agent, llm
from .tools import get_orchestrator_tools
from .database import get_experience_store, get_static_rule_store
from .memory import GlobalMemory, ScratchMemory
from .agents.master import MasterAgent

logger = logging.getLogger(__name__)

DECOMPOSE_SYSTEM_PROMPT = """你是参数解析助手。
你可以使用以下工具：
- parse_planning_params: 从用户的自然语言请求中提取结构化规划参数

请调用 parse_planning_params 工具，从用户输入中提取结构化参数。
返回 JSON 格式的参数。"""

QA_SYSTEM_PROMPT = """你是校园政策助手。
你可以使用以下工具：
- search_policy: 根据关键词搜索校园校规

请调用 search_policy 工具搜索相关校规，然后基于搜索结果回答用户问题。"""


WEIGHTS = {"academic": 0.4, "env": 0.3, "budget": 0.2, "policy": 0.1}


class Supervisor:
    def __init__(self):
        self.experience = get_experience_store()
        self.g = GlobalMemory.instance()
        self.master = MasterAgent()

    # ===================== 校规 QA（Tool Calling） =====================
    def policy_qa(self, query):
        tools = get_orchestrator_tools()
        executor = create_agent(tools, QA_SYSTEM_PROMPT)

        try:
            answer = run_agent(executor, query)
        except Exception as e:
            logger.warning(f"policy_qa tool calling 失败，回退: {e}")
            store = get_static_rule_store()
            docs = store.search(query, top_k=3)
            context = "\n".join([f"· {d['text']}" for d in docs])
            answer = llm(f"校规：{context}\n问题：{query}\n回答：")

        # 获取引用的校规
        store = get_static_rule_store()
        refs = store.search(query, top_k=3)

        return {
            "question": query,
            "answer": answer,
            "refs": refs
        }

    # ===================== CoT 需求拆解（Tool Calling） =====================
    def decompose(self, text):
        tools = get_orchestrator_tools()
        executor = create_agent(tools, DECOMPOSE_SYSTEM_PROMPT)

        try:
            raw = run_agent(executor, f"请解析以下用户请求：{text}")
            # 尝试提取 JSON
            if "{" in raw and "}" in raw:
                json_str = raw[raw.index("{"):raw.rindex("}") + 1]
                return json.loads(json_str)
            return json.loads(raw)
        except Exception as e:
            logger.warning(f"decompose tool calling 失败，回退: {e}")
            # fallback: 直接 LLM
            try:
                raw = llm(
                    f"从用户请求中提取结构化参数，返回JSON（不要输出其他内容）：\n"
                    f"字段：budget,daily_hours,want_env,care_policy,intensity,subjects\n"
                    f"用户请求：{text}\n"
                    f"请直接输出JSON"
                )
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
