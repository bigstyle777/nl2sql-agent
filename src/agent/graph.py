"""LangGraph 状态图：理解 → 生成SQL → 执行 → 自检 →（不通过则带反馈回炉）→ 回答。

M2 自纠错闭环：自检节点发现执行报错或结果可疑（空结果/大小写未归一/全 NULL 列）时，
携带反馈回到生成节点重写 SQL，最多重试 MAX_ATTEMPTS 轮，防止死循环。
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from langgraph.graph import END, START, StateGraph

from src.db import engine

from .nodes.answer import make_answer_node
from .nodes.check import make_check_node
from .nodes.execute import make_execute_node
from .nodes.generate_sql import make_generate_sql_node
from .nodes.understand import make_understand_node
from .state import AgentState

load_dotenv()


def build_graph(
    client=None,
    db_path: Path | str | None = None,
    conn=None,
    max_attempts: int = 3,
    use_hints: bool = True,
    use_table_selection: bool = False,
):
    """组装 Agent 图。client/conn 支持注入，便于测试时替换为假实现。

    消融开关（M4 评测数据见 evals/reports/）：
    - use_hints：schema 语义增强，准确率 78.3% -> 87.5%，默认开启
    - use_table_selection：动态裁剪，token -13.6% 但准确率 -4.2pt（14 表小 schema
      下选表开销与漏选风险大于 DDL 收益），默认关闭；大 schema 场景可开启
    """
    if client is None:
        from src.llm.client import LLMClient

        client = LLMClient()
    if conn is None:
        conn = engine.connect(db_path or os.getenv("DB_PATH", engine.DEFAULT_DB_PATH))

    ddl = engine.get_ddl(conn)
    data_range = engine.get_data_time_range(conn)
    bootstrap = {"ddl": ddl, "data_range": data_range}

    check, route = make_check_node(max_attempts=max_attempts)

    builder = StateGraph(AgentState)
    builder.add_node("understand", make_understand_node(client))
    builder.add_node("generate_sql", make_generate_sql_node(client, use_hints=use_hints))
    builder.add_node("execute", make_execute_node(conn))
    builder.add_node("check", check)
    builder.add_node("answer", make_answer_node(client))

    builder.add_edge(START, "understand")
    if use_table_selection:
        from .nodes.select_tables import make_select_tables_node

        builder.add_node(
            "select_tables", make_select_tables_node(client, engine.get_ddl_by_table(conn))
        )
        builder.add_edge("understand", "select_tables")
        builder.add_edge("select_tables", "generate_sql")
    else:
        builder.add_edge("understand", "generate_sql")
    builder.add_edge("generate_sql", "execute")
    builder.add_edge("execute", "check")
    # 自纠错闭环：check -> generate_sql（重试）或 check -> answer（收尾）
    builder.add_conditional_edges(
        "check", route, {"regenerate": "generate_sql", "finish": "answer"}
    )
    builder.add_edge("answer", END)

    graph = builder.compile()
    graph._bootstrap = bootstrap  # 供调用方合并进初始状态
    return graph


def run(graph, question: str) -> AgentState:
    """执行一次完整问答，返回最终状态。"""
    return graph.invoke({"question": question, **graph._bootstrap})
