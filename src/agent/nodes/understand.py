"""理解节点：将用户问题改写为自包含的分析问题。

相对时间词（"上月""最近7天"）若不锚定具体日期，SQL 无法生成或产生歧义。
改写需要一次 LLM 调用；不包含相对时间词的问题走快速路径直接放行，省一次调用。
"""

from __future__ import annotations

import re

from ..state import AgentState

RELATIVE_TIME_PATTERN = re.compile(
    r"今天|昨天|前天|本周|这周|上周|本月|这个月|上个月|上月|近\d*|最近|今年|去年|目前|当前|最新|至今|截止"
)

REWRITE_PROMPT = """你负责把用户的数据分析问题改写为"自包含"的问题：消解所有相对时间词和指代，\
改写后的问题不依赖任何上下文即可理解。

规则：
1. 当前日期：{today}。业务数据的时间范围是 {data_range}。
2. 相对时间必须换算为明确的日期区间。若相对时间超出数据范围，以数据范围内最近的对应区间为准。
3. 不确定的统计口径（如"销售额"是否含退款）保留原措辞，不要自行假设。
4. 只输出改写后的问题，不要解释。
"""


def make_understand_node(client):
    def understand(state: AgentState) -> dict:
        question = state["question"]
        if not RELATIVE_TIME_PATTERN.search(question):
            return {"expanded_question": question}

        from datetime import date

        result = client.chat(
            question,
            system=REWRITE_PROMPT.format(
                today=date.today().isoformat(), data_range=state["data_range"]
            ),
        )
        rewritten = result.content.strip().strip('"')
        return {"expanded_question": rewritten or question}

    return understand
