"""Streamlit 演示界面：多模型切换、会话历史、执行明细。

启动（项目根目录下）：
    .venv/Scripts/python.exe -m streamlit run src/ui/app.py

多模型：侧边栏列出已配置 Key 的服务商（.env 或 HF Secrets 中），一键切换。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st

from src.agent.graph import build_graph, run
from src.db.engine import DEFAULT_DB_PATH
from src.llm.client import PROVIDERS, LLMClient, resolve_config

st.set_page_config(page_title="数据问答分析 Agent", page_icon="📊", layout="wide")

SAMPLE_QUESTIONS = [
    "上月各订单状态的订单数量和总金额",
    "最近30天销量最高的10个商品及其所属类目",
    "本月哪些城市的用户下单最多？取前5名",
    "各支付方式的订单占比",
    "评价平均分最低的5个商品及其差评关键词",
]


def available_providers() -> list[str]:
    """列出已配置 API Key 的服务商（通用 LLM_API_KEY 也算）。"""
    names = []
    for name, p in PROVIDERS.items():
        if os.getenv("LLM_API_KEY") or os.getenv(p.key_env):
            names.append(name)
    return names


@st.cache_resource(show_spinner=False)
def load_graph(provider: str, model: str | None, use_selection: bool):
    config = resolve_config(provider=provider, model=model or None)
    client = LLMClient(config)
    return build_graph(
        client=client, use_table_selection=use_selection
    ), f"{config.provider}/{config.model}"


# ---------- 启动前确保业务库存在（部署环境首次启动自动生成，约 1~2 分钟） ----------
if not Path(DEFAULT_DB_PATH).exists():
    with st.spinner("首次启动：正在生成业务演示库（约 1~2 分钟，仅此一次）…"):
        from data.generator import generate

        generate(DEFAULT_DB_PATH, scale=float(os.getenv("DEMO_SCALE", "1.0")))

# ---------- 侧边栏：模型切换与高级选项 ----------
with st.sidebar:
    st.header("⚙️ 模型配置")
    providers = available_providers()
    if not providers:
        st.error("未检测到任何 API Key，请在 .env 中配置 LLM_API_KEY 或 <服务商>_API_KEY")
        st.stop()
    provider = st.selectbox(
        "服务商", providers, index=providers.index("deepseek") if "deepseek" in providers else 0
    )
    model_override = st.text_input("模型名（留空用默认）", value="")
    use_selection = st.checkbox(
        "动态 schema 裁剪",
        value=False,
        help="大 schema 省 Token；当前 14 表场景实测会掉准确率，默认关闭",
    )
    st.divider()
    st.caption(
        "架构：LangGraph 状态机\n\n"
        "理解 → 选表 → 生成 SQL → 只读沙箱执行\n\n"
        "→ 规则自检 →（不通过带反馈回炉）→ 结论"
    )

graph, model_label = load_graph(provider, model_override.strip() or None, use_selection)

# ---------- 会话历史 ----------
if "history" not in st.session_state:
    st.session_state.history = []

st.title("📊 数据问答分析 Agent")
st.caption(f"自然语言提问 → SQL 生成 → 沙箱执行 → 中文结论｜当前模型：{model_label}")

with st.expander("💡 试试这些示例问题"):
    for i in range(0, len(SAMPLE_QUESTIONS), 2):
        cols = st.columns(2)
        for col, q in zip(cols, SAMPLE_QUESTIONS[i : i + 2], strict=False):
            col.button(q, on_click=lambda q=q: st.session_state.update(pending=q))

question = st.text_input(
    "输入你的分析问题",
    value=st.session_state.get("pending", ""),
    key="question_input",
    placeholder="例如：上月各订单状态的订单数量和总金额",
)

if question:
    with st.spinner("Agent 正在分析…"):
        state = run(graph, question)

    st.subheader("结论")
    st.markdown(state.get("answer", "（无输出）"))

    if state.get("error"):
        st.error("SQL 执行出错，最终结果不可用。")

    with st.expander("🔍 执行明细"):
        attempts = state.get("attempts", 1)
        if attempts > 1:
            st.success(f"🔄 自纠错生效：共执行 {attempts} 轮后成功")
        if state.get("feedback"):
            st.info(f"**最后一轮自检反馈**：{state['feedback']}")
        if state.get("expanded_question") != state.get("question"):
            st.markdown(f"**问题改写**：{state['expanded_question']}")
        st.code(state.get("sql", ""), language="sql")
        if state.get("rows"):
            df = pd.DataFrame(state["rows"], columns=state["columns"])
            st.dataframe(df, use_container_width=True, height=320)
            if state.get("truncated"):
                st.warning(f"结果超过行数上限，仅展示前 {len(df)} 行。")
        else:
            st.info("查询结果为空。")

    st.session_state.history.append(
        {"question": question, "answer": state.get("answer", ""), "attempts": attempts}
    )

if st.session_state.history:
    with st.expander(f"🕘 会话历史（{len(st.session_state.history)} 条）"):
        for h in reversed(st.session_state.history):
            st.markdown(f"**Q：{h['question']}**（{h['attempts']} 轮）")
            st.markdown(h["answer"].split("\n")[0])
            st.divider()
