"""评测判定：执行准确率（execution accuracy）。

判定规则：
  - 列数必须一致，列名不要求一致（别名自由）
  - 结果行按多重集合比较；仅当 gold SQL 含 ORDER BY 且不含 LIMIT 时按顺序比较
    （top-N 查询存在并列随机序，按集合比较更稳定，题目只关心"是哪几行"）
  - 数值比较带容差：浮点求和受行序影响，绝对误差 0.011 或相对误差 1e-6 内视为相等
"""

from __future__ import annotations

import re

ABS_TOL = 0.011
REL_TOL = 1e-6


def _norm_cell(v) -> float | str | None:
    if v is None:
        return None
    if isinstance(v, int | float):
        return float(v)
    return str(v).strip()


def _cells_equal(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    a_num, b_num = isinstance(a, float), isinstance(b, float)
    if a_num != b_num:  # 数值列与文本列不可比（投影枚举时会出现）
        return False
    if a_num and b_num:
        return abs(a - b) <= max(ABS_TOL, abs(b) * REL_TOL)
    return a == b


def _rows_equal(ra, rb) -> bool:
    return len(ra) == len(rb) and all(_cells_equal(a, b) for a, b in zip(ra, rb, strict=True))


def is_ordered_query(gold_sql: str) -> bool:
    """ORDER BY 且无 LIMIT 才做顺序敏感比较。"""
    sql = gold_sql.lower()
    return "order by" in sql and not re.search(r"\blimit\b", sql)


def _align_columns(gold_columns, pred_columns, pred_rows):
    """按列名（大小写不敏感）重排 pred 行；列名对不上则保持原顺序。"""
    lower_gold = [c.strip().lower() for c in gold_columns]
    lower_pred = [c.strip().lower() for c in pred_columns]
    if len(set(lower_gold)) != len(lower_gold) or len(set(lower_pred)) != len(lower_pred):
        return pred_rows
    try:
        perm = [lower_pred.index(name) for name in lower_gold]
    except ValueError:
        return pred_rows
    return [tuple(row[j] for j in perm) for row in pred_rows]


def _set_rows_equal(gold: list[tuple], pred: list[tuple]) -> tuple[bool, str]:
    key = lambda row: tuple(round(c, 4) if isinstance(c, float) else str(c) for c in row)  # noqa: E731
    gs, ps = sorted(gold, key=key), sorted(pred, key=key)
    for i, (g, p) in enumerate(zip(gs, ps, strict=True)):
        if not _rows_equal(g, p):
            return False, f"第 {i} 行不一致（集合比较）：gold={g} pred={p}"
    return True, ""


def _ordered_rows_equal(gold: list[tuple], pred: list[tuple]) -> tuple[bool, str]:
    for i, (g, p) in enumerate(zip(gold, pred, strict=True)):
        if not _rows_equal(g, p):
            return False, f"第 {i} 行不一致（顺序敏感比较）：gold={g} pred={p}"
    return True, ""


def _try_projections(
    gold: list[tuple], pred: list[tuple], n_gold: int, n_pred: int, ordered: bool
) -> tuple[bool, str] | None:
    """pred 列多于 gold 时，逐个尝试 gold 列在 pred 中的对齐方式。

    模型常额外输出 id、名称等描述列；只要 gold 要求的每列都能在 pred 中找到
    对应列且数值全部吻合，即视为回答正确。列数差异控制在小规模内枚举。
    """
    if n_pred - n_gold > 3 or n_pred > 6:
        return None
    from itertools import permutations

    for idx in permutations(range(n_pred), n_gold):
        projected_p = [tuple(row[j] for j in idx) for row in pred]
        ok, reason = (
            _ordered_rows_equal(gold, projected_p)
            if ordered
            else _set_rows_equal(gold, projected_p)
        )
        if ok:
            return True, ""
    return None


def compare_results(
    gold_columns: list[str],
    gold_rows: list[tuple],
    pred_columns: list[str],
    pred_rows: list[tuple],
    gold_sql: str = "",
) -> tuple[bool, str]:
    """返回 (是否一致, 不一致原因)。列名一致时自动对齐列顺序。"""
    if len(gold_rows) != len(pred_rows):
        return False, f"行数不一致：gold={len(gold_rows)} pred={len(pred_rows)}"
    if not gold_rows:
        return True, ""
    if len(gold_columns) != len(pred_columns):
        # 允许 pred 带额外描述列，但要求投影后完全吻合
        if len(pred_columns) > len(gold_columns):
            gold = [tuple(_norm_cell(c) for c in row) for row in gold_rows]
            pred = [tuple(_norm_cell(c) for c in row) for row in pred_rows]
            result = _try_projections(
                gold, pred, len(gold_columns), len(pred_columns), is_ordered_query(gold_sql)
            )
            if result is not None:
                return result
        return False, f"列数不一致：gold={len(gold_columns)} pred={len(pred_columns)}"

    pred_rows = _align_columns(gold_columns, pred_columns, pred_rows)
    gold = [tuple(_norm_cell(c) for c in row) for row in gold_rows]
    pred = [tuple(_norm_cell(c) for c in row) for row in pred_rows]

    if is_ordered_query(gold_sql):
        return _ordered_rows_equal(gold, pred)
    return _set_rows_equal(gold, pred)
