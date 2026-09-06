"""few-shot 示例库与检索。

归因报告（evals/reports/ATTRIBUTION-m5-final.md）定位出两类"套路缺失"失败：
两级类目穿越、退款统计的日期字段选择。本模块维护覆盖这些惯用写法的黄金示例，
按问题相似度动态挑选注入生成 prompt。

设计要点：
  - 示例是"本地惯例"的载体（表关系怎么连、日期怎么过滤、状态怎么归一），不是答案背诵
  - 检索用字符 2-gram Jaccard 相似度：零依赖、确定性，中文短句上够用
  - 检索不到足够相似的示例就不注入，避免噪声
"""

from __future__ import annotations

GOLD_EXAMPLES: list[dict] = [
    {
        "question": "2025-03 月销售额最高的前 5 个二级类目及其销售额？（按订单明细的 (单价-折扣)*数量 求和）",
        "keywords": "二级类目 销售额 类目 排名",
        "sql": """SELECT c.name AS category, SUM((oi.unit_price - oi.discount) * oi.quantity) AS sales
FROM order_items oi
JOIN orders o ON oi.order_id = o.id
JOIN products p ON oi.product_id = p.id
JOIN categories c ON p.category_id = c.id
WHERE c.parent_id IS NOT NULL
  AND replace(substr(o.created_at,1,7),'/','-') = '2025-03'
GROUP BY c.id
ORDER BY sales DESC
LIMIT 5""",
    },
    {
        "question": "每个一级类目下各有多少个商品？（商品挂在二级类目上，需经二级类目的 parent_id 找到所属一级类目）",
        "keywords": "一级类目 商品数量 分布 穿越",
        "sql": """SELECT p1.name AS category, COUNT(*) AS cnt
FROM products p
JOIN categories c ON p.category_id = c.id
JOIN categories p1 ON c.parent_id = p1.id
GROUP BY p1.id""",
    },
    {
        "question": "2025-02 月退款金额最高的前 3 个一级类目及其退款金额？",
        "keywords": "退款 类目 月度 排名",
        "sql": """SELECT p1.name AS category, SUM(r.amount) AS refund_amt
FROM refunds r
JOIN order_items oi ON r.order_item_id = oi.id
JOIN products p ON oi.product_id = p.id
JOIN categories c ON p.category_id = c.id
JOIN categories p1 ON c.parent_id = p1.id
WHERE replace(substr(r.refunded_at,1,7),'/','-') = '2025-02'
GROUP BY p1.id
ORDER BY refund_amt DESC
LIMIT 3""",
    },
    {
        "question": "2025-01 月发生了多少笔退款？（退款发生时间看 refunds.refunded_at）",
        "keywords": "退款 计数 月度",
        "sql": """SELECT COUNT(*)
FROM refunds
WHERE replace(substr(refunded_at,1,7),'/','-') = '2025-01'""",
    },
    {
        "question": "2025-01 月 GMV 最高的前 5 个商品及其名称？（宽表 date 是标准 YYYY-MM-DD，直接 LIKE）",
        "keywords": "GMV 宽表 商品 排名",
        "sql": """SELECT p.name AS product, SUM(d.gmv) AS total_gmv
FROM daily_product_metrics d
JOIN products p ON d.product_id = p.id
WHERE d.date LIKE '2025-01%'
GROUP BY p.id
ORDER BY total_gmv DESC
LIMIT 5""",
    },
    {
        "question": "各订单状态分别有多少笔订单、总金额是多少？（状态大小写混杂，分组前 LOWER 归一）",
        "keywords": "订单状态 分组 归一 大小写",
        "sql": """SELECT LOWER(status) AS status, COUNT(*) AS cnt, SUM(total_amount) AS amt
FROM orders
GROUP BY LOWER(status)""",
    },
    {
        "question": "2025-01 月人均消费金额是多少？（金额缺失的订单不计入总额，下单用户仍计入分母）",
        "keywords": "人均 消费 月度 比率",
        "sql": """SELECT SUM(total_amount) / COUNT(DISTINCT user_id) AS arpu
FROM orders
WHERE replace(substr(created_at,1,7),'/','-') = '2025-01'""",
    },
]

FEWSHOT_HEADER = (
    "参考示例（学习其中对本库的惯用写法：表关系怎么连、日期怎么过滤、状态怎么归一；"
    "不要照抄示例的题目和数值）："
)


def _bigrams(text: str) -> set[str]:
    return {text[i : i + 2] for i in range(len(text) - 1)}


def similarity(a: str, b: str) -> float:
    """字符 2-gram Jaccard 相似度（0~1）。"""
    ba, bb = _bigrams(a), _bigrams(b)
    if not ba or not bb:
        return 0.0
    return len(ba & bb) / len(ba | bb)


def retrieve_examples(question: str, k: int = 2, min_score: float = 0.15) -> list[dict]:
    """返回与问题最相关的 k 个示例（低于阈值的不返回）。"""
    scored = []
    for ex in GOLD_EXAMPLES:
        score = max(
            similarity(question, ex["question"]),
            max((similarity(question, kw) for kw in ex["keywords"].split()), default=0.0),
        )
        scored.append((score, ex))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [ex for score, ex in scored[:k] if score >= min_score]


def format_examples(examples: list[dict]) -> str:
    parts = [FEWSHOT_HEADER]
    for i, ex in enumerate(examples, 1):
        parts.append(f"\n### 示例{i}\n问题：{ex['question']}\nSQL：\n{ex['sql']}")
    return "\n".join(parts)
