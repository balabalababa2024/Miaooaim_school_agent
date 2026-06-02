import os

# PostgreSQL 向量库配置（你的新库）
PG_CONFIG = {
    "dbname": os.getenv("PG_DATABASE", "my_new_agent_pg"),
    "user": os.getenv("PG_USER", "postgres"),
    "password": os.getenv("PG_PASSWORD", "123456"),
    "host": os.getenv("PG_HOST", "localhost"),
    "port": int(os.getenv("PG_PORT", "5432"))
}

# MySQL 业务库配置（与 app.py 保持一致）
MYSQL_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
    "port": int(os.getenv("MYSQL_PORT", "3306")),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", "123456"),
    "database": os.getenv("MYSQL_DATABASE", "my_agent_db"),
}