"""Agent 共享状态定义。"""

from __future__ import annotations

from typing import TypedDict


class AgentState(TypedDict, total=False):
    question: str  # 用户原始问题
    expanded_question: str  # 理解节点改写后的问题（消解相对时间等）
    ddl: str  # 业务库建表语句
    data_range: str  # 业务数据时间范围，如 "2025-01-01 至 2025-04-29"
    sql: str  # 生成的 SQL
    columns: list[str]  # 结果列名
    rows: list[tuple]  # 结果行
    truncated: bool  # 结果是否被截断
    error: str  # 执行错误信息（空串表示无错误）
    answer: str  # 最终结论文本
