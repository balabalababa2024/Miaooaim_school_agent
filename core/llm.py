"""
LLM 模块 —— 统一 LangChain LLM 接口
====================================
1. llm(prompt)         — 原始文本补全（向后兼容 fallback）
2. get_llm()           — 返回 LangChain ChatOpenAI 实例
3. create_agent()      — 创建 Tool Calling Agent（LangChain 1.x CompiledStateGraph）
4. run_agent()         — 执行 Agent 并提取最终文本
"""
import os
import traceback
import logging
from openai import OpenAI
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain.agents import create_agent as _lc_create_agent

logger = logging.getLogger(__name__)

# 加载环境变量
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(CURRENT_DIR, ".env")
load_dotenv(env_path)

# 接口配置
SENSENOVA_API_KEY = os.getenv("SENSENOVA_API_KEY")
BASE_URL = os.getenv("OPENAI_BASE_URL", "https://token.sensenova.cn/v1")
MODEL_ID = "sensenova-6.7-flash-lite"

# 密钥校验
if not SENSENOVA_API_KEY:
    raise EnvironmentError(f"未读取到 SENSENOVA_API_KEY，请检查 {env_path} 文件")


# ===================== 原始 OpenAI 客户端（向后兼容） =====================
_client = OpenAI(
    api_key=SENSENOVA_API_KEY,
    base_url=BASE_URL,
    timeout=30
)


def llm(prompt: str) -> str:
    """原始文本补全接口（无 tool calling）。向后兼容用。内置 Redis 缓存。"""
    prompt = prompt.strip()
    if not prompt:
        print("[LLM] 输入为空")
        return "输入内容不能为空，请重新输入有效问题或需求。"

    # ---- Redis 缓存读取 ----
    from .cache import cache_get, cache_set, _make_hash
    cache_key = f"llm:{_make_hash(prompt)}"
    cached_val = cache_get(cache_key)
    if cached_val is not None:
        return cached_val

    print(f"[LLM 发起请求] 提示词片段：{prompt[:200]}...")
    try:
        response = _client.chat.completions.create(
            model=MODEL_ID,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            timeout=30
        )
        if not response.choices:
            print("[LLM] 接口返回空结果")
            return "大模型未返回有效内容"

        result = response.choices[0].message.content.strip()
        print(f"[LLM 返回结果] 内容片段：{result[:200]}...")

        # ---- Redis 缓存写入（只缓存正常结果） ----
        if result and not result.startswith("大模型"):
            cache_set(cache_key, result, ttl=600)

        return result

    except Exception as e:
        print(f"[LLM 调用失败] 异常信息：{str(e)}")
        traceback.print_exc()
        return f"大模型调用异常：{str(e)}"


# ===================== LangChain LLM 工厂 =====================
def get_llm() -> ChatOpenAI:
    """创建 Sensenova LangChain LLM 实例（OpenAI 兼容接口）"""
    return ChatOpenAI(
        api_key=SENSENOVA_API_KEY,
        base_url=BASE_URL,
        model=MODEL_ID,
        temperature=0.1,
        timeout=30,
    )


# ===================== Tool Calling Agent 工厂 =====================
def create_agent(tools: list, system_prompt: str):
    """
    创建 Tool Calling Agent（LangChain 1.x CompiledStateGraph）。

    Args:
        tools: LangChain @tool 工具列表
        system_prompt: 系统提示词

    Returns:
        CompiledStateGraph，可调用 .invoke({"messages": [...]})
    """
    lc_llm = get_llm()
    agent = _lc_create_agent(lc_llm, tools=tools, system_prompt=system_prompt)
    return agent


def run_agent(agent, user_input: str, chat_history: list = None) -> str:
    """
    执行 Agent 并返回最终文本输出。

    Args:
        agent: CompiledStateGraph（由 create_agent 返回）
        user_input: 用户输入
        chat_history: 可选的历史消息列表

    Returns:
        Agent 的最终回复文本
    """
    try:
        # 构建消息列表
        messages = []
        if chat_history:
            messages.extend(chat_history)
        messages.append(HumanMessage(content=user_input))

        # 调用 agent
        result = agent.invoke({"messages": messages})

        # 提取最后一条 AI 消息
        output = ""
        if "messages" in result:
            for msg in reversed(result["messages"]):
                if hasattr(msg, "content") and msg.content and isinstance(msg, AIMessage):
                    output = msg.content
                    break

        if not output:
            output = str(result)
        return output

    except Exception as e:
        logger.error(f"Agent 执行失败: {e}")
        # fallback: 直接调用 LLM
        logger.info("回退到基础 LLM 调用")
        return llm(user_input)
