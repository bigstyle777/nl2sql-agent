"""执行节点：在只读连接上运行生成的 SQL。"""

from __future__ import annotations

from src.db.engine import QueryResult, run_sql

from ..state import AgentState


def make_execute_node(conn):
    def execute(state: AgentState) -> dict:
        try:
            result: QueryResult = run_sql(conn, state["sql"])
        except Exception as err:  # M1：出错直接透传，M2 在此接入自纠错循环
            return {"error": f"{type(err).__name__}: {err}"}
        return {
            "columns": result.columns,
            "rows": result.rows,
            "truncated": result.truncated,
            "error": "",
        }

    return execute
