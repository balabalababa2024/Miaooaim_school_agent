# core/llm.py
import os
from openai import OpenAI
from dotenv import load_dotenv

# 1. 强制锁定：当前文件所在目录下的 .env
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(CURRENT_DIR, ".env")

# 2. 加载前先打印调试，看是否真的找到了
print("尝试加载 .env：", env_path)
print("文件存在？", os.path.exists(env_path))

# 3. 显式传路径，不要用默认
load_dotenv(env_path)

# 4. 读变量并打印
api_key = os.getenv("SENSENOVA_API_KEY")
print("拿到的 key 前10位：", repr(api_key[:10] if api_key else None))

if not api_key:
    raise ValueError(f"❌ 未找到 SENSENOVA_API_KEY，路径：{env_path}")

client = OpenAI(
    api_key=api_key,
    base_url="https://token.sensenova.cn/v1"
)

MODEL_ID = "sensenova-6.7-flash-lite"

def llm(prompt: str) -> str:
    try:
        resp = client.chat.completions.create(
            model=MODEL_ID,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"商汤调用失败：{str(e)}"