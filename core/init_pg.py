import sys
from pathlib import Path

# 把项目根目录加入 Python 路径
sys.path.append(str(Path(__file__).parent.parent))

# 现在可以正常导入了
from core.database import init_db, seed_static_rules

if __name__ == "__main__":
    print("初始化 PostgreSQL...")
    init_db()
    print("✅ 表创建完成")

    print("导入校规向量...")
    seed_static_rules()
    print("✅ 全部完成！")