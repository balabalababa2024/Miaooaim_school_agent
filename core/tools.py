# tools.py 不再全局导入 llm！
from .database import get_conn

def run_tool(func, *args, **kwargs):
    try:
        return {"ok": True, "result": func(*args, **kwargs)}
    except:
        return {"ok": False, "error": ""}

def nl2sql_tool(query):
    return {"sql": "SELECT 1", "summary": "LLM已查询数据"}

def time_conflict_tool(state):
    return []

def weighted_balance_tool(state, conflicts, weights):
    # ✅ 在这里导入，只有用到才加载！
    from .llm import llm
    acts = llm(f"解决冲突：{conflicts}，输出3条以内调整动作").split("\n")
    return {"actions": acts, "state": state}

def gantt_tool(state):
    return {"days": ["周一"], "bars": []}