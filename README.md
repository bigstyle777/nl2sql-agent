# nl2sql-agent

基于 LangGraph 的 Text-to-SQL 数据分析 Agent：自然语言提问 → SQL 生成 → 沙箱执行 → 自纠错重试 → 图表与结论输出，配套自建评测集与量化对比报告。

> 规划文档见 [PLAN.md](PLAN.md)。当前进度：M1（最小闭环）✅

## 快速开始

```bash
# 1. 创建环境（Python 3.11）
py -3.11 -m venv .venv
.venv\Scripts\activate

# 2. 安装依赖
pip install -e ".[dev]"

# 3. 配置 LLM Key
copy .env.example .env   # 填入你的 API Key

# 4. 生成业务演示库
python data/generator.py

# 5. 冒烟测试 LLM 连通性
python scripts/smoke_llm.py "上月各品类销售额是多少"

# 6. 启动 Web 界面
python -m streamlit run src/ui/app.py
```

## 目录结构

```
src/agent    LangGraph 状态图与各节点
src/llm      LLM 统一调用层（多模型适配点）
src/db       连接管理、schema 获取与裁剪、安全控制
src/eval     评测脚本与归因工具
data         业务库数据生成脚本
evals        评测集与回归报告
```
