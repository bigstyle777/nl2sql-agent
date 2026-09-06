"""留出集（holdout）构建脚本：evals/dataset/holdout-v2.jsonl（40 题）。

与主评测集（v1.jsonl）的区别：
  1. 问法口语化、去模板化，模拟真实用户表达；
  2. 覆盖 v1 未触碰的 SQL 特性：窗口函数（RANK/ROW_NUMBER/LAG）、
     CASE 条件聚合、字符串函数、双时间区间、连续活跃（gaps-and-islands）；
  3. 评测协议：本集构建完成后封存，调参过程不得参考其结果，
     仅做单次终评（single-shot final evaluation），结果无论高低直接采用。

用法：
    python evals/build_holdout.py --check   # 生成 + gold SQL 实库验证
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

DATASET_DIR = Path(__file__).parent / "dataset"


def entry(qid: int, question: str, gold: str, difficulty: str, tags: list[str]) -> dict:
    return {
        "id": qid,
        "question": question,
        "gold_sql": " ".join(gold.split()),
        "difficulty": difficulty,
        "tags": tags,
    }


def build_entries() -> list[dict]:
    es: list[dict] = []

    # ---------- EASY（12） ----------
    es.append(
        entry(1, "现在一共有多少个商品？", "SELECT COUNT(*) FROM products", "easy", ["count"])
    )
    es.append(
        entry(
            2, "卖得最贵的商品标价多少？", "SELECT MAX(price) FROM products", "easy", ["aggregate"]
        )
    )
    es.append(
        entry(
            3,
            "有多少用户领过优惠券？",
            "SELECT COUNT(DISTINCT user_id) FROM user_coupons",
            "easy",
            ["distinct"],
        )
    )
    es.append(
        entry(
            4,
            "北京和上海的用户加起来有多少个？",
            "SELECT COUNT(*) FROM users WHERE city IN ('北京','上海')",
            "easy",
            ["filter"],
        )
    )
    es.append(
        entry(
            5,
            "平均每个用户下几单？",
            "SELECT COUNT(*) * 1.0 / COUNT(DISTINCT user_id) FROM orders",
            "easy",
            ["ratio"],
        )
    )
    es.append(
        entry(
            6,
            "有多少订单没记录金额？",
            "SELECT COUNT(*) FROM orders WHERE total_amount IS NULL",
            "easy",
            ["null"],
        )
    )
    es.append(
        entry(
            7,
            "评分满分的评价有多少条？",
            "SELECT COUNT(*) FROM reviews WHERE rating=5",
            "easy",
            ["filter"],
        )
    )
    es.append(
        entry(
            8,
            "杭州的卖家平均评分多少？",
            "SELECT AVG(rating) FROM sellers WHERE city='杭州'",
            "easy",
            ["aggregate"],
        )
    )
    es.append(
        entry(
            9,
            "成功支付的订单里，用支付宝（alipay）的有多少笔？",
            "SELECT COUNT(*) FROM payments WHERE method='alipay' AND status='success'",
            "easy",
            ["filter"],
        )
    )
    es.append(
        entry(
            10,
            "在售商品里库存最少的那件还剩几件？",
            "SELECT MIN(stock) FROM products WHERE status='on_sale'",
            "easy",
            ["aggregate"],
        )
    )
    es.append(
        entry(
            11,
            "还没支付过的订单有多少笔？",
            "SELECT COUNT(*) FROM orders WHERE pay_time IS NULL",
            "easy",
            ["null"],
        )
    )
    es.append(
        entry(
            12,
            "3 月 15 日当天有多少用户活跃？",
            "SELECT COUNT(DISTINCT user_id) FROM daily_user_activity WHERE date='2025-03-15'",
            "easy",
            ["wide_table"],
        )
    )

    # ---------- MEDIUM（16） ----------
    es.append(
        entry(
            13,
            "活跃记录里，每种设备各有多少不同的活跃用户？",
            "SELECT device, COUNT(DISTINCT user_id) AS users FROM daily_user_activity "
            "GROUP BY device",
            "medium",
            ["wide_table", "distinct"],
        )
    )
    es.append(
        entry(
            14,
            "2025 年 2 月每天的退款金额是多少？",
            "SELECT replace(substr(refunded_at,1,10),'/','-') AS day, SUM(amount) AS amt "
            "FROM refunds WHERE replace(substr(refunded_at,1,7),'/','-')='2025-02' GROUP BY day",
            "medium",
            ["date_format_trap", "time_series"],
        )
    )
    es.append(
        entry(
            15,
            "有多少商品从来没被退过款？",
            "SELECT COUNT(*) FROM products p WHERE NOT EXISTS (SELECT 1 FROM order_items oi "
            "JOIN refunds r ON r.order_item_id=oi.id WHERE oi.product_id=p.id)",
            "medium",
            ["anti_join"],
        )
    )
    es.append(
        entry(
            16,
            "销售额排名前 3 的卖家是谁？各卖了多少？（按订单明细的 (单价-折扣)*数量 算）",
            "SELECT s.name AS seller, SUM((oi.unit_price-oi.discount)*oi.quantity) AS sales "
            "FROM order_items oi JOIN products p ON oi.product_id=p.id "
            "JOIN sellers s ON p.seller_id=s.id GROUP BY s.id ORDER BY sales DESC LIMIT 3",
            "medium",
            ["join", "top_n"],
        )
    )
    es.append(
        entry(
            17,
            "3 月上半月（15 号及以前）和下半月的订单量各是多少？输出一行两列。",
            "SELECT SUM(CASE WHEN replace(substr(created_at,1,10),'/','-')<='2025-03-15' "
            "THEN 1 ELSE 0 END) AS first_half, "
            "SUM(CASE WHEN replace(substr(created_at,1,10),'/','-')>'2025-03-15' "
            "THEN 1 ELSE 0 END) AS second_half FROM orders "
            "WHERE replace(substr(created_at,1,7),'/','-')='2025-03'",
            "medium",
            ["case", "date_format_trap"],
        )
    )
    es.append(
        entry(
            18,
            "3 月有哪些城市挤进了下单量前五？把名次（允许并列）也一起输出。",
            "SELECT city, cnt, rk FROM (SELECT u.city AS city, COUNT(*) AS cnt, "
            "RANK() OVER (ORDER BY COUNT(*) DESC) AS rk FROM orders o JOIN users u "
            "ON o.user_id=u.id WHERE u.city IS NOT NULL AND "
            "replace(substr(o.created_at,1,7),'/','-')='2025-03' GROUP BY u.city) WHERE rk<=5",
            "medium",
            ["window", "top_n"],
        )
    )
    es.append(
        entry(
            19,
            "VIP 用户（等级大于 0）里，每个等级分别有多少人？",
            "SELECT vip_level, COUNT(*) AS cnt FROM users WHERE vip_level>0 GROUP BY vip_level",
            "medium",
            ["group_by"],
        )
    )
    es.append(
        entry(
            20,
            "平均一单买几件东西？",
            "SELECT AVG(quantity) FROM order_items",
            "medium",
            ["aggregate"],
        )
    )
    es.append(
        entry(
            21,
            "金额是负数的订单有多少笔？（数据里确实有这种异常单）",
            "SELECT COUNT(*) FROM orders WHERE total_amount<0",
            "medium",
            ["dirty_data"],
        )
    )
    es.append(
        entry(
            22,
            "3 月订单量最多的前 3 天分别是哪几天？各下了多少单？",
            "SELECT replace(substr(created_at,1,10),'/','-') AS day, COUNT(*) AS cnt "
            "FROM orders WHERE replace(substr(created_at,1,7),'/','-')='2025-03' "
            "GROUP BY day ORDER BY cnt DESC LIMIT 3",
            "medium",
            ["time_series", "top_n"],
        )
    )
    es.append(
        entry(
            23,
            "成本超过 500 的商品，平均标价是多少？",
            "SELECT AVG(price) FROM products WHERE cost>500",
            "medium",
            ["filter"],
        )
    )
    es.append(
        entry(
            24,
            "有多少卖家到现在一个商品都没上架？",
            "SELECT COUNT(*) FROM sellers s WHERE NOT EXISTS "
            "(SELECT 1 FROM products p WHERE p.seller_id=s.id)",
            "medium",
            ["anti_join"],
        )
    )
    es.append(
        entry(
            25,
            "1 月活跃过的用户和 3 月活跃过的用户分别有多少个？输出一行两列。",
            "SELECT COUNT(DISTINCT CASE WHEN date LIKE '2025-01%' THEN user_id END) AS jan_users, "
            "COUNT(DISTINCT CASE WHEN date LIKE '2025-03%' THEN user_id END) AS mar_users "
            "FROM daily_user_activity",
            "medium",
            ["case", "wide_table"],
        )
    )
    es.append(
        entry(
            26,
            "评价内容里提到'物流'的评价有多少条？",
            "SELECT COUNT(*) FROM reviews WHERE content LIKE '%物流%'",
            "medium",
            ["like"],
        )
    )
    es.append(
        entry(
            27,
            "库存总量最大的前 3 个二级类目是哪些？各多少库存？",
            "SELECT c.name AS category, SUM(p.stock) AS total_stock FROM products p "
            "JOIN categories c ON p.category_id=c.id WHERE c.parent_id IS NOT NULL "
            "GROUP BY c.id ORDER BY total_stock DESC LIMIT 3",
            "medium",
            ["join", "top_n"],
        )
    )
    es.append(
        entry(
            28,
            "3 月的订单平均每单带几件商品？",
            "SELECT AVG(n) FROM (SELECT COUNT(*) AS n FROM order_items oi "
            "JOIN orders o ON oi.order_id=o.id WHERE "
            "replace(substr(o.created_at,1,7),'/','-')='2025-03' GROUP BY o.id)",
            "medium",
            ["subquery", "date_format_trap"],
        )
    )

    # ---------- HARD（12） ----------
    es.append(
        entry(
            29,
            "每个月的订单量是多少？相比上个月的增长比例是多少？（首月增长记空）",
            "SELECT mon, cnt, cnt * 1.0 / LAG(cnt) OVER (ORDER BY mon) - 1 AS growth FROM "
            "(SELECT replace(substr(created_at,1,7),'/','-') AS mon, COUNT(*) AS cnt "
            "FROM orders GROUP BY mon)",
            "hard",
            ["window", "time_series"],
        )
    )
    es.append(
        entry(
            30,
            "3 月每个一级类目里 GMV 最高的商品是哪个？",
            "SELECT category, product FROM (SELECT p1.name AS category, p.name AS product, "
            "ROW_NUMBER() OVER (PARTITION BY p1.id ORDER BY SUM(d.gmv) DESC) AS rn "
            "FROM daily_product_metrics d JOIN products p ON d.product_id=p.id "
            "JOIN categories c ON p.category_id=c.id JOIN categories p1 ON c.parent_id=p1.id "
            "WHERE d.date LIKE '2025-03%' GROUP BY p1.id, p.id) WHERE rn=1",
            "hard",
            ["window", "wide_table", "join"],
        )
    )
    es.append(
        entry(
            31,
            "3 月人均会话数最高的渠道是最低渠道的多少倍？",
            "SELECT (SELECT MAX(per_user) FROM (SELECT channel, SUM(sessions)*1.0/"
            "COUNT(DISTINCT user_id) AS per_user FROM daily_user_activity "
            "WHERE date LIKE '2025-03%' GROUP BY channel)) / "
            "(SELECT MIN(per_user) FROM (SELECT channel, SUM(sessions)*1.0/"
            "COUNT(DISTINCT user_id) AS per_user FROM daily_user_activity "
            "WHERE date LIKE '2025-03%' GROUP BY channel)) AS spread",
            "hard",
            ["ratio", "wide_table"],
        )
    )
    es.append(
        entry(
            32,
            "有多少用户 3 月下过单但从来没有一笔支付成功的记录？",
            "SELECT COUNT(DISTINCT user_id) FROM orders WHERE user_id NOT IN "
            "(SELECT DISTINCT user_id FROM payments WHERE status='success') "
            "AND replace(substr(created_at,1,7),'/','-')='2025-03'",
            "hard",
            ["anti_join"],
        )
    )
    es.append(
        entry(
            33,
            "退款率（退款金额/销售金额）最高的前 3 个卖家是谁？",
            "SELECT seller, refund_amt * 1.0 / sales_amt AS rate FROM "
            "(SELECT s.name AS seller, s.id AS sid, "
            "(SELECT COALESCE(SUM(r.amount),0) FROM refunds r JOIN order_items oi "
            "ON r.order_item_id=oi.id JOIN products p ON p.id=oi.product_id "
            "WHERE p.seller_id=s.id) AS refund_amt, "
            "(SELECT COALESCE(SUM((oi.unit_price-oi.discount)*oi.quantity),0) "
            "FROM order_items oi JOIN products p ON p.id=oi.product_id "
            "WHERE p.seller_id=s.id) AS sales_amt FROM sellers s) "
            "WHERE sales_amt>0 ORDER BY rate DESC LIMIT 3",
            "hard",
            ["ratio", "correlated_subquery"],
        )
    )
    es.append(
        entry(
            34,
            "3 月连续 3 天及以上每天都活跃的用户有多少个？",
            "SELECT COUNT(*) FROM (SELECT user_id, grp FROM "
            "(SELECT user_id, CAST(julianday(date) AS INTEGER) - "
            "ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY date) AS grp FROM "
            "(SELECT DISTINCT user_id, date FROM daily_user_activity WHERE date LIKE '2025-03%')) "
            "GROUP BY user_id, grp HAVING COUNT(*)>=3)",
            "hard",
            ["window", "gaps_and_islands", "wide_table"],
        )
    )
    es.append(
        entry(
            35,
            "1 到 5 星的评价各有多少条？（越界的异常评分不要算进来）",
            "SELECT rating, COUNT(*) AS cnt FROM reviews WHERE rating BETWEEN 1 AND 5 "
            "GROUP BY rating",
            "hard",
            ["case_aware"],
        )
    )
    es.append(
        entry(
            36,
            "各支付方式（大小写变体算同一种）在 1 月和 3 月的成功支付金额分别是多少？输出每行一个方式、两列金额。",
            "SELECT LOWER(method) AS method, "
            "SUM(CASE WHEN replace(substr(paid_at,1,7),'/','-')='2025-01' THEN amount END) AS jan_amt, "
            "SUM(CASE WHEN replace(substr(paid_at,1,7),'/','-')='2025-03' THEN amount END) AS mar_amt "
            "FROM payments WHERE status='success' GROUP BY LOWER(method)",
            "hard",
            ["case", "date_format_trap"],
        )
    )
    es.append(
        entry(
            37,
            "用户所在城市里，有多少个城市从没人下过单？",
            "SELECT COUNT(DISTINCT city) FROM users u WHERE u.city IS NOT NULL AND NOT EXISTS "
            "(SELECT 1 FROM orders o WHERE o.user_id=u.id)",
            "hard",
            ["anti_join"],
        )
    )
    es.append(
        entry(
            38,
            "金额最大的那一笔订单，下单用户的 VIP 等级是多少？",
            "SELECT u.vip_level FROM orders o JOIN users u ON o.user_id=u.id "
            "WHERE o.total_amount=(SELECT MAX(total_amount) FROM orders)",
            "hard",
            ["subquery"],
        )
    )
    es.append(
        entry(
            39,
            "2 月还活跃、3 月就流失了的用户有多少个？",
            "SELECT COUNT(DISTINCT user_id) FROM daily_user_activity WHERE date LIKE '2025-02%' "
            "AND user_id NOT IN (SELECT DISTINCT user_id FROM daily_user_activity "
            "WHERE date LIKE '2025-03%')",
            "hard",
            ["anti_join", "wide_table"],
        )
    )
    es.append(
        entry(
            40,
            "按用户的 VIP 等级分组，每组有多少个下过单的用户、平均订单金额是多少？",
            "SELECT u.vip_level, COUNT(DISTINCT o.user_id) AS users, "
            "AVG(o.total_amount) AS avg_amt FROM orders o JOIN users u ON o.user_id=u.id "
            "GROUP BY u.vip_level",
            "hard",
            ["join", "group_by"],
        )
    )

    return es


def main() -> None:
    parser = argparse.ArgumentParser(description="生成留出评测集（40 题）")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    entries = build_entries()
    assert len(entries) == 40, f"应为 40 题，实际 {len(entries)}"
    assert len({e["question"] for e in entries}) == 40, "存在重复题目"

    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    out = DATASET_DIR / "holdout-v2.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    by_diff: dict[str, int] = {}
    for e in entries:
        by_diff[e["difficulty"]] = by_diff.get(e["difficulty"], 0) + 1
    print(f"已生成 {out}，共 {len(entries)} 题：{by_diff}")

    if args.check:
        import sys

        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from src.db import engine

        conn = engine.connect()
        bad = 0
        for e in entries:
            try:
                cursor = conn.execute(e["gold_sql"])
                cursor.fetchall()
                assert cursor.description is not None
            except Exception as err:
                bad += 1
                print(f"[FAIL] id={e['id']}: {err}\n  {e['gold_sql']}")
        conn.close()
        print(f"gold SQL 实库执行验证：{'全部通过' if bad == 0 else f'{bad} 题失败'}")
        if bad:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
