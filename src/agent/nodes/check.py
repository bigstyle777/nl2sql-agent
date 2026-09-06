"""自检节点：执行后对结果做规则式合理性检查，并决定是否回炉重试。

检查项（全部零 LLM 成本）：
  1. 执行报错 → 反馈给生成节点修正
  2. 结果为空 → 提示检查过滤条件/日期格式兼容性（也可能确实无数据）
  3. 文本列存在仅大小写不同的值 → 提示用 LOWER() 归一（真实踩过的坑：
     订单状态 paid/PAID/Paid 被拆成多组统计）
  4. 某列全为 NULL → 提示可能是字段选择错误

路由：有反馈且未达轮次上限 → 回到生成节点；否则进入回答节点。
"""

from __future__ import annotations

from src.agent.state import AgentState

MAX_ATTEMPTS = 3


def sanity_issues(columns: list[str], rows: list[tuple]) -> list[str]:
    issues: list[str] = []
    if not rows:
        issues.append(
            "查询结果为空。请检查：过滤条件是否过严、日期过滤是否同时兼容"
            "'2025-03-01 12:00:00' 与 '2025/03/01 12:00' 两种格式、状态比较是否用 LOWER() 归一。"
            "若确认查询正确且确实无数据，请原样重新输出相同 SQL。"
        )
        return issues

    for idx, col in enumerate(columns):
        values = [str(r[idx]) for r in rows if r[idx] is not None]
        if not values:
            issues.append(f"列 {col} 的所有取值均为 NULL，可能选错了字段或过滤条件有误。")
            continue
        distinct = set(values)
        lowered = {v.lower() for v in values}
        if len(lowered) < len(distinct):
            issues.append(
                f"列 {col} 中存在仅大小写不同的取值（会被拆成不同分组），"
                f"分组聚合时应使用 LOWER({col}) 归一后输出。"
            )
    return issues


def make_check_node(max_attempts: int = MAX_ATTEMPTS):
    def check(state: AgentState) -> dict:
        attempts = state.get("attempts", 0) + 1
        error = state.get("error", "")
        if error:
            return {
                "attempts": attempts,
                "feedback": f"上一版 SQL 执行报错：{error}。请修正 SQL 使其可执行。",
            }
        issues = sanity_issues(state["columns"], state["rows"])
        return {
            "attempts": attempts,
            "feedback": "；".join(issues),
        }

    def route(state: AgentState) -> str:
        """条件边：有反馈且还有重试机会 → regenerate；否则 → answer。"""
        if state.get("feedback") and state.get("attempts", 0) < max_attempts:
            return "regenerate"
        return "finish"

    return check, route
