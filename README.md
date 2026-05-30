# 校园多智能体综合生活学业协同规划平台

面向在校大学生的**多智能体博弈协同规划平台**：一句自然语言复合需求（如「期末冲刺高数，
预算每月吃饭1000，想要环境好的自习室，不能违反宿舍熄灯规定」），系统自动拆解约束、
驱动 4 个垂直 Agent 生成方案、多轮博弈协商消解冲突、输出全局均衡规划方案。

> 纯 Python 实现，零外部服务依赖，VSCode 里一条命令即可运行，自带美观可视化前端。

## 快速开始

```bash
cd campus_agent
pip install -r requirements.txt
python app.py
```

浏览器打开 **http://127.0.0.1:5000**，在「智能规划」页输入需求并点击启动即可。

VSCode 用户：直接打开 `campus_agent` 文件夹，右上角 ▶ 运行 `app.py` 即可。

## 技术亮点（对应简历）

| 能力 | 实现位置 |
|------|----------|
| ① CoT 思维链复杂需求拆解 | `core/supervisor.py` `decompose()` |
| ② 多智能体多轮博弈协商（时间片冲突检测+加权均衡，最多3轮） | `core/supervisor.py` `plan()` + `core/tools.py` |
| ③ 三级隔离记忆（全局共享/Agent私有/单次任务临时） | `core/memory.py` |
| ④ 任务复盘 + 动态经验自进化（案例向量化，同类需求直接复用，越用越快） | `core/supervisor.py` `try_reuse/_reflect_and_store` |
| ⑤ 多工具自主编排 + 失败重试（NL2SQL/冲突检测/加权均衡/甘特图） | `core/tools.py` `run_tool()` |

## 四大垂直 Agent

- **学业风险分析** `core/agents/academic.py`：成绩波动+挂科+难度加权算风险分，输出保守/冲刺两套带时间约束的复习方案。
- **自习环境研判** `core/agents/study_env.py`：基于 CO₂/人流时序传感数据算舒适度，生成 3 套错峰选址方案。
- **校园后勤消费** `core/agents/logistics.py`：消费数据分析，按预算生成省钱搭配+水电节能，输出每日餐饮上限约束。
- **校园政策咨询** `core/agents/policy.py`：静态政策向量库 RAG 检索，下发硬性约束（关闭/熄灯时间、奖学金门槛）并做合规校验。

## 数据与存储

- `data/*.csv`：4 类样本数据集（学业成绩时序 / 自习室 IoT / 食堂水电消费），结构对齐真实公开数据集字段。
  **接入真实数据**：把同名 CSV（字段一致）放入 `data/` 覆盖即可（删 `data/campus.db` 后重启重新导入）。
- SQLite (`data/campus.db`)：替代 MySQL，存成绩/自习/消费/规划历史，NL2SQL 直接查真实表。
- 轻量向量库（词袋余弦，`data/vec_*.json`）：替代 PostgreSQL+pgvector，物理分两表
  `static_rule`（静态校规）与 `dynamic_plan_experience`（动态经验，自进化）。

## 与企业版的差异说明

原始设计为 Java 中台 + Python LangGraph + Vue3 + MySQL/PostgreSQL/Redis + Docker 双服务架构。
本落地版在**完整保留所有 Agent 算法与技术点**的前提下，为「VSCode 一键运行 + 美观前端」做了等价轻量化：
Flask+原生前端替代双服务，SQLite/JSON 向量库替代重数据库，显式状态机等价 LangGraph 循环博弈编排。
核心算法（风险评分、时间片冲突检测、加权均衡、三级记忆、经验自进化）均为真实实现。

## 目录结构

```
campus_agent/
├── app.py                  # Flask 入口 + REST API
├── requirements.txt
├── core/
│   ├── seed_data.py        # 样本数据生成
│   ├── database.py         # SQLite + 轻量向量库
│   ├── memory.py           # 三级隔离记忆
│   ├── tools.py            # 四大工具 + 失败重试
│   ├── supervisor.py       # 顶层总控（CoT/博弈/经验自进化）
│   └── agents/             # 四大垂直 Agent
├── templates/index.html    # 前端单页
├── static/style.css
└── static/app.js
```
