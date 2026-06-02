import os
import traceback
from openai import OpenAI
from dotenv import load_dotenv

# 加载环境变量
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(CURRENT_DIR, ".env")
load_dotenv(env_path)

# 接口配置
SENSENOVA_API_KEY = os.getenv("SENSENOVA_API_KEY")
BASE_URL = "https://token.sensenova.cn/v1"
MODEL_ID = "sensenova-6.7-flash-lite"

# 密钥校验
if not SENSENOVA_API_KEY:
    raise EnvironmentError(f"❌ 未读取到 SENSENOVA_API_KEY，请检查 {env_path} 文件")

# 全局客户端
_client = OpenAI(
    api_key=SENSENOVA_API_KEY,
    base_url=BASE_URL,
    timeout=30
)

def llm(prompt: str) -> str:
    prompt = prompt.strip()
    if not prompt:
        print("[LLM] 输入为空")
        return "输入内容不能为空，请重新输入有效问题或需求。"

    # 截断打印，避免日志刷屏
    print(f"[LLM 发起请求] 提示词片段：{prompt[:200]}...")
    try:
        response = _client.chat.completions.create(
            model=MODEL_ID,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            timeout=30
        )
        if not response.choices:
            print("[LLM] 接口返回空结果")
            return "大模型未返回有效内容"
        
        result = response.choices[0].message.content.strip()
        print(f"[LLM 返回结果] 内容片段：{result[:200]}...")
        return result

    except Exception as e:
        print(f"[LLM 调用失败] 异常信息：{str(e)}")
        traceback.print_exc()  # 打印完整堆栈，定位报错位置
        return f"大模型调用异常：{str(e)}"