"""LangGraph 状态图：理解 → 生成 SQL → 执行 → 回答（M1 最小闭环，M2 在此接入纠错循环）。"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from langgraph.graph import END, START, StateGraph

from src.db import engine

from .nodes.answer import make_answer_node
from .nodes.execute import make_execute_node
from .nodes.generate_sql import make_generate_sql_node
from .nodes.understand import make_understand_node
from .state import AgentState

load_dotenv()


def build_graph(client=None, db_path: Path | str | None = None, conn=None):
    """组装 Agent 图。client/conn 支持注入，便于测试时替换为假实现。"""
    if client is None:
        from src.llm.client import LLMClient

        client = LLMClient()
    if conn is None:
        conn = engine.connect(db_path or os.getenv("DB_PATH", engine.DEFAULT_DB_PATH))

    ddl = engine.get_ddl(conn)
    data_range = engine.get_data_time_range(conn)
    bootstrap = {"ddl": ddl, "data_range": data_range}

    builder = StateGraph(AgentState)
    builder.add_node("understand", make_understand_node(client))
    builder.add_node("generate_sql", make_generate_sql_node(client))
    builder.add_node("execute", make_execute_node(conn))
    builder.add_node("answer", make_answer_node(client))

    builder.add_edge(START, "understand")
    builder.add_edge("understand", "generate_sql")
    builder.add_edge("generate_sql", "execute")
    builder.add_edge("execute", "answer")
    builder.add_edge("answer", END)

    graph = builder.compile()
    graph._bootstrap = bootstrap  # 供调用方合并进初始状态
    return graph


def run(graph, question: str) -> AgentState:
    """执行一次完整问答，返回最终状态。"""
    return graph.invoke({"question": question, **graph._bootstrap})
