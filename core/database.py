"""
底层数据存储层
==============
- SQLite 替代 MySQL：存学生成绩时序、自习 IoT、消费账单、规划历史（NL2SQL 直接查真实表）。
- 轻量向量库（纯 Python 词袋余弦）替代 PostgreSQL+pgvector，物理分两表：
    static_rule            —— 静态校规政策知识库
    dynamic_plan_experience —— 动态博弈规划经验库（自进化）
"""
import hashlib
import math
import os
import re
import secrets
import sqlite3
import json
import datetime
import pandas as pd

from . import seed_data

BASE = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE, "data", "campus.db")


# ---------------------------------------------------------------- SQLite ----
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(force=False):
    """生成样本数据 → 建表 → 批量导入 CSV。"""
    seed_data.ensure_all()
    if force and os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    fresh = not os.path.exists(DB_PATH)
    conn = get_conn()
    if fresh:
        _load_csv(conn, "students_grades.csv", "grades")
        _load_csv(conn, "study_room_iot.csv", "iot")
        _load_csv(conn, "consumption.csv", "consumption")
    conn.execute("""CREATE TABLE IF NOT EXISTS plan_history(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id TEXT, request TEXT, created_at TEXT,
        final_plan TEXT, rounds INTEGER, reused INTEGER DEFAULT 0)""")
    # 用户表：学号+盐哈希密码，role(student/admin)，status(pending/active/rejected)
    conn.execute("""CREATE TABLE IF NOT EXISTS users(
        student_id TEXT PRIMARY KEY, name TEXT, pwd_hash TEXT, salt TEXT,
        role TEXT DEFAULT 'student', status TEXT DEFAULT 'pending', created_at TEXT)""")
    conn.commit()
    # 播种默认管理员（首次）
    if not conn.execute("SELECT 1 FROM users WHERE student_id='admin'").fetchone():
        salt = secrets.token_hex(16)
        conn.execute(
            "INSERT INTO users(student_id,name,pwd_hash,salt,role,status,created_at)"
            " VALUES(?,?,?,?,?,?,?)",
            ("admin", "系统管理员", hash_pwd("admin123", salt), salt,
             "admin", "active", _now()))
        conn.commit()
    conn.close()


def _now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# --------------------------------------------------- 密码哈希（标准库） ----
def hash_pwd(password, salt):
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000).hex()


def verify_pwd(password, salt, pwd_hash):
    return secrets.compare_digest(hash_pwd(password, salt), pwd_hash)


# ------------------------------------------------------------- 用户管理 ----
def create_user(student_id, name, password):
    """注册：状态 pending，等待管理员审核。学号已存在则返回 False。"""
    conn = get_conn()
    try:
        if conn.execute("SELECT 1 FROM users WHERE student_id=?", (student_id,)).fetchone():
            return False
        salt = secrets.token_hex(16)
        conn.execute(
            "INSERT INTO users(student_id,name,pwd_hash,salt,role,status,created_at)"
            " VALUES(?,?,?,?,?,?,?)",
            (student_id, name, hash_pwd(password, salt), salt, "student", "pending", _now()))
        conn.commit()
        return True
    finally:
        conn.close()


