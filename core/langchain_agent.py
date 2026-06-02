"""
LangChain 智能体模块（适配 LangChain 1.x / LangGraph）
========================================================
1. LangChain LLM（ChatOpenAI 对接 Sensenova API）
2. 工具定义（查成绩、查消费、查IoT、查校规）
3. Agent 工厂（create_campus_agent）
4. 记忆桥接（AgentMemory ↔ LangChain Messages）
"""
import os
import logging
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain.agents import create_agent

logger = logging.getLogger(__name__)

# 加载环境变量
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(CURRENT_DIR, ".env"))

# ===================== Part 1: LangChain LLM =====================
def get_llm():
    """创建 Sensenova LLM（OpenAI 兼容接口）"""
    api_key = os.getenv("SENSENOVA_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://token.sensenova.cn/v1")
    if not api_key:
        raise EnvironmentError("SENSENOVA_API_KEY 未配置")
    return ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model="sensenova-6.7-flash-lite",
        temperature=0.1,
        timeout=30,
    )


# ===================== Part 2: 数据查询函数 =====================
def query_grades_from_db(student_id: str) -> list[dict]:
    """从 MySQL 查询学生成绩"""
    from .database import get_mysql_conn
    try:
        conn = get_mysql_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT subject, score, failed FROM grades WHERE student_id = %s",
            (student_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        return rows
    except Exception as e:
        logger.error(f"查询成绩失败: {e}")
        return []


def query_consumption_from_db(student_id: str) -> list[dict]:
    """从 MySQL 查询学生消费明细"""
    from .database import get_mysql_conn
    try:
        conn = get_mysql_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT category, SUM(amount) AS total, COUNT(*) AS cnt "
            "FROM consumption WHERE student_id = %s GROUP BY category",
            (student_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        return rows
    except Exception as e:
        logger.error(f"查询消费失败: {e}")
        return []


def query_iot_from_db() -> list[dict]:
    """从 MySQL 查询自习室 IoT 数据"""
    from .database import get_mysql_conn
    try:
        conn = get_mysql_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT floor, hour, traffic, co2, temp FROM iot ORDER BY floor, hour")
        rows = cursor.fetchall()
        conn.close()
        return rows
    except Exception as e:
        logger.error(f"查询IoT数据失败: {e}")
        return []


def query_policy_from_db(query: str, top_k: int = 3) -> list[str]:
    """从向量库搜索校规"""
    try:
        from .database import get_static_rule_store
        store = get_static_rule_store()
        hits = store.search(query, top_k=top_k)
        return [h["text"] for h in hits]
    except Exception as e:
        logger.error(f"搜索校规失败: {e}")
        return []


# ===================== Part 3: LangChain 工具 =====================
def create_tools(student_id: str) -> list:
    """创建绑定到特定学生的 LangChain 工具列表（闭包捕获 student_id）"""

    @tool
    def query_grades() -> str:
        """查询当前学生的所有科目成绩。返回科目名称、分数、是否挂科。"""
        rows = query_grades_from_db(student_id)
        if not rows:
            return "未查询到成绩数据"
        lines = []
        for r in rows:
            fail_tag = " [挂科]" if r.get("failed") == 1 else ""
            lines.append(f"- {r['subject']}：{r['score']}分{fail_tag}")
        return "\n".join(lines)

    @tool
    def query_consumption() -> str:
        """查询当前学生的月度消费明细。返回各类别的消费总额和笔数。"""
        rows = query_consumption_from_db(student_id)
        if not rows:
            return "未查询到消费数据"
        lines = []
        total = 0
        for r in rows:
            lines.append(f"- {r['category']}：{r['total']:.1f}元（{r['cnt']}笔）")
            total += r['total']
        lines.append(f"合计：{total:.1f}元")
        return "\n".join(lines)

    @tool
    def query_iot_data() -> str:
        """查询自习室IoT传感器数据。返回各楼层各时段的人流量、CO2浓度、温度。"""
        rows = query_iot_from_db()
        if not rows:
            return "未查询到IoT数据"
        lines = []
        for r in rows[:15]:
            lines.append(f"- {r['floor']}楼 {r['hour']}时：人流{r['traffic']}，CO2 {r['co2']}ppm，温度{r['temp']}°C")
        return "\n".join(lines)

    @tool
    def search_policy(query: str) -> str:
        """根据关键词搜索校园政策校规。输入搜索关键词，返回相关校规条文。"""
        hits = query_policy_from_db(query)
        if not hits:
            return "未找到相关校规"
        return "\n".join([f"- {h}" for h in hits])

    return [query_grades, query_consumption, query_iot_data, search_policy]


# ===================== Part 4: Agent 工厂 =====================
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
    创建校园规划 LangChain Agent（LangChain 1.x / LangGraph）。

    Args:
        student_id: 学生ID

    Returns:
        CompiledStateGraph，可调用 .invoke({"messages": [...]})
    """
    llm = get_llm()
    tools = create_tools(student_id)
    agent = create_agent(llm, tools=tools, system_prompt=SYSTEM_PROMPT)
    return agent


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
    agent = create_campus_agent(student_id)

    # 构建消息列表：历史 + 当前输入
    messages = []

    # 从 AgentMemory 加载历史对话
    if agent_memory:
        history = agent_memory.get_history(n=8)
        for msg in history:
            role = msg.get("role", "human")
            content = msg.get("content", "")
            if role == "human":
                messages.append(HumanMessage(content=content))
            elif role == "ai":
                messages.append(AIMessage(content=content))

    # 添加当前输入
    messages.append(HumanMessage(content=prompt))

    try:
        result = agent.invoke({"messages": messages})

        # 提取最后一条 AI 消息
        output = ""
        if "messages" in result:
            for msg in reversed(result["messages"]):
                if hasattr(msg, "content") and msg.content:
                    output = msg.content
                    break

        if not output:
            output = str(result)

        # 保存交互到 AgentMemory
        if agent_memory:
            agent_memory.add_interaction("human", prompt)
            agent_memory.add_interaction("ai", output)

        return output

    except Exception as e:
        logger.error(f"LangChain Agent 执行失败: {e}")
        return f"规划生成失败: {str(e)}"
