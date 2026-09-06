"""仿电商业务库生成脚本。

生成一个有真实感的 SQLite 业务库，供 Text-to-SQL Agent 开发与评测使用。

刻意埋入的"脏数据"是本项目的重要资产，对应真实数仓中常见的问题：
  - 日期以 TEXT 存储，且存在 %Y-%m-%d、%Y/%m/%d、ISO 三种格式混杂
  - 少量时间戳带 '+08:00' 时区后缀，大部分不带
  - 订单状态大小写不一致（paid / PAID / Paid）
  - 金额 NULL / 负数异常 / 三位小数精度噪音
  - 用户 city 缺失、商品 category_id 缺失
  - 完全重复的订单（内容相同、id 不同）
  - 评分越界（0 分、6 分）、非法邮箱
  - 两张 10+ 列的每日指标宽表（后续 schema 裁剪优化的演示对象）

用法:
    python data/generator.py                    # 全量生成 data/ecommerce.db
    python data/generator.py --scale 0.01       # 1% 规模，快速调试
    python data/generator.py --seed 7           # 固定随机种子保证可复现
"""

from __future__ import annotations

import argparse
import random
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).parent / "ecommerce.db"
BASE_DATE = datetime(2025, 1, 1)
DAYS = 120

CITIES = [
    "北京",
    "上海",
    "广州",
    "深圳",
    "杭州",
    "成都",
    "武汉",
    "南京",
    "西安",
    "重庆",
    "苏州",
    "长沙",
]
PROVINCES = {
    "北京": "北京",
    "上海": "上海",
    "广州": "广东",
    "深圳": "广东",
    "杭州": "浙江",
    "成都": "四川",
    "武汉": "湖北",
    "南京": "江苏",
    "西安": "陕西",
    "重庆": "重庆",
    "苏州": "江苏",
    "长沙": "湖南",
}
SURNAMES = ["王", "李", "张", "刘", "陈", "杨", "赵", "黄", "周", "吴", "徐", "孙", "马", "朱"]
GIVEN_NAMES = [
    "伟",
    "芳",
    "娜",
    "敏",
    "静",
    "磊",
    "军",
    "洋",
    "勇",
    "艳",
    "杰",
    "涛",
    "明",
    "超",
    "秀英",
    "国强",
    "建国",
    "雨轩",
    "思远",
    "梦琪",
]
ADJECTIVES = ["轻奢", "经典", "智能", "便携", "旗舰", "甄选", "潮流", "简约", "定制", "降噪"]
NOUNS = [
    "耳机",
    "保温杯",
    "键盘",
    "鼠标",
    "充电宝",
    "台灯",
    "背包",
    "水壶",
    "音箱",
    "手环",
    "衬衫",
    "运动鞋",
    "笔记本支架",
    "加湿器",
    "瑜伽垫",
]

L1_CATEGORIES = ["数码电器", "服饰鞋包", "家居日用", "运动户外", "美妆个护"]
L2_CATEGORIES = {
    "数码电器": ["耳机", "键盘", "鼠标", "充电宝", "音箱", "手环"],
    "服饰鞋包": ["衬衫", "运动鞋", "背包"],
    "家居日用": ["保温杯", "台灯", "加湿器", "水壶", "笔记本支架"],
    "运动户外": ["瑜伽垫", "运动鞋", "手环"],
    "美妆个护": ["面膜", "洗发水", "香水"],
}

PAY_METHODS = ["alipay", "wechat", "card", "Wechat"]  # wechat 大小写不一致是刻意的
ORDER_STATUSES = ["pending", "paid", "shipped", "completed", "cancelled"]
# 同一状态故意存在多种写法
STATUS_VARIANTS = {
    "pending": ["pending", "PENDING"],
    "paid": ["paid", "PAID", "Paid"],
    "shipped": ["shipped", "SHIPPED"],
    "completed": ["completed", "COMPLETED", "Completed"],
    "cancelled": ["cancelled", "CANCELLED"],
}
REFUND_REASONS = ["七天无理由", "质量问题", "发错货", "不想要了", "尺寸不合", "物流损坏"]
DEVICES = ["iPhone", "Android", "PC", "iPad"]
CHANNELS = ["app_store", "douyin", "wechat", "search", "direct"]
APP_VERSIONS = ["4.2.0", "4.2.1", "4.3.0", "5.0.0"]

TS_FORMATS = ["%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y-%m-%dT%H:%M:%S"]


def _ts(dt: datetime, rng: random.Random) -> str:
    """按三种格式之一输出时间字符串，约 2% 概率追加时区后缀。"""
    fmt = rng.choices(TS_FORMATS, weights=[80, 15, 5])[0]
    s = dt.strftime(fmt)
    if rng.random() < 0.02:
        s += "+08:00"
    return s


def _money(x: float) -> float:
    return round(x, 2)


def _noisy_price(price: float, rng: random.Random) -> float:
    """约 5% 的金额带三位小数精度噪音，模拟上游分摊计算产生的脏值。"""
    if rng.random() < 0.05:
        return round(price, 3)
    return _money(price)


def build_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL,
            email TEXT,
            city TEXT,
            register_date TEXT,
            vip_level INTEGER DEFAULT 0,
            is_deleted INTEGER DEFAULT 0
        );
        CREATE TABLE addresses (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            province TEXT,
            city TEXT,
            detail TEXT,
            is_default INTEGER DEFAULT 0
        );
        CREATE TABLE categories (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            parent_id INTEGER REFERENCES categories(id)
        );
        CREATE TABLE sellers (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            city TEXT,
            rating REAL,
            open_date TEXT
        );
        CREATE TABLE products (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            category_id INTEGER REFERENCES categories(id),
            seller_id INTEGER REFERENCES sellers(id),
            price REAL,
            cost REAL,
            stock INTEGER,
            status TEXT,
            created_at TEXT
        );
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            status TEXT,
            total_amount REAL,
            created_at TEXT,
            pay_time TEXT
        );
        CREATE TABLE order_items (
            id INTEGER PRIMARY KEY,
            order_id INTEGER NOT NULL REFERENCES orders(id),
            product_id INTEGER NOT NULL REFERENCES products(id),
            seller_id INTEGER,
            quantity INTEGER NOT NULL,
            unit_price REAL,
            discount REAL DEFAULT 0
        );
        CREATE TABLE payments (
            id INTEGER PRIMARY KEY,
            order_id INTEGER NOT NULL REFERENCES orders(id),
            method TEXT,
            amount REAL,
            paid_at TEXT,
            status TEXT
        );
        CREATE TABLE refunds (
            id INTEGER PRIMARY KEY,
            order_item_id INTEGER NOT NULL REFERENCES order_items(id),
            amount REAL,
            reason TEXT,
            refunded_at TEXT
        );
        CREATE TABLE reviews (
            id INTEGER PRIMARY KEY,
            product_id INTEGER NOT NULL REFERENCES products(id),
            user_id INTEGER NOT NULL REFERENCES users(id),
            rating INTEGER,
            content TEXT,
            created_at TEXT
        );
        CREATE TABLE coupons (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            discount_type TEXT,
            value REAL,
            min_amount REAL,
            start_date TEXT,
            end_date TEXT
        );
        CREATE TABLE user_coupons (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            coupon_id INTEGER NOT NULL REFERENCES coupons(id),
            used INTEGER DEFAULT 0,
            used_at TEXT
        );
        CREATE TABLE daily_product_metrics (
            date TEXT NOT NULL,
            product_id INTEGER NOT NULL REFERENCES products(id),
            pv INTEGER,
            uv INTEGER,
            cart_adds INTEGER,
            orders INTEGER,
            gmv REAL,
            refund_amount REAL,
            search_impressions INTEGER,
            search_clicks INTEGER,
            stock_out_hours REAL,
            avg_price REAL,
            PRIMARY KEY (date, product_id)
        );
        CREATE TABLE daily_user_activity (
            date TEXT NOT NULL,
            user_id INTEGER NOT NULL REFERENCES users(id),
            sessions INTEGER,
            page_views INTEGER,
            duration_sec INTEGER,
            orders INTEGER,
            amount REAL,
            device TEXT,
            os TEXT,
            app_version TEXT,
            channel TEXT,
            PRIMARY KEY (date, user_id)
        );
        CREATE INDEX idx_orders_user ON orders(user_id);
        CREATE INDEX idx_orders_created ON orders(created_at);
        CREATE INDEX idx_items_order ON order_items(order_id);
        CREATE INDEX idx_items_product ON order_items(product_id);
        CREATE INDEX idx_reviews_product ON reviews(product_id);
        CREATE INDEX idx_dpm_product ON daily_product_metrics(product_id);
        CREATE INDEX idx_dua_user ON daily_user_activity(user_id);
        """
    )


def _rand_time(day_offset: int, rng: random.Random) -> datetime:
    return BASE_DATE + timedelta(days=day_offset, seconds=rng.randrange(86400))


def generate(db_path: Path = DEFAULT_DB_PATH, scale: float = 1.0, seed: int = 42) -> dict[str, int]:
    """生成业务库，返回各表行数。scale 控制规模（测试用小值）。"""
    rng = random.Random(seed)
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    build_schema(conn)

    n_users = max(200, int(20000 * scale))
    n_sellers = max(30, int(500 * scale))
    n_products = max(100, int(3000 * scale))
    n_orders = max(500, int(100000 * scale))
    n_days = max(14, int(DAYS * min(1.0, scale * 10)))

    # ---- categories（两级）----
    l2_list: list[tuple[int, str, int]] = []
    cid = 1
    l1_ids: dict[str, int] = {}
    for l1 in L1_CATEGORIES:
        l1_ids[l1] = cid
        conn.execute("INSERT INTO categories VALUES (?,?,NULL)", (cid, l1))
        cid += 1
        for l2 in L2_CATEGORIES[l1]:
            l2_list.append((cid, l2, l1_ids[l1]))
            cid += 1

    # ---- sellers ----
    sellers = []
    for i in range(1, n_sellers + 1):
        sellers.append(
            (
                i,
                f"{rng.choice(SURNAMES)}氏{rng.choice(['优选', '官方', '工厂', '直营'])}店",
                rng.choice(CITIES),
                round(rng.uniform(3.2, 5.0), 1),
                _ts(_rand_time(-rng.randrange(365, 900), rng), rng),
            )
        )

    # ---- users ----
    users = []
    used_emails: set[str] = set()
    for i in range(1, n_users + 1):
        name = rng.choice(SURNAMES) + rng.choice(GIVEN_NAMES)
        city = None if rng.random() < 0.03 else rng.choice(CITIES)
        email = f"user{i}@{rng.choice(['qq.com', '163.com', 'gmail.com'])}"
        if rng.random() < 0.005:  # 少量重复/非法邮箱
            email = rng.choice(
                [email, email.replace("@", "@@"), rng.choice(list(used_emails) or [email])]
            )
        used_emails.add(email)
        users.append(
            (
                i,
                name + str(i),
                email,
                city,
                _ts(_rand_time(-rng.randrange(30, 900), rng), rng),
                rng.choices([0, 1, 2, 3], weights=[70, 20, 8, 2])[0],
                1 if rng.random() < 0.01 else 0,
            )
        )

    # ---- addresses ----
    addresses = []
    aid = 1
    for u in users:
        if u[3] is None:
            continue
        for _ in range(rng.choices([0, 1, 2], weights=[20, 60, 20])[0]):
            addresses.append(
                (
                    aid,
                    u[0],
                    PROVINCES[u[3]],
                    u[3],
                    f"{rng.randrange(1, 99)}号小区{rng.randrange(1, 30)}栋{rng.randrange(101, 2505)}",
                    1 if not any(a[1] == u[0] and a[5] == 1 for a in addresses) else 0,
                )
            )
            aid += 1

    # ---- products ----
    products = []
    product_l2: dict[int, str] = {}
    for i in range(1, n_products + 1):
        l2_id, l2_name, _ = rng.choice(l2_list)
        product_l2[i] = l2_name
        price = round(rng.uniform(9.9, 2999), 2)
        if rng.random() < 0.002:  # 极端价格异常
            price = 999999.0
        cat_id = None if rng.random() < 0.02 else l2_id  # 少量商品缺失类目
        status = rng.choices(["on_sale", "off_sale"], weights=[85, 15])[0]
        products.append(
            (
                i,
                f"{rng.choice(ADJECTIVES)}{l2_name}{'Pro' if rng.random() < 0.2 else ''}",
                cat_id,
                rng.randrange(1, n_sellers + 1),
                price,
                _money(price * rng.uniform(0.4, 0.8)),
                rng.randrange(0, 5000),
                status,
                _ts(_rand_time(-rng.randrange(30, 700), rng), rng),
            )
        )

    # ---- coupons ----
    coupons = []
    for i in range(1, 41):
        dtype = rng.choice(["fixed", "percent"])
        coupons.append(
            (
                i,
                f"满{rng.choice([99, 199, 299, 599])}减{rng.choice([10, 20, 50])}券"
                if dtype == "fixed"
                else f"{rng.choice([5, 8, 9])}折券",
                dtype,
                rng.choice([10, 20, 50]) if dtype == "fixed" else rng.choice([0.9, 0.85, 0.95]),
                rng.choice([0, 99, 199, 299]),
                (BASE_DATE - timedelta(days=rng.randrange(0, 90))).strftime("%Y-%m-%d"),
                (BASE_DATE + timedelta(days=rng.randrange(30, 180))).strftime("%Y-%m-%d"),
            )
        )

    # ---- orders + order_items + payments + refunds + reviews ----
    orders: list[tuple] = []
    order_items: list[tuple] = []
    payments: list[tuple] = []
    refunds: list[tuple] = []
    reviews: list[tuple] = []
    item_id = 1
    pay_id = 1
    refund_id = 1
    review_id = 1
    dup_snapshot: list[tuple] = []

    for oid in range(1, n_orders + 1):
        user = rng.choice(users)
        created = _rand_time(rng.randrange(n_days), rng)
        n_items = rng.choices([1, 2, 3, 5], weights=[50, 30, 15, 5])[0]
        items, total = [], 0.0
        for _ in range(n_items):
            p = rng.choice(products)
            qty = rng.choices([1, 2, 3], weights=[75, 20, 5])[0]
            disc = _money(p[4] * rng.choice([0, 0, 0, 0.05, 0.1]))
            total += (p[4] - disc) * qty
            items.append((None, oid, p[0], p[3], qty, _noisy_price(p[4], rng), disc))
        total = _noisy_price(total + rng.choice([0, 0, 6.0, 8.0]), rng)
        if rng.random() < 0.003:
            total = None  # 金额缺失
        elif rng.random() < 0.003:
            total = -total  # 负数异常
        status = rng.choices(ORDER_STATUSES, weights=[8, 25, 15, 45, 7])[0]
        pay_time = (
            _ts(created + timedelta(minutes=rng.randrange(1, 30)), rng)
            if status != "pending"
            else None
        )
        row = (
            oid,
            user[0],
            rng.choice(STATUS_VARIANTS[status]),
            total,
            _ts(created, rng),
            pay_time,
        )
        orders.append(row)
        if rng.random() < 0.002 and len(dup_snapshot) < 200:
            dup_snapshot.append(row)  # 完全重复订单（稍后换个 id 再插一次）
        for it in items:
            order_items.append((item_id, it[1], it[2], it[3], it[4], it[5], it[6]))
            if status in ("paid", "shipped", "completed", "cancelled") and rng.random() < 0.03:
                refunds.append(
                    (
                        refund_id,
                        item_id,
                        _money((it[5] - it[6]) * it[4]),
                        rng.choice(REFUND_REASONS),
                        _ts(created + timedelta(days=rng.randrange(1, 10)), rng),
                    )
                )
                refund_id += 1
            item_id += 1
        if status != "pending":
            payments.append(
                (
                    pay_id,
                    oid,
                    rng.choice(PAY_METHODS),
                    total,
                    pay_time,
                    rng.choice(["success", "success", "success", "failed"]),
                )
            )
            pay_id += 1
        if rng.random() < 0.6:
            p = rng.choice(products)
            rating = rng.choices([1, 2, 3, 4, 5], weights=[5, 8, 15, 30, 42])[0]
            if rng.random() < 0.01:
                rating = rng.choice([0, 6])  # 评分越界
            reviews.append(
                (
                    review_id,
                    p[0],
                    user[0],
                    rating,
                    rng.choice(
                        [
                            "不错",
                            "物流很快",
                            "质量一般",
                            "和描述一致",
                            "包装破损",
                            "性价比高",
                            "客服态度差",
                            "回购第三次了",
                        ]
                    ),
                    _ts(created + timedelta(days=rng.randrange(1, 15)), rng),
                )
            )
            review_id += 1

    for i, row in enumerate(dup_snapshot):  # 重复订单换 id 重插
        orders.append((n_orders + 1 + i, *row[1:]))

    # ---- user_coupons ----
    user_coupons = []
    for i in range(1, max(50, int(60000 * scale)) + 1):
        used = rng.random() < 0.4
        user_coupons.append(
            (
                i,
                rng.randrange(1, n_users + 1),
                rng.randrange(1, 41),
                1 if used else 0,
                _ts(_rand_time(rng.randrange(n_days), rng), rng) if used else None,
            )
        )

    # ---- daily_product_metrics（宽表 1）----
    dpm = []
    for d in range(n_days):
        date = (BASE_DATE + timedelta(days=d)).strftime("%Y-%m-%d")
        for p in products:
            base = rng.randrange(0, 800)
            gmv = _money(base * p[4] * rng.uniform(0.02, 0.08)) if base else 0.0
            dpm.append(
                (
                    date,
                    p[0],
                    base * rng.randrange(2, 6),
                    base,
                    int(base * rng.uniform(0.02, 0.1)),
                    int(base * rng.uniform(0.01, 0.06)),
                    gmv,
                    _money(gmv * rng.uniform(0, 0.05)),
                    base * rng.randrange(3, 10),
                    int(base * rng.uniform(0.3, 0.9)),
                    round(rng.uniform(0, 24), 1),
                    _noisy_price(p[4], rng),
                )
            )

    # ---- daily_user_activity（宽表 2）----
    dua = []
    active_users = users[: max(200, int(n_users * 0.4))]
    for d in range(n_days):
        date = (BASE_DATE + timedelta(days=d)).strftime("%Y-%m-%d")
        for u in active_users:
            if rng.random() < 0.3:
                continue
            sess = rng.randrange(1, 8)
            dua.append(
                (
                    date,
                    u[0],
                    sess,
                    sess * rng.randrange(3, 15),
                    sess * rng.randrange(30, 600),
                    rng.randrange(0, 3),
                    _money(rng.uniform(0, 2000) if rng.random() < 0.4 else 0),
                    (dev := rng.choice(DEVICES)),
                    "iOS" if dev == "iPhone" else rng.choice(["Android", "Windows", "macOS"]),
                    rng.choice(APP_VERSIONS),
                    rng.choice(CHANNELS),
                )
            )

    # ---- 批量写入 ----
    def insert(sql: str, rows: list[tuple]) -> None:
        conn.executemany(sql, rows)

    insert("INSERT INTO categories VALUES (?,?,?)", [(i, n, p) for i, n, p in l2_list])
    insert("INSERT INTO sellers VALUES (?,?,?,?,?)", sellers)
    insert("INSERT INTO users VALUES (?,?,?,?,?,?,?)", users)
    insert("INSERT INTO addresses VALUES (?,?,?,?,?,?)", addresses)
    insert("INSERT INTO products VALUES (?,?,?,?,?,?,?,?,?)", products)
    insert("INSERT INTO coupons VALUES (?,?,?,?,?,?,?)", coupons)
    insert("INSERT INTO orders VALUES (?,?,?,?,?,?)", orders)
    insert("INSERT INTO order_items VALUES (?,?,?,?,?,?,?)", order_items)
    insert("INSERT INTO payments VALUES (?,?,?,?,?,?)", payments)
    insert("INSERT INTO refunds VALUES (?,?,?,?,?)", refunds)
    insert("INSERT INTO reviews VALUES (?,?,?,?,?,?)", reviews)
    insert("INSERT INTO user_coupons VALUES (?,?,?,?,?)", user_coupons)
    insert("INSERT INTO daily_product_metrics VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", dpm)
    insert("INSERT INTO daily_user_activity VALUES (?,?,?,?,?,?,?,?,?,?,?)", dua)

    conn.commit()
    counts = {
        t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        for t in (
            "users",
            "addresses",
            "categories",
            "sellers",
            "products",
            "orders",
            "order_items",
            "payments",
            "refunds",
            "reviews",
            "coupons",
            "user_coupons",
            "daily_product_metrics",
            "daily_user_activity",
        )
    }
    conn.close()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="生成仿电商业务库")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--scale", type=float, default=1.0, help="数据规模系数")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    counts = generate(args.db_path, scale=args.scale, seed=args.seed)
    print(f"已生成 {args.db_path}（seed={args.seed}, scale={args.scale}）")
    for table, n in counts.items():
        print(f"  {table:<24} {n:>8} 行")


if __name__ == "__main__":
    main()