def get_user(student_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE student_id=?", (student_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_users(status=None):
    conn = get_conn()
    if status:
        rows = conn.execute(
            "SELECT student_id,name,role,status,created_at FROM users "
            "WHERE status=? ORDER BY created_at DESC", (status,)).fetchall()
    else:
        rows = conn.execute(
            "SELECT student_id,name,role,status,created_at FROM users "
            "ORDER BY (status='pending') DESC, created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_user_status(student_id, status):
    conn = get_conn()
    conn.execute("UPDATE users SET status=? WHERE student_id=?", (status, student_id))
    conn.commit()
    conn.close()


def authenticate(student_id, password):
    """返回 (user_dict, error_msg)。校验密码 + 审核状态。"""
    user = get_user(student_id)
    if not user or not verify_pwd(password, user["salt"], user["pwd_hash"]):
        return None, "学号或密码错误"
    if user["status"] == "pending":
        return None, "账号待管理员审核，请稍后再试"
    if user["status"] == "rejected":
        return None, "账号审核未通过，请联系管理员"
    return user, None


# ----------------------------------------------------------- 数据录入 ----
def insert_grade(student_id, name, subject, score, attendance, failed,
                 difficulty, credit, exam_label="录入", term_index=0, exam_week=16):
    conn = get_conn()
    conn.execute(
        "INSERT INTO grades(student_id,name,subject,exam_label,term_index,score,"
        "attendance,failed,difficulty,credit,exam_week) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (student_id, name, subject, exam_label, term_index, score,
         attendance, 1 if failed else 0, difficulty, credit, exam_week))
    conn.commit()
    conn.close()


def insert_consumption(student_id, name, day, category, item, amount):
    conn = get_conn()
    conn.execute(
        "INSERT INTO consumption(student_id,name,day,category,item,amount)"
        " VALUES(?,?,?,?,?,?)",
        (student_id, name, day, category, item, amount))
    conn.commit()
    conn.close()


# 各表允许批量导入的列（防止上传 CSV 注入异常列）
_IMPORT_COLS = {
    "grades": ["subject", "exam_label", "term_index", "score", "attendance",
               "failed", "difficulty", "credit", "exam_week"],
    "consumption": ["day", "category", "item", "amount"],
}


def import_csv_for_student(student_id, name, table, file_path):
    """把上传的 CSV 追加进 grades/consumption，强制归属到当前学生。返回导入行数。"""
    if table not in _IMPORT_COLS:
        raise ValueError(f"不支持的导入表：{table}")
    df = pd.read_csv(file_path)
    keep = [c for c in _IMPORT_COLS[table] if c in df.columns]
    if not keep:
        raise ValueError(f"CSV 缺少有效列，{table} 需要包含：{_IMPORT_COLS[table]}")
    df = df[keep].copy()
    df.insert(0, "student_id", student_id)
    df.insert(1, "name", name)
    conn = get_conn()
    try:
        df.to_sql(table, conn, if_exists="append", index=False)
        conn.commit()
        return len(df)
    finally:
        conn.close()


def my_data(student_id):
    """个人数据中心：返回该学生已录入的成绩与消费明细。"""
    conn = get_conn()
    grades = [dict(r) for r in conn.execute(
        "SELECT subject,exam_label,score,attendance,failed,difficulty,credit "
        "FROM grades WHERE student_id=? ORDER BY subject", (student_id,)).fetchall()]
    consumption = [dict(r) for r in conn.execute(
        "SELECT day,category,item,amount FROM consumption WHERE student_id=? "
        "ORDER BY day", (student_id,)).fetchall()]
    conn.close()
    return {"grades": grades, "consumption": consumption}


def _load_csv(conn, csv_name, table):
    df = pd.read_csv(os.path.join(BASE, "data", csv_name))
    df.to_sql(table, conn, if_exists="replace", index=False)


def save_plan(student_id, request, final_plan, rounds, reused, created_at):
    conn = get_conn()
    conn.execute(
        "INSERT INTO plan_history(student_id,request,created_at,final_plan,rounds,reused)"
        " VALUES(?,?,?,?,?,?)",
        (student_id, request, created_at, json.dumps(final_plan, ensure_ascii=False),
         rounds, 1 if reused else 0))
    conn.commit()
    conn.close()


def list_plans(student_id=None, limit=20):
    conn = get_conn()
    if student_id:
        rows = conn.execute(
            "SELECT * FROM plan_history WHERE student_id=? ORDER BY id DESC LIMIT ?",
            (student_id, limit)).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM plan_history ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --------------------------------------------------- 轻量向量库（词袋余弦） ----
def _tokenize(text):
    """中英文混合分词：英文按词，中文按字 + 相邻 bigram，足够做相似度匹配。"""
    text = text.lower()
    tokens = re.findall(r"[a-z0-9]+", text)
    cjk = re.findall(r"[一-鿿]", text)
    tokens += cjk
    tokens += [cjk[i] + cjk[i + 1] for i in range(len(cjk) - 1)]
    return tokens


def _vectorize(text):
    vec = {}
    for tok in _tokenize(text):
        vec[tok] = vec.get(tok, 0) + 1
    return vec


def _cosine(a, b):
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    dot = sum(a[t] * b[t] for t in common)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


class VectorStore:
    """JSON 持久化的双表向量库。"""

    def __init__(self, table):
        self.table = table
        self.path = os.path.join(BASE, "data", f"vec_{table}.json")
        self.items = []
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as f:
                self.items = json.load(f)

    def _save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.items, f, ensure_ascii=False)

    def add(self, text, meta=None):
        self.items.append({"text": text, "meta": meta or {}, "vec": _vectorize(text)})
        self._save()

    def count(self):
        return len(self.items)

    def search(self, query, top_k=3, threshold=0.0):
        qv = _vectorize(query)
        scored = [(round(_cosine(qv, it["vec"]), 3), it) for it in self.items]
        scored.sort(key=lambda x: x[0], reverse=True)
        out = []
        for score, it in scored[:top_k]:
            if score >= threshold:
                out.append({"score": score, "text": it["text"], "meta": it["meta"]})
        return out


def get_static_rule_store():
    return VectorStore("static_rule")


def get_experience_store():
    return VectorStore("dynamic_plan_experience")


def seed_static_rules():
    """把政策文档按段落切片写入 static_rule 向量库（仅首次）。"""
    store = get_static_rule_store()
    if store.count() > 0:
        return store
    with open(os.path.join(BASE, "data", "policies.md"), encoding="utf-8") as f:
        text = f.read()
    chunks, current_title = [], ""
    for line in text.splitlines():
        if line.startswith("## "):
            current_title = line[3:].strip()
        elif line.strip():
            chunks.append((current_title, line.strip()))
    for title, content in chunks:
        store.add(f"{title}：{content}", meta={"section": title, "content": content})
    return store
