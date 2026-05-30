from ..llm import llm
from ..memory import GlobalMemory

# 数据库向量检索依赖（自动走 PostgreSQL）
import os
import psycopg2
from pgvector.psycopg2 import register_vector
from sentence_transformers import SentenceTransformer

# 强制国内镜像，不卡不超时
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

# ===================== 【你的数据库配置】 =====================
DB_CONFIG = {
    "dbname": "rag_db",
    "user": "postgres",
    "password": "123456",  # 改成你自己的密码
    "host": "localhost",
    "port": 5432
}
# ==============================================================

# 加载模型（全局一次）
model = SentenceTransformer("moka-ai/m3e-small")

# 数据库连接（全局一次）
conn = psycopg2.connect(**DB_CONFIG)
conn.autocommit = True
register_vector(conn)
cur = conn.cursor()

# ===================== 【真正语义检索】 =====================
def search_rules(query, top_k=3):
    q_vec = model.encode(query)
    cur.execute('''
        SELECT content, embedding <=> %s AS distance
        FROM school_rules
        ORDER BY embedding <=> %s
        LIMIT %s;
    ''', (q_vec, q_vec, top_k))
    results = cur.fetchall()
    return [{"text": row[0], "score": 1 - row[1]} for row in results]

# ===================== 你的 PolicyAgent =====================
class PolicyAgent:
    name = "policy"
    display = "政策合规智能体"

    def __init__(self):
        # 不再用旧的 store，直接走 PostgreSQL
        self.g = GlobalMemory.instance()

    def constraints(self):
        return {
            "study_room_close": 22.5,
            "lights_out": 23.0,
            "scholarship_gpa": 85,
            "utility_cap": 130
        }

    def analyze(self):
        return {
            "constraints": self.constraints(),
            "narrative": "已加载校规约束"
        }

    def validate(self, state):
        return []

    def ask(self, question):
        # ===================== 关键替换 =====================
        # 从 PostgreSQL 查询，真正语义匹配
        hits = search_rules(question, top_k=3)
        # ====================================================

        if not hits:
            return {"answer": "未查询到相关政策"}

        context = "\n".join([h["text"] for h in hits])
        answer = llm(f"校规：{context}\n问题：{question}\n直接回答")
        return {
            "answer": answer,
            "sources": [h["text"] for h in hits]
        }