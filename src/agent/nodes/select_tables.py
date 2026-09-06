"""选表节点：动态 schema 裁剪的第一步。

不把全部 14 张表 DDL 塞进生成 prompt，而是先让模型基于"一行式表说明"
选出回答问题必需的表，生成节点只注入这些表的 DDL。
表说明很短（百级 Token），换来生成/重试轮次的大 DDL 注入减少。

兜底：选出 0 张或选出全部 → 注入全量 DDL；执行报"表不存在"时回退全量。
"""

from __future__ import annotations

import re

from src.db.engine import TABLE_DESCRIPTIONS

from ..state import AgentState

SELECT_PROMPT = (
    "你是数据分析师。下面是数据库的表清单（表名：说明）。"
    "根据用户问题，选出回答该问题必需的最少表集合。\n"
    "规则：只输出逗号分隔的表名，不要输出其他内容；不确定时宁可多选。"
)


def make_select_tables_node(client, ddl_by_table: dict[str, str]):
    def select_tables(state: AgentState) -> dict:
        listing = "\n".join(f"- {name}：{desc}" for name, desc in TABLE_DESCRIPTIONS.items())
        result = client.chat(state["expanded_question"], system=f"{SELECT_PROMPT}\n\n{listing}")
        picked = [
            t.strip()
            for t in re.split(r"[,，;；\s]+", result.content.strip())
            if t.strip() in ddl_by_table
        ]
        # 空结果或全选都等价于全量 DDL，不产生裁剪收益
        if not picked or len(picked) >= len(ddl_by_table):
            return {"selected_tables": [], "ddl_subset": "\n\n".join(ddl_by_table.values())}
        subset = "\n\n".join(ddl_by_table[name] for name in picked)
        return {"selected_tables": picked, "ddl_subset": subset}

    return select_tables
