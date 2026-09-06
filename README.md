# nl2sql-agent

基于 LangGraph 的 Text-to-SQL 数据分析 Agent：自然语言提问 → SQL 生成 → 沙箱执行 → 自纠错重试 → 图表与结论输出，配套自建评测集与量化对比报告。

> 规划文档见 [PLAN.md](PLAN.md)。当前进度：M4（优化迭代）✅

## 评测驱动的优化数据（120 题自建评测集，deepseek-chat）

| 配置 | 执行准确率 | easy / medium / hard | 平均 Token/题 | 说明 |
|---|---|---|---|---|
| 基线 | 78.3% | 86.7 / 82.5 / 45.0 | 1420 | 全量 DDL，无提示 |
| +schema 语义增强 | **87.5%** | 100 / 87.5 / 50.0 | 1773 | 枚举值 + 日期惯用写法提示 |
| +动态 schema 裁剪 | 83.3% | 98.3 / 85.0 / 35.0 | 1532 | token -13.6% 但准确率 -4.2pt，14 表场景不划算，默认关闭 |

两轮关键教训（详见报告 `evals/reports/`）：
- 提示词注入的领域知识必须是**纯描述**——"异常值请清洗"类建议性措辞会诱导模型自行改变统计口径，反而掉 3.3 个点（`opt1-hints_*.json`）；
- 动态裁剪在 14 表小 schema 下，选表调用本身的开销 ≈ DDL 节省量，且漏选伤准确率；该能力保留为开关（`--selection`），大 schema 场景再启用。

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
