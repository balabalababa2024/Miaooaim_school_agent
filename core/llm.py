import os
from openai import OpenAI
from dotenv import load_dotenv

# 1. 强制加载当前目录下的 .env
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(CURRENT_DIR, ".env")

# 加载环境变量
load_dotenv(env_path)

# 2. 读取 API Key
api_key = os.getenv("SENSENOVA_API_KEY")

if not api_key:
    raise ValueError(f"❌ 未在 .env 中找到 SENSENOVA_API_KEY，路径：{env_path}")

# 3. 初始化客户端（兼容 OpenAI 格式）
client = OpenAI(
    api_key=api_key,
    base_url="https://token.sensenova.cn/v1"
)

MODEL_ID = "sensenova-6.7-flash-lite"

def llm(prompt: str) -> str:
    if not prompt or len(prompt.strip()) == 0:
        return "输入不能为空"
    
    try:
        resp = client.chat.completions.create(
            model=MODEL_ID,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,  # 越低越稳定、越确定
            timeout=30
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"大模型调用失败：{str(e)}"