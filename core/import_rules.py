import os
import psycopg2
from psycopg2.extras import execute_values
from pgvector.psycopg2 import register_vector

# ---------- 关键：强制走国内镜像，解决下载超时 ----------
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

from sentence_transformers import SentenceTransformer

# ===================== 数据库配置（改你自己的密码）=====================
DB_CONFIG = {
    "dbname": "rag_db",
    "user": "postgres",
    "password": "123456",  # <-- 改成你的 PostgreSQL 密码
    "host": "localhost",
    "port": 5432
}
# =========================================================================

# 加载向量模型（国内镜像下载，m3e-small 512维）
model = SentenceTransformer("moka-ai/m3e-small")

# 从 rules.txt 读取校规
def load_rules():
    if not os.path.exists("rules.txt"):
        print("❌ 请在当前目录创建 rules.txt，一行一条校规")
        return []
    with open("rules.txt", "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

# 连接数据库
conn = psycopg2.connect(**DB_CONFIG)
conn.autocommit = True
register_vector(conn)
cur = conn.cursor()

# 1. 开启向量扩展
cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

# 2. 创建向量表
cur.execute('''
CREATE TABLE IF NOT EXISTS school_rules (
    id SERIAL PRIMARY KEY,
    content TEXT NOT NULL,
    embedding vector(512) NOT NULL
);
''')

# 3. 创建唯一索引（去重关键：内容一样就不插入）
cur.execute('''
CREATE UNIQUE INDEX IF NOT EXISTS idx_school_rules_content
ON school_rules (content);
''')

# 4. 读取并向量化
rules = load_rules()
if not rules:
    print("⚠️ rules.txt 中没有校规内容")
    cur.close()
    conn.close()
    exit()

vectors = model.encode(rules)
data = list(zip(rules, vectors))

# 5. 批量插入（ON CONFLICT 自动跳过重复）
insert_sql = '''
INSERT INTO school_rules (content, embedding)
VALUES %s
ON CONFLICT (content) DO NOTHING;
'''
execute_values(cur, insert_sql, data, page_size=100)

print(f"✅ 导入完成！共 {len(rules)} 条（重复自动跳过）")

# 6. 测试语义查询
# 6. 测试语义查询
def search(query, top_k=3):
    q_vec = model.encode(query)
    cur.execute('''
        SELECT content, embedding <=> %s AS distance
        FROM school_rules
        ORDER BY embedding <=> %s
        LIMIT %s;
    ''', (q_vec, q_vec, top_k))
    return cur.fetchall()

# 测试
print("\n" + "="*50)
print("🔍 测试查询：划船？")
result = search("划船？")
for content, dist in result:
    print(f"📌 匹配度：{1-dist:.2f} | {content}")

cur.close()
conn.close()