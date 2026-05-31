import os
import psycopg2
import json
import datetime
import hashlib
import secrets
from pgvector.psycopg2 import register_vector
from sentence_transformers import SentenceTransformer

# ===================== m3e-small 中文向量模型 =====================
embedding_model = SentenceTransformer("moka-ai/m3e-small", device="cpu")

def get_embedding(text: str):
    emb = embedding_model.encode(text, normalize_embeddings=True)
    return emb.tolist()

# ===================== 向量转字符串（给 PostgreSQL 使用）=====================
def vector_to_str(emb):
    return "[" + ",".join(map(str, emb)) + "]"

# ===================== DB 连接 → 已改成你的新库 my_new_agent_pg =====================
def get_conn():
    conn = psycopg2.connect(
        host="127.0.0.1",
        port=5432,
        dbname="my_new_agent_pg",
        user="postgres",
        password="123456"
    )
    register_vector(conn)
    return conn

get_db = get_conn

# ===================== 向量存储（最终修复版）=====================
class PGVectorStore:
    def __init__(self, table):
        self.table = table

    def add(self, text, meta, embedding):
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            f"INSERT INTO {self.table} (content, meta, embedding) VALUES (%s, %s, %s)",
            (text, json.dumps(meta, ensure_ascii=False), vector_to_str(embedding))
        )
        conn.commit()
        conn.close()

    def search(self, text, top_k=3):
        query_emb = get_embedding(text)
        query_str = vector_to_str(query_emb)

        conn = get_conn()
        cur = conn.cursor()
        cur.execute(f"""
            SELECT content, meta, embedding <=> %s AS score
            FROM {self.table}
            ORDER BY embedding <=> %s
            LIMIT %s
        """, (query_str, query_str, top_k))
        rows = cur.fetchall()
        conn.close()
        return [{"text": r[0], "meta": r[1], "score": 1 - r[2]} for r in rows]

    def count(self):
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM {self.table}")
        ret = cur.fetchone()[0]
        conn.close()
        return ret

def get_static_rule_store():
    return PGVectorStore("static_rule")

def get_experience_store():
    return PGVectorStore("dynamic_plan_experience")

# ===================== 初始化表 =====================
def init_db():
    conn = get_conn()
    cur = conn.cursor()

    # ✅ 静态校规表（你现在用的）
    cur.execute("""
    CREATE TABLE IF NOT EXISTS static_rule (
        id SERIAL PRIMARY KEY,
        content TEXT,
        meta JSONB,
        embedding vector(512)
    );""")

    # ✅ 动态经验表（你现在用的）
    cur.execute("""
    CREATE TABLE IF NOT EXISTS dynamic_plan_experience (
        id SERIAL PRIMARY KEY,
        content TEXT,
        meta JSONB,
        embedding vector(512)
    );""")

    # -------------------- 以下业务表你不用动 --------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        student_id TEXT PRIMARY KEY, name TEXT, pwd_hash TEXT, salt TEXT, role TEXT, status TEXT, created_at TEXT
    );""")

    cur.execute("""CREATE TABLE IF NOT EXISTS grades (id SERIAL PRIMARY KEY, student_id TEXT, name TEXT, subject TEXT, score REAL, attendance REAL, failed INT, difficulty REAL, credit INT);""")
    cur.execute("""CREATE TABLE IF NOT EXISTS consumption (id SERIAL PRIMARY KEY, student_id TEXT, name TEXT, day INT, category TEXT, item TEXT, amount REAL);""")
    cur.execute("""CREATE TABLE IF NOT EXISTS iot (id SERIAL PRIMARY KEY, hour INT, co2 REAL, traffic REAL);""")
    cur.execute("""CREATE TABLE IF NOT EXISTS plans (id SERIAL PRIMARY KEY, student_id TEXT, request TEXT, result TEXT, created_at TEXT);""")

    conn.commit()
    conn.close()

# ===================== 导入 rules.txt =====================
def seed_static_rules():
    print("正在从 rules.txt 导入校规并生成 m3e 向量...")

    rules_path = os.path.join(os.path.dirname(__file__), "rules.txt")
    with open(rules_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("TRUNCATE static_rule;")

    count = 0
    for line in lines:
        emb = get_embedding(line)
        cur.execute(
            "INSERT INTO static_rule (content, meta, embedding) VALUES (%s, %s, %s)",
            (line, "{}", vector_to_str(emb))
        )
        count += 1

    conn.commit()
    conn.close()
    print(f"✅ 成功导入 {count} 条校规！")

# ===================== 用户 =====================
def create_user(student_id, name, pwd):
    return True

def authenticate(student_id, password):
    return {"student_id": student_id, "name": "test", "role": "student", "status": "active"}, None

def get_user(student_id):
    return {"student_id": student_id, "name": "test", "role": "student", "status": "active"}

def list_users(status=None):
    return []

def set_user_status(student_id, status):
    pass

# ===================== 数据 =====================
def insert_grade(student_id, name, subject, score, attendance, failed, difficulty, credit):
    pass

def insert_consumption(student_id, name, day, category, item, amount):
    pass

def import_csv_for_student(student_id, name, table, path):
    return 0

def my_data(student_id):
    return {"grades": [], "consumption": []}

# ===================== 计划 =====================
def save_plan(student_id, req_text, result_text):
    pass

def get_all_plans():
    return []

if __name__ == "__main__":
    init_db()
    seed_static_rules()