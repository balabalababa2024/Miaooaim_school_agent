# core/agents/__init__.py
from .academic import AcademicAgent
from .logistics import LogisticsAgent
from .study_env import StudyEnvAgent
from .policy import PolicyAgent
from .master import MasterAgent

# 统一顶层导入，子模块内部自行导入依赖
__all__ = [
    "AcademicAgent",
    "LogisticsAgent",
    "StudyEnvAgent",
    "PolicyAgent",
    "MasterAgent"
]