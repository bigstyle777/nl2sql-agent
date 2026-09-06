"""SQL 生成节点：基于 DDL 与改写后的问题生成单条 SQLite 查询。"""

from __future__ import annotations

import re

from ..state import AgentState

GENERATE_PROMPT = """你是 SQLite 专家。根据表结构和分析问题，写出一条查询语句。

要求：
1. 只输出一条 SQL，不要任何解释、不要 markdown 代码块。
2. 使用 SQLite 方言（日期函数用 strftime 等，没有 DATE_TRUNC）。
3. 表中的日期字段是 TEXT 类型且格式不统一（存在 '2025-03-01 12:00:00'、'2025/03/01 12:00' 两种主流格式），\
做时间过滤时必须同时兼容这两种格式。
4. 聚合前注意数据质量问题：金额可能为 NULL，状态字段大小写不统一（比较时用 LOWER() 归一）。
5. 只查询回答问题所需的最少字段，避免 SELECT *。
"""


def extract_sql(text: str) -> str:
    """从模型输出中提取 SQL（兼容模型偶发输出的代码块包裹）。"""
    fence = re.search(r"```(?:sql)?\s*(.+?)\s*```", text, re.DOTALL)
    sql = fence.group(1) if fence else text
    return sql.strip().rstrip(";").strip()


def make_generate_sql_node(client):
    def generate_sql(state: AgentState) -> dict:
        feedback = state.get("feedback", "")
        if feedback:
            # 自纠错：带着上一版 SQL 和问题反馈回炉重写
            user = (
                f"分析问题：{state['expanded_question']}\n\n"
                f"你上一版生成的 SQL：\n{state['sql']}\n\n"
                f"上一版的问题反馈：{feedback}\n\n"
                "请针对反馈修正，输出修正后的完整 SQL。"
            )
        else:
            user = f"分析问题：{state['expanded_question']}"
        result = client.chat(
            user,
            system=(
                f"{GENERATE_PROMPT}\n\n表结构（DDL）：\n{state['ddl']}\n\n"
                f"业务数据时间范围：{state['data_range']}"
            ),
        )
        return {"sql": extract_sql(result.content)}

    return generate_sql
