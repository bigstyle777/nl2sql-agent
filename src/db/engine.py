"""数据库访问层：只读连接、schema 获取、受限执行。

安全基线（M1 即生效，M2 继续加固）：
  - 以只读模式（URI mode=ro）打开 SQLite，任何写语句在连接层直接失败
  - 仅允许单条 SELECT/WITH 语句，多语句与非查询语句直接拒绝
  - progress handler 实现查询超时，防止全表笛卡尔积拖死 UI
  - 结果行数上限，超出部分截断并在状态中标记
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "ecommerce.db"
MAX_ROWS = 200
QUERY_TIMEOUT_S = 10.0


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[tuple]
    truncated: bool


def connect(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    path = Path(db_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"业务库不存在：{path}，请先运行 python data/generator.py")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=QUERY_TIMEOUT_S)
    return conn


def get_ddl(conn: sqlite3.Connection, include_indexes: bool = False) -> str:
    """返回建表 DDL 文本，作为生成 SQL 的上下文。"""
    query = "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL AND type = ? ORDER BY name"
    types = ["table", "index"] if include_indexes else ["table"]
    statements = [sql_text for t in types for (sql_text,) in conn.execute(query, (t,))]
    return ";\n\n".join(statements) + ";"


def get_ddl_by_table(conn: sqlite3.Connection) -> dict[str, str]:
    """按表名返回各自的 CREATE TABLE 语句，供动态裁剪按需拼接。"""
    rows = conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL ORDER BY name"
    ).fetchall()
    return {name: sql for name, sql in rows}


# 表的一行式说明：供选表节点在不看 DDL 的情况下判断相关性
TABLE_DESCRIPTIONS: dict[str, str] = {
    "users": "用户表：注册用户资料（所在城市、VIP等级、注销标记 is_deleted）",
    "addresses": "收货地址表：省份、城市、是否默认地址",
    "categories": "类目表（两级结构：parent_id 为空是一级类目，非空是二级类目）",
    "sellers": "卖家表：店铺名、所在城市、评分",
    "products": "商品表：价格、成本、库存、上下架状态、所属类目/卖家",
    "orders": "订单主表：订单状态、总金额、下单时间、支付时间",
    "order_items": "订单明细表：每个订单包含的商品、数量、单价、折扣",
    "payments": "支付流水表：支付方式、金额、支付成功/失败、支付时间",
    "refunds": "退款表：退款金额、退款原因、退款时间",
    "reviews": "商品评价表：评分 1-5、评价内容、评价时间",
    "coupons": "优惠券定义表：满减/折扣类型、面额、有效期",
    "user_coupons": "用户领券表：用户领取的券、是否已使用、使用时间",
    "daily_product_metrics": "商品每日指标宽表（按天聚合）：浏览PV/UV、加购、订单数、GMV、退款金额、搜索曝光点击、缺货时长",
    "daily_user_activity": "用户每日活跃宽表（按天聚合）：会话数、浏览量、时长、订单、设备、渠道",
}

# 列取值/格式说明：DDL 本身无法表达的语义（枚举值、日期格式惯用写法）。
# 注意措辞保持"纯描述"：不要出现"异常值""应该排除"等建议性语言，
# 否则模型会自行清洗/过滤数据，改变统计口径（M4 评测验证过的坑）。
COLUMN_HINTS = """列取值与格式说明（生成 SQL 前务必核对）：
- 统计口径严格按问题字面执行：不要自行排除任何状态或取值（如取消订单、低评分），
  也不要附加 is_deleted 等过滤，除非问题明确要求
- products.status 取值只有 'on_sale'（在售）和 'off_sale'（下架）
- orders.status 取值：pending/paid/shipped/completed/cancelled，存在大小写混杂（paid/PAID/Paid），
  按状态分组统计时输出 LOWER(status) 归一后的分组
- payments.method 取值：alipay/wechat/card（wechat 存在大小写变体）
- payments.status 取值：success/failed
- coupons.discount_type 取值：fixed（满减）/percent（折扣）
- user_coupons.used：1=已使用，0=未使用
- reviews.rating 取值 1-5 之间（存在个别越界值，属于数据本身，直接统计即可）
- 所有 TEXT 日期列（created_at/pay_time/paid_at/refunded_at/register_date 等）存在两种格式混存：
  '2025-03-05 12:00:00' 与 '2025/03/05 12:00'。按月过滤的标准写法：replace(substr(列名,1,7),'/','-')='2025-03'；
  按天分组：replace(substr(列名,1,10),'/','-')。直接用 substr(col,1,7)='2025-03' 会漏掉斜杠格式的行
- daily_product_metrics 和 daily_user_activity 的 date 列是标准 'YYYY-MM-DD' 格式，可直接 LIKE '2025-03%' 过滤"""


def get_data_time_range(conn: sqlite3.Connection) -> str:
    """查询业务库的实际时间范围，供相对时间词（"上月"等）锚定。"""
    end = conn.execute("SELECT MAX(date) FROM daily_product_metrics").fetchone()[0]
    start = conn.execute("SELECT MIN(date) FROM daily_product_metrics").fetchone()[0]
    return f"{start} 至 {end}"


def validate_sql(sql: str) -> str:
    """仅放行单条查询语句，返回清洗后的 SQL。"""
    cleaned = sql.strip().rstrip(";").strip()
    if not cleaned:
        raise ValueError("SQL 为空")
    if ";" in cleaned:
        raise ValueError("不允许包含多条语句")
    head = cleaned.split(None, 1)[0].upper() if cleaned.split() else ""
    if head not in ("SELECT", "WITH"):
        raise ValueError(f"仅允许 SELECT/WITH 查询，收到：{head}")
    return cleaned


def run_sql(conn: sqlite3.Connection, sql: str, max_rows: int = MAX_ROWS) -> QueryResult:
    cleaned = validate_sql(sql)

    deadline = time.monotonic() + QUERY_TIMEOUT_S

    def _guard() -> int:  # 返回非 0 中断查询
        return 1 if time.monotonic() > deadline else 0

    conn.create_function("_noop", 0, lambda: None)
    conn.set_progress_handler(_guard, 10000)
    try:
        cursor = conn.execute(cleaned)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = cursor.fetchmany(max_rows + 1)
    finally:
        conn.set_progress_handler(None, 0)

    truncated = len(rows) > max_rows
    return QueryResult(columns=columns, rows=rows[:max_rows], truncated=truncated)
