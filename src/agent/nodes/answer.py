"""回答节点：把查询结果转成面向用户的中文结论。"""

from __future__ import annotations

import json

from ..state import AgentState

MAX_ROWS_IN_PROMPT = 50

ANSWER_PROMPT = """你是数据分析助手。根据用户的分析问题、实际执行的 SQL 和查询结果，给出简洁的中文结论。

要求：
1. 直接回答问题，先给结论，再给关键数字；结果多时突出最大/最小的少数关键项，不要罗列全部。
2. 结果若被截断（行数超过上限），明确说明"仅展示部分数据"。
3. 结果为空时，说明未查到数据，并给出一种可能的原因（如时间范围内无数据、口径过严）。
4. 不确定的口径注明假设。不要编造结果里不存在的数字。
"""


def make_answer_node(client):
    def answer(state: AgentState) -> dict:
        if state.get("error"):
            return {"answer": f"查询执行失败：{state['error']}"}

        rows = state["rows"]
        payload = {
            "columns": state["columns"],
            "rows": [list(r) for r in rows[:MAX_ROWS_IN_PROMPT]],
            "total_rows_shown": min(len(rows), MAX_ROWS_IN_PROMPT),
            "truncated": state.get("truncated", False),
        }
        result = client.chat(
            f"分析问题：{state['expanded_question']}\n"
            f"执行的 SQL：\n{state['sql']}\n"
            f"查询结果（JSON）：\n{json.dumps(payload, ensure_ascii=False, default=str)}"
            + (
                f"\n\n注意：结果自检仍有未解决的反馈（已达重试上限）：{state.get('feedback')}。"
                if state.get("feedback")
                else ""
            ),
            system=ANSWER_PROMPT,
        )
        return {"answer": result.content.strip()}

    return answer
