# test_vector.py
from embedding import get_embedding  # 直接导入你的向量函数

# 1. 输入一句话
text = "自习室晚上22点关门"

# 2. 调用向量化（核心！）
vector = get_embedding(text)

# 3. 输出结果
print("✅ 向量化成功！")
print("文本：", text)
print("向量长度：", len(vector))  # m3e-small 输出 512 维
print("向量前10个数字：", vector[:10])