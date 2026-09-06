"""评测集生成脚本：参数化模板 → evals/dataset/v1.jsonl（120 题）。

设计原则：
  - gold SQL 与生成 SQL 面对同一份数据，难度分层（easy 60 / medium 40 / hard 20）
  - 模板覆盖真实坑点：TEXT 日期两种格式、状态大小写、NULL 金额、宽表、多表 join
  - 日期过滤统一用 replace(substr(col,1,7),'/','-') 归一，这是 gold 的"标准答案"写法
  - 确定性：固定 seed，重复运行产物完全一致（tests/test_dataset.py 会校验）

用法：
    python evals/build_dataset.py                # 生成 evals/dataset/v1.jsonl
    python evals/build_dataset.py --check        # 生成后逐题在库上执行 gold SQL 验证
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

DATASET_DIR = Path(__file__).parent / "dataset"
MONTHS = ["2025-01", "2025-02", "2025-03"]
CITIES = ["北京", "上海", "广州", "深圳", "杭州", "成都"]


def month_filter(col: str, month: str) -> str:
    """TEXT 日期（两种格式混杂）按月过滤的标准写法。"""
    return f"replace(substr({col},1,7),'/','-')='{month}'"


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

    # ============ EASY（60 题）：单表过滤 / 聚合 ============
    es.append(
        entry(1, "业务库里总共有多少笔订单？", "SELECT COUNT(*) FROM orders", "easy", ["count"])
    )
    for i, s in enumerate(["paid", "pending", "shipped", "cancelled"], 2):
        es.append(
            entry(
                i,
                f"{s} 状态的订单有多少笔？（状态字段大小写不统一，需归一）",
                f"SELECT COUNT(*) FROM orders WHERE LOWER(status)='{s}'",
                "easy",
                ["case_normalize"],
            )
        )
    for i, c in enumerate(CITIES, 6):
        es.append(
            entry(
                i,
                f"用户表中所在城市为 {c} 的记录有多少条？",
                f"SELECT COUNT(*) FROM users WHERE city='{c}'",
                "easy",
                ["filter"],
            )
        )
    es.append(
        entry(
            12,
            "在售（on_sale）商品有多少个？",
            "SELECT COUNT(*) FROM products WHERE status='on_sale'",
            "easy",
            ["filter"],
        )
    )
    for i, m in enumerate(MONTHS, 13):
        es.append(
            entry(
                i,
                f"{m} 月的订单有多少笔？",
                f"SELECT COUNT(*) FROM orders WHERE {month_filter('created_at', m)}",
                "easy",
                ["date_format_trap"],
            )
        )
    l2_names = ["耳机", "键盘", "鼠标", "充电宝", "音箱", "手环"]
    for i, name in enumerate(l2_names, 16):
        es.append(
            entry(
                i,
                f"二级类目「{name}」下有多少个商品？",
                f"SELECT COUNT(*) FROM products p JOIN categories c ON p.category_id=c.id "
                f"WHERE c.name='{name}'",
                "easy",
                ["join"],
            )
        )
    for i, c in enumerate(["深圳", "杭州", "成都"], 22):
        es.append(
            entry(
                i,
                f"{c}有多少个卖家？",
                f"SELECT COUNT(*) FROM sellers WHERE city='{c}'",
                "easy",
                ["filter"],
            )
        )
    es.append(
        entry(
            25, "平台总退款金额是多少？", "SELECT SUM(amount) FROM refunds", "easy", ["aggregate"]
        )
    )
    for i, pid in enumerate([1, 2, 3, 4], 26):
        es.append(
            entry(
                i,
                f"商品 id 为 {pid} 的平均评分是多少？",
                f"SELECT AVG(rating) FROM reviews WHERE product_id={pid}",
                "easy",
                ["aggregate"],
            )
        )
    es.append(
        entry(
            30,
            "VIP 等级为 3 的用户有多少个？",
            "SELECT COUNT(*) FROM users WHERE vip_level=3",
            "easy",
            ["filter"],
        )
    )
    for i, th in enumerate([100, 1000, 3000], 31):
        es.append(
            entry(
                i,
                f"库存超过 {th} 的在售商品有几个？",
                f"SELECT COUNT(*) FROM products WHERE stock>{th} AND status='on_sale'",
                "easy",
                ["filter"],
            )
        )
    es.append(
        entry(
            34,
            "满减型（fixed）优惠券有多少张？",
            "SELECT COUNT(*) FROM coupons WHERE discount_type='fixed'",
            "easy",
            ["filter"],
        )
    )
    es.append(
        entry(
            35,
            "默认收货地址有多少条？",
            "SELECT COUNT(*) FROM addresses WHERE is_default=1",
            "easy",
            ["filter"],
        )
    )
    es.append(
        entry(
            36,
            "有多少用户没有填写所在城市？",
            "SELECT COUNT(*) FROM users WHERE city IS NULL",
            "easy",
            ["null"],
        )
    )
    es.append(entry(37, "评价总条数是多少？", "SELECT COUNT(*) FROM reviews", "easy", ["count"]))
    es.append(
        entry(
            38,
            "支付失败的订单有多少笔？",
            "SELECT COUNT(*) FROM payments WHERE status='failed'",
            "easy",
            ["filter"],
        )
    )
    es.append(
        entry(
            39,
            "全部商品的平均定价是多少？",
            "SELECT AVG(price) FROM products",
            "easy",
            ["aggregate"],
        )
    )
    es.append(
        entry(
            40,
            "用户表中城市为上海的用户，平均 VIP 等级是多少？",
            "SELECT AVG(vip_level) FROM users WHERE city='上海'",
            "easy",
            ["aggregate"],
        )
    )
    es.append(
        entry(
            41,
            "所有商品的库存总量是多少？",
            "SELECT SUM(stock) FROM products",
            "easy",
            ["aggregate"],
        )
    )
    es.append(
        entry(42, "收货地址总共有多少条？", "SELECT COUNT(*) FROM addresses", "easy", ["count"])
    )
    es.append(
        entry(
            43,
            "二级类目（有父级类目的）有多少个？",
            "SELECT COUNT(*) FROM categories WHERE parent_id IS NOT NULL",
            "easy",
            ["filter"],
        )
    )
    es.append(
        entry(
            44, "卖家的平均评分是多少？", "SELECT AVG(rating) FROM sellers", "easy", ["aggregate"]
        )
    )
    for i, m in enumerate(MONTHS, 45):
        es.append(
            entry(
                i,
                f"{m} 月发生了多少笔退款？",
                f"SELECT COUNT(*) FROM refunds WHERE {month_filter('refunded_at', m)}",
                "easy",
                ["date_format_trap"],
            )
        )
    es.append(
        entry(
            48,
            "评分为 5 分的评价有多少条？",
            "SELECT COUNT(*) FROM reviews WHERE rating=5",
            "easy",
            ["filter"],
        )
    )
    es.append(
        entry(
            49,
            "业务数据里的设备类型一共有几种？",
            "SELECT COUNT(DISTINCT device) FROM daily_user_activity",
            "easy",
            ["distinct"],
        )
    )
    es.append(
        entry(
            50,
            "APP 一共有多少个不同版本？",
            "SELECT COUNT(DISTINCT app_version) FROM daily_user_activity",
            "easy",
            ["distinct"],
        )
    )
    es.append(
        entry(
            51,
            "折扣型（percent）优惠券有多少张？",
            "SELECT COUNT(*) FROM coupons WHERE discount_type='percent'",
            "easy",
            ["filter"],
        )
    )
    es.append(
        entry(
            52,
            "订单明细表（order_items）总共有多少行？",
            "SELECT COUNT(*) FROM order_items",
            "easy",
            ["count"],
        )
    )
    es.append(
        entry(
            53,
            "每日商品指标表记录的总 GMV 是多少？",
            "SELECT SUM(gmv) FROM daily_product_metrics",
            "easy",
            ["wide_table"],
        )
    )
    es.append(
        entry(
            54,
            "已被使用的优惠券有多少张？",
            "SELECT COUNT(*) FROM user_coupons WHERE used=1",
            "easy",
            ["filter"],
        )
    )
    es.append(
        entry(
            55,
            "北京的默认收货地址有多少条？",
            "SELECT COUNT(*) FROM addresses WHERE is_default=1 AND city='北京'",
            "easy",
            ["filter"],
        )
    )
    es.append(
        entry(
            56,
            "成本高于 100 元的在售商品有多少个？",
            "SELECT COUNT(*) FROM products WHERE cost>100 AND status='on_sale'",
            "easy",
            ["filter"],
        )
    )
    es.append(
        entry(
            57,
            "退款原因一共有多少种？",
            "SELECT COUNT(DISTINCT reason) FROM refunds",
            "easy",
            ["distinct"],
        )
    )
    es.append(
        entry(
            58,
            "支付方式一共有几种？（wechat/Wechat 等大小写变体算同一种）",
            "SELECT COUNT(DISTINCT LOWER(method)) FROM payments",
            "easy",
            ["distinct"],
        )
    )
    es.append(
        entry(
            59,
            "单笔订单的最高金额是多少？",
            "SELECT MAX(total_amount) FROM orders",
            "easy",
            ["aggregate"],
        )
    )
    es.append(
        entry(
            60,
            "最便宜的在售商品价格是多少？",
            "SELECT MIN(price) FROM products WHERE status='on_sale'",
            "easy",
            ["aggregate"],
        )
    )

    # ============ MEDIUM（40 题）：join / 分组 / top-N / 宽表 ============
    es.append(
        entry(
            61,
            "各订单状态分别有多少笔订单、总金额是多少？（注意状态字段大小写不统一）",
            "SELECT LOWER(status) AS status, COUNT(*) AS cnt, SUM(total_amount) AS amt "
            "FROM orders GROUP BY LOWER(status)",
            "medium",
            ["case_normalize", "group_by"],
        )
    )
    es.append(
        entry(
            62,
            "每个一级类目下各有多少个商品？",
            "SELECT p1.name AS category, COUNT(*) AS cnt FROM products p "
            "JOIN categories c ON p.category_id=c.id JOIN categories p1 ON c.parent_id=p1.id "
            "GROUP BY p1.id",
            "medium",
            ["join", "group_by"],
        )
    )
    es.append(
        entry(
            63,
            "各支付方式分别成功支付了多少笔？",
            "SELECT LOWER(method) AS method, COUNT(*) AS cnt FROM payments "
            "WHERE status='success' GROUP BY LOWER(method)",
            "medium",
            ["case_normalize"],
        )
    )
    for i, (m, n) in enumerate(
        [
            ("2025-01", 5),
            ("2025-02", 5),
            ("2025-03", 3),
            ("2025-03", 8),
            ("2025-01", 10),
            ("2025-02", 3),
        ],
        64,
    ):
        es.append(
            entry(
                i,
                f"{m} 月下单量最多的前 {n} 个城市及其订单量？（按用户资料的 city 字段统计，不含未填城市的订单）",
                f"SELECT u.city AS city, COUNT(*) AS cnt FROM orders o JOIN users u "
                f"ON o.user_id=u.id WHERE u.city IS NOT NULL AND {month_filter('o.created_at', m)} "
                f"GROUP BY u.city ORDER BY cnt DESC LIMIT {n}",
                "medium",
                ["join", "date_format_trap", "top_n"],
            )
        )
    for i, m in enumerate(MONTHS, 70):
        es.append(
            entry(
                i,
                f"{m} 月销售额最高的前 5 个二级类目及其销售额？（按订单明细的 (单价-折扣)*数量 求和）",
                f"SELECT c.name AS category, SUM((oi.unit_price-oi.discount)*oi.quantity) AS sales "
                f"FROM order_items oi JOIN orders o ON oi.order_id=o.id "
                f"JOIN products p ON oi.product_id=p.id JOIN categories c ON p.category_id=c.id "
                f"WHERE c.parent_id IS NOT NULL AND {month_filter('o.created_at', m)} "
                f"GROUP BY c.id ORDER BY sales DESC LIMIT 5",
                "medium",
                ["join", "date_format_trap", "top_n"],
            )
        )
    for i, n in enumerate([3, 5], 73):
        es.append(
            entry(
                i,
                f"评价数不少于 10 条的商品中，平均评分最低的前 {n} 个商品及其均分？",
                f"SELECT product_id, AVG(rating) AS avg_rating FROM reviews "
                f"GROUP BY product_id HAVING COUNT(*)>=10 ORDER BY avg_rating ASC LIMIT {n}",
                "medium",
                ["having", "top_n"],
            )
        )
    es.append(
        entry(
            75,
            "退款金额最高的前 5 个卖家及其退款金额？",
            "SELECT s.name AS seller, SUM(r.amount) AS refund_amt FROM refunds r "
            "JOIN order_items oi ON r.order_item_id=oi.id JOIN products p ON oi.product_id=p.id "
            "JOIN sellers s ON p.seller_id=s.id GROUP BY s.id ORDER BY refund_amt DESC LIMIT 5",
            "medium",
            ["join", "top_n"],
        )
    )
    es.append(
        entry(
            76,
            "各省份分别有多少条收货地址？",
            "SELECT province, COUNT(*) AS cnt FROM addresses WHERE province IS NOT NULL "
            "GROUP BY province",
            "medium",
            ["group_by"],
        )
    )
    for i, m in enumerate(["2025-02", "2025-03"], 77):
        es.append(
            entry(
                i,
                f"{m} 月每天的订单量分别是多少？",
                f"SELECT replace(substr(created_at,1,10),'/','-') AS day, COUNT(*) AS cnt "
                f"FROM orders WHERE {month_filter('created_at', m)} GROUP BY day",
                "medium",
                ["date_format_trap", "time_series"],
            )
        )
    for i, (pid, m) in enumerate(
        [
            ("101", "2025-01"),
            ("101", "2025-03"),
            ("202", "2025-02"),
            ("202", "2025-03"),
            ("303", "2025-01"),
            ("303", "2025-03"),
        ],
        79,
    ):
        es.append(
            entry(
                i,
                f"商品 {pid} 在 {m} 月的总 GMV 是多少？（宽表直接查询）",
                f"SELECT SUM(gmv) FROM daily_product_metrics "
                f"WHERE product_id={pid} AND date LIKE '{m}%'",
                "medium",
                ["wide_table"],
            )
        )
    for i, ch in enumerate(["app_store", "douyin", "search"], 85):
        es.append(
            entry(
                i,
                f"2025-03 月来自 {ch} 渠道的活跃用户有多少个？",
                f"SELECT COUNT(DISTINCT user_id) FROM daily_user_activity "
                f"WHERE channel='{ch}' AND date LIKE '2025-03%'",
                "medium",
                ["wide_table", "distinct"],
            )
        )
    es.append(
        entry(
            88,
            "每种优惠券各被领取了多少张？",
            "SELECT c.name AS coupon, COUNT(*) AS cnt FROM user_coupons uc "
            "JOIN coupons c ON uc.coupon_id=c.id GROUP BY c.id",
            "medium",
            ["join", "group_by"],
        )
    )
    es.append(
        entry(
            89,
            "VIP 等级大于 0 的用户的人均下单金额是多少？（不排除任何订单状态）",
            "SELECT SUM(o.total_amount)/COUNT(DISTINCT o.user_id) AS arppu FROM orders o "
            "JOIN users u ON o.user_id=u.id WHERE u.vip_level>0",
            "medium",
            ["ratio", "null"],
        )
    )
    es.append(
        entry(
            90,
            "评价数最多的前 5 个商品及其评价数？",
            "SELECT product_id, COUNT(*) AS cnt FROM reviews GROUP BY product_id "
            "ORDER BY cnt DESC LIMIT 5",
            "medium",
            ["top_n"],
        )
    )
    for i, m in enumerate(MONTHS, 91):
        es.append(
            entry(
                i,
                f"{m} 月全部订单的平均订单金额是多少？（不排除任何状态）",
                f"SELECT AVG(total_amount) FROM orders WHERE {month_filter('created_at', m)}",
                "medium",
                ["date_format_trap", "null"],
            )
        )
    es.append(
        entry(
            94,
            "2025-03 月各设备类型的总会话数是多少？",
            "SELECT device, SUM(sessions) AS total_sessions FROM daily_user_activity "
            "WHERE date LIKE '2025-03%' GROUP BY device",
            "medium",
            ["wide_table"],
        )
    )
    es.append(
        entry(
            95,
            "平均定价最高的前 5 个二级类目及其均价？",
            "SELECT c.name AS category, AVG(p.price) AS avg_price FROM products p "
            "JOIN categories c ON p.category_id=c.id WHERE c.parent_id IS NOT NULL "
            "GROUP BY c.id ORDER BY avg_price DESC LIMIT 5",
            "medium",
            ["join", "top_n"],
        )
    )
    es.append(
        entry(
            96,
            "商品数最多的前 5 个卖家及其商品数？",
            "SELECT seller_id, COUNT(*) AS cnt FROM products GROUP BY seller_id "
            "ORDER BY cnt DESC LIMIT 5",
            "medium",
            ["top_n"],
        )
    )
    es.append(
        entry(
            97,
            "发表评价最多的前 3 个用户及其评价数？",
            "SELECT user_id, COUNT(*) AS cnt FROM reviews GROUP BY user_id "
            "ORDER BY cnt DESC LIMIT 3",
            "medium",
            ["top_n"],
        )
    )
    es.append(
        entry(
            98,
            "各优惠券分别被使用了多少张？",
            "SELECT c.name AS coupon, COUNT(*) AS used_cnt FROM user_coupons uc "
            "JOIN coupons c ON uc.coupon_id=c.id WHERE uc.used=1 GROUP BY c.id",
            "medium",
            ["join", "filter"],
        )
    )
    es.append(
        entry(
            99,
            "2025-03 月订单量最高的前 5 个渠道及其订单总量？（用每日用户活跃宽表中的 orders 列统计）",
            "SELECT channel, SUM(orders) AS total_orders FROM daily_user_activity "
            "WHERE date LIKE '2025-03%' GROUP BY channel ORDER BY total_orders DESC LIMIT 5",
            "medium",
            ["wide_table"],
        )
    )
    es.append(
        entry(
            100,
            "2025-03 月每天的活跃用户数是多少？",
            "SELECT date, COUNT(DISTINCT user_id) AS active_users FROM daily_user_activity "
            "WHERE date LIKE '2025-03%' GROUP BY date",
            "medium",
            ["wide_table", "time_series"],
        )
    )

    # ============ HARD（20 题）：多表关联 / 比率 / 反直觉条件 ============
    for i, m in enumerate(MONTHS, 101):
        es.append(
            entry(
                i,
                f"{m} 月退款金额最高的前 3 个一级类目及其退款金额？",
                f"SELECT p1.name AS category, SUM(r.amount) AS refund_amt FROM refunds r "
                f"JOIN order_items oi ON r.order_item_id=oi.id "
                f"JOIN products p ON oi.product_id=p.id JOIN categories c ON p.category_id=c.id "
                f"JOIN categories p1 ON c.parent_id=p1.id "
                f"WHERE {month_filter('r.refunded_at', m)} GROUP BY p1.id "
                f"ORDER BY refund_amt DESC LIMIT 3",
                "hard",
                ["join_x4", "date_format_trap", "top_n"],
            )
        )
    es.append(
        entry(
            104,
            "下单次数不少于 2 次的用户有多少个？",
            "SELECT COUNT(*) FROM (SELECT user_id FROM orders GROUP BY user_id HAVING COUNT(*)>=2)",
            "hard",
            ["subquery"],
        )
    )
    es.append(
        entry(
            105,
            "用户表中从未发表过评价的记录有多少条？",
            "SELECT COUNT(*) FROM users u WHERE NOT EXISTS "
            "(SELECT 1 FROM reviews r WHERE r.user_id=u.id)",
            "hard",
            ["anti_join"],
        )
    )
    for i, m in enumerate(MONTHS, 106):
        es.append(
            entry(
                i,
                f"{m} 月人均消费金额是多少？（按当月有下单的用户平摊，不排除任何订单状态；"
                "金额缺失的订单不计入总额，但下单用户仍计入分母）",
                f"SELECT SUM(total_amount)/COUNT(DISTINCT user_id) AS arpu FROM orders "
                f"WHERE {month_filter('created_at', m)}",
                "hard",
                ["ratio", "null", "date_format_trap"],
            )
        )
    for i, m in enumerate(MONTHS, 109):
        es.append(
            entry(
                i,
                f"{m} 月 GMV 最高的前 5 个商品、其名称及所属一级类目？（用每日商品指标宽表的 gmv 列统计）",
                f"SELECT p.name AS product, p1.name AS category, SUM(d.gmv) AS total_gmv "
                f"FROM daily_product_metrics d JOIN products p ON d.product_id=p.id "
                f"JOIN categories c ON p.category_id=c.id JOIN categories p1 ON c.parent_id=p1.id "
                f"WHERE d.date LIKE '{m}%' GROUP BY p.id ORDER BY total_gmv DESC LIMIT 5",
                "hard",
                ["wide_table", "join", "top_n"],
            )
        )
    es.append(
        entry(
            112,
            "平台整体退款率是多少？（退款总金额 / 订单明细销售总金额）",
            "SELECT (SELECT SUM(amount) FROM refunds) / "
            "(SELECT SUM((unit_price-discount)*quantity) FROM order_items) AS refund_rate",
            "hard",
            ["ratio"],
        )
    )
    for i, m in enumerate(MONTHS, 113):
        es.append(
            entry(
                i,
                f"{m} 月的订单量和订单总金额分别是多少？",
                f"SELECT COUNT(*) AS cnt, SUM(total_amount) AS amt FROM orders "
                f"WHERE {month_filter('created_at', m)}",
                "hard",
                ["date_format_trap", "null"],
            )
        )
    es.append(
        entry(
            116,
            "VIP 等级不低于 2、但在 2025-03 月一次都没下过单的用户有多少个？",
            "SELECT COUNT(*) FROM users u WHERE u.vip_level>=2 AND NOT EXISTS "
            f"(SELECT 1 FROM orders o WHERE o.user_id=u.id AND {month_filter('o.created_at', '2025-03')})",
            "hard",
            ["anti_join", "date_format_trap"],
        )
    )
    es.append(
        entry(
            117,
            "各一级类目在售商品的平均定价是多少？",
            "SELECT p1.name AS category, AVG(p.price) AS avg_price FROM products p "
            "JOIN categories c ON p.category_id=c.id JOIN categories p1 ON c.parent_id=p1.id "
            "WHERE p.status='on_sale' GROUP BY p1.id",
            "hard",
            ["join", "group_by"],
        )
    )
    es.append(
        entry(
            118,
            "2025-03 月缺货时长最长的前 3 个商品及其累计缺货小时数？",
            "SELECT product_id, SUM(stock_out_hours) AS total_stockout "
            "FROM daily_product_metrics WHERE date LIKE '2025-03%' "
            "GROUP BY product_id ORDER BY total_stockout DESC LIMIT 3",
            "hard",
            ["wide_table", "top_n"],
        )
    )
    es.append(
        entry(
            119,
            "下单 3 次及以上的用户占全部下单用户的比例是多少？",
            "SELECT COUNT(*) * 1.0 / (SELECT COUNT(DISTINCT user_id) FROM orders) AS repeat_rate "
            "FROM (SELECT user_id FROM orders GROUP BY user_id HAVING COUNT(*)>=3)",
            "hard",
            ["ratio", "subquery"],
        )
    )
    es.append(
        entry(
            120,
            "2025-03 月人均会话数最高的前 5 个渠道及其人均会话数？",
            "SELECT channel, SUM(sessions)*1.0/COUNT(DISTINCT user_id) AS sessions_per_user "
            "FROM daily_user_activity WHERE date LIKE '2025-03%' GROUP BY channel "
            "ORDER BY sessions_per_user DESC LIMIT 5",
            "hard",
            ["wide_table", "ratio"],
        )
    )

    return es


def main() -> None:
    parser = argparse.ArgumentParser(description="生成评测集")
    parser.add_argument("--check", action="store_true", help="生成后逐题执行 gold SQL 验证")
    args = parser.parse_args()

    entries = build_entries()
    assert len(entries) == 120, f"题目数量应为 120，实际 {len(entries)}"
    assert len({e["question"] for e in entries}) == 120, "存在重复题目"
    assert len({e["id"] for e in entries}) == 120, "存在重复 id"

    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    out = DATASET_DIR / "v1.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    by_diff = {}
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
                conn.execute(e["gold_sql"]).fetchall()
            except Exception as err:
                bad += 1
                print(f"[FAIL] id={e['id']}: {err}\n  {e['gold_sql']}")
        conn.close()
        print(f"gold SQL 实库执行验证：{'全部通过' if bad == 0 else f'{bad} 题失败'}")
        if bad:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
