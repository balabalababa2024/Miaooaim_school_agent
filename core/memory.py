"""
三级隔离记忆体系
================
1. GlobalMemory   全局共享记忆：全体 Agent 共享公共基础数据（考试时间表、自习室开放时段、
                  食堂菜品定价、全校统一校规），进程级持久（落 JSON）。
2. AgentMemory    Agent 私有记忆：每个垂直 Agent 独立私有存储，互不干扰（落 JSON）。
3. ScratchMemory  单次任务临时记忆：仅当前一轮规划博弈任务生效，任务结束自动清空。
"""
import json
import os
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(__file__))
MEM_DIR = os.path.join(BASE, "data", "memory")


def _ensure():
    os.makedirs(MEM_DIR, exist_ok=True)


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class _JsonMemory:
    def __init__(self, name):
        _ensure()
        self.path = os.path.join(MEM_DIR, f"{name}.json")
        self.data = {}
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as f:
                self.data = json.load(f)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self._flush()

    def _flush(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def all(self):
        return dict(self.data)


class GlobalMemory(_JsonMemory):
    """全局共享记忆，单例。"""
    _inst = None

    @classmethod
    def instance(cls):
        if cls._inst is None:
            cls._inst = GlobalMemory("global_shared")
            cls._inst._bootstrap()
        return cls._inst

    def _bootstrap(self):
        if self.data:
            return
        self.set("exam_week", 16)
        self.set("study_room_open", [6.5, 22.5])   # 6:30 - 22:30
        self.set("dorm_lights_out", 23.0)          # 23:00 熄灯
        self.set("scholarship_gpa_threshold", 85)
        self.set("recommended_utility_cap", 130)


class AgentMemory(_JsonMemory):
    """Agent 私有记忆，按 agent 名隔离文件。支持交互历史。"""
    def __init__(self, agent_name):
        super().__init__(f"agent_{agent_name}")

    def add_interaction(self, role, content):
        """记录一次交互（供 LangChain 恢复上下文）"""
        history = self.get("history", [])
        history.append({
            "role": role,
            "content": content[:500],  # 截断避免文件过大
            "time": _now()
        })
        # 保留最近 50 条
        self.set("history", history[-50:])

    def get_history(self, n=20):
        """获取最近 n 条交互历史"""
        return self.get("history", [])[-n:]

    def save_summary(self, summary):
        """保存一次规划的摘要（长期记忆）"""
        plans = self.get("past_plans", [])
        plans.append({"summary": summary[:300], "time": _now()})
        self.set("past_plans", plans[-20:])

    def get_past_plans(self, n=5):
        """获取最近 n 次规划摘要"""
        return self.get("past_plans", [])[-n:]


class ScratchMemory:
    """单次任务临时记忆，纯内存，任务结束 clear()。"""
    def __init__(self):
        self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value

    def clear(self):
        self.data = {}
