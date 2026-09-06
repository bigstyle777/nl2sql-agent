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
