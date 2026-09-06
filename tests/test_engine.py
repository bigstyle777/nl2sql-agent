"""数据库访问层测试：安全约束是重点。"""

import sqlite3

import pytest

from src.db import engine


@pytest.fixture(scope="module")
def conn(tmp_path_factory):
    from data.generator import generate

    path = tmp_path_factory.mktemp("db") / "engine.db"
    generate(path, scale=0.01, seed=42)
    return engine.connect(path)


def test_connection_is_readonly(conn):
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM orders")


def test_validate_sql_rejects_non_select():
    for bad in [
        "UPDATE orders SET status='paid'",
        "DROP TABLE orders",
        "PRAGMA database_list",
        "ATTACH 'x' AS y",
        "INSERT INTO orders VALUES (1)",
        "SELECT 1; SELECT 2",
        "",
    ]:
        with pytest.raises(ValueError):
            engine.validate_sql(bad)


def test_validate_sql_accepts_select_and_cte():
    assert engine.validate_sql("select 1") == "select 1"
    assert engine.validate_sql("WITH t AS (SELECT 1 AS x) SELECT x FROM t;").startswith("WITH")


def test_get_ddl_contains_all_tables(conn):
    ddl = engine.get_ddl(conn)
    for table in ("users", "orders", "order_items", "daily_product_metrics"):
        assert f"CREATE TABLE {table}" in ddl


def test_run_sql_row_cap_and_truncation_flag(tmp_path_factory):
    path = tmp_path_factory.mktemp("db") / "cap.db"
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE t (x INTEGER)")
    c.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(50)])
    c.commit()

    result = engine.run_sql(c, "SELECT x FROM t", max_rows=10)
    assert len(result.rows) == 10
    assert result.truncated is True

    small = engine.run_sql(c, "SELECT x FROM t WHERE x < 3")
    assert len(small.rows) == 3
    assert small.truncated is False


def test_run_sql_timeout_guard(tmp_path_factory):
    """笛卡尔积必须被超时打断而不是卡死。"""
    path = tmp_path_factory.mktemp("db") / "slow.db"
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE t (x INTEGER)")
    c.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(2000)])
    c.commit()

    with pytest.raises(sqlite3.OperationalError):
        engine.run_sql(c, "SELECT COUNT(*) FROM t a, t b, t c, t d", max_rows=1)
