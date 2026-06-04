"""
LangChain 智能体模块（适配 Tool Calling）
========================================
提供便捷函数创建和运行校园规划 Agent。
底层使用 llm.py 的 create_agent / run_agent 工厂。
"""
import logging
from langchain_core.messages import HumanMessage, AIMessage
from .llm import create_agent, run_agent
from .tools import get_data_query_tools

logger = logging.getLogger(__name__)


# ===================== 综合规划 System Prompt =====================
SYSTEM_PROMPT = """你是校园多智能体协同规划平台的综合规划助手。

你可以使用以下工具获取学生的真实数据：
- query_grades: 查询学生成绩
- query_consumption: 查询消费明细
- query_iot_data: 查询自习室环境数据
- search_policy: 搜索校园校规

请基于真实数据进行分析和规划。输出要求：
1. 分模块：学业安排、自习计划、消费预算、合规提醒
2. 每个模块 3-5 条具体可执行的要点
3. 数据驱动：引用具体的分数、消费金额、环境数据
"""


def create_campus_agent(student_id: str):
    """
    创建校园规划 Tool Calling Agent。

    Args:
        student_id: 学生ID（工具调用时自动注入）

    Returns:
        AgentExecutor
    """
    tools = get_data_query_tools()
    return create_agent(tools, SYSTEM_PROMPT)


def run_campus_agent(student_id: str, prompt: str, agent_memory=None) -> str:
    """
    便捷函数：创建 Agent 并执行一次调用。
    自动从 AgentMemory 加载历史、保存交互。

    Args:
        student_id: 学生ID
        prompt: 用户输入
        agent_memory: AgentMemory 实例（可选）

    Returns:
        Agent 的最终回复文本
    """
    executor = create_campus_agent(student_id)

    # 构建历史消息
    chat_history = []
    if agent_memory:
        history = agent_memory.get_history(n=8)
        for msg in history:
            role = msg.get("role", "human")
            content = msg.get("content", "")
            if role == "human":
                chat_history.append(HumanMessage(content=content))
            elif role == "ai":
                chat_history.append(AIMessage(content=content))

    output = run_agent(executor, prompt, chat_history=chat_history if chat_history else None)

    # 保存交互到 AgentMemory
    if agent_memory:
        agent_memory.add_interaction("human", prompt)
        agent_memory.add_interaction("ai", output)

    return output
