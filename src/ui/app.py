"""Streamlit 演示界面。

启动（项目根目录下）：
    .venv/Scripts/python.exe -m streamlit run src/ui/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st

from src.agent.graph import build_graph, run

st.set_page_config(page_title="数据问答分析 Agent", page_icon="📊", layout="wide")

SAMPLE_QUESTIONS = [
    "上月各订单状态的订单数量和总金额",
    "最近30天销量最高的10个商品及其所属类目",
    "本月哪些城市的用户下单最多？取前5名",
    "各支付方式的订单占比",
    "评价平均分最低的5个商品及其差评关键词",
]


@st.cache_resource(show_spinner=False)
def load_graph():
    return build_graph()


st.title("📊 数据问答分析 Agent")
st.caption("自然语言提问 → SQL 生成 → 沙箱执行 → 中文结论（LangGraph + DeepSeek）")

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
    graph = load_graph()
    with st.spinner("Agent 正在分析…"):
        state = run(graph, question)

    st.subheader("结论")
    st.markdown(state.get("answer", "（无输出）"))

    if state.get("error"):
        st.error("SQL 执行出错，最终结果不可用。")

    with st.expander("🔍 执行明细"):
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
