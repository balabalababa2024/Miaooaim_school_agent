import os
import psycopg2
from psycopg2.extras import execute_values
from pgvector.psycopg2 import register_vector

# ---------- 关键：强制走国内镜像，解决下载超时 ----------
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

from sentence_transformers import SentenceTransformer

# ===================== 数据库配置（已经改成你的新库）=====================
DB_CONFIG = {
    "dbname": "my_new_agent_pg",    # 你的新库
    "user": "postgres",
    "password": "123456",
    "host": "localhost",
    "port": 5432
}
# =========================================================================

# 加载向量模型
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

# 先创建唯一索引（修复报错关键！）
cur.execute('''
CREATE UNIQUE INDEX IF NOT EXISTS idx_static_rule_content
ON static_rule (content);
''')

# 2. 读取并向量化 rules.txt
rules = load_rules()
if not rules:
    print("⚠️ rules.txt 中没有校规内容")
    cur.close()
    conn.close()
    exit()

print("✅ 正在生成向量...")
vectors = model.encode(rules)
data = list(zip(rules, vectors))

# 3. 批量插入 static_rule
insert_sql = '''
INSERT INTO static_rule (content, embedding)
VALUES %s
ON CONFLICT (content) DO NOTHING;
'''
execute_values(cur, insert_sql, data, page_size=100)

print(f"✅ 导入完成！共 {len(rules)} 条校规已存入 my_new_agent_pg → static_rule")

# 4. 测试语义查询
def search(query, top_k=3):
    q_vec = model.encode(query)
    cur.execute('''
        SELECT content, embedding <=> %s AS distance
        FROM static_rule
        ORDER BY embedding <=> %s
        LIMIT %s;
    ''', (q_vec, q_vec, top_k))
    return cur.fetchall()

# 测试
print("\n" + "="*50)
print("🔍 测试：划船？")
result = search("划船")
for content, dist in result:
    print(f"📌 匹配度：{1-dist:.2f} | {content}")

cur.close()
conn.close()