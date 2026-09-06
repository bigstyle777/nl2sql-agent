"""业务库生成脚本测试。"""

import sqlite3

import pytest

from data.generator import generate

EXPECTED_TABLES = {
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
}


@pytest.fixture(scope="module")
def db_path(tmp_path_factory):
    path = tmp_path_factory.mktemp("data") / "test.db"
    return path, generate(path, scale=0.05, seed=42)


def _conn(db_path):
    return sqlite3.connect(db_path)


def test_all_tables_exist_and_populated(db_path):
    path, counts = db_path
    conn = _conn(path)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert EXPECTED_TABLES <= tables
    for table in EXPECTED_TABLES:
        assert counts[table] > 0, f"{table} 不应有空表"
    conn.close()


def test_row_counts_scale_with_factor(db_path):
    _, counts = db_path
    assert 4000 <= counts["orders"] <= 6000
    assert counts["order_items"] > counts["orders"]
    assert counts["daily_product_metrics"] > counts["products"] * 50


def test_dirty_data_is_present(db_path):
    """脏数据是本项目的核心资产，必须稳定存在。"""
    path, _ = db_path
    conn = _conn(path)
    n_status = conn.execute("SELECT COUNT(DISTINCT status) FROM orders").fetchone()[0]
    assert n_status > len(
        conn.execute("SELECT DISTINCT LOWER(status) FROM orders").fetchall()
    ), "状态大小写应存在不一致变体"
    assert conn.execute("SELECT COUNT(*) FROM orders WHERE total_amount IS NULL").fetchone()[0] > 0
    assert conn.execute("SELECT COUNT(*) FROM orders WHERE total_amount < 0").fetchone()[0] > 0
    assert conn.execute("SELECT COUNT(*) FROM products WHERE category_id IS NULL").fetchone()[0] > 0
    assert (
        conn.execute("SELECT COUNT(*) FROM reviews WHERE rating NOT BETWEEN 1 AND 5").fetchone()[0]
        > 0
    )
    assert (
        conn.execute("SELECT COUNT(*) FROM orders WHERE created_at LIKE '%+08:00'").fetchone()[0]
        > 0
    )
    # 日期格式混杂：至少两种格式同时出现
    formats = conn.execute(
        "SELECT COUNT(DISTINCT CASE "
        "WHEN created_at LIKE '____-__-__ %' THEN 'dash' "
        "WHEN created_at LIKE '____/__/__%' THEN 'slash' "
        "ELSE 'other' END) FROM orders"
    ).fetchone()[0]
    assert formats >= 2, "应存在多种日期格式"
    conn.close()


def test_generation_is_deterministic(tmp_path):
    path_a = tmp_path / "a.db"
    path_b = tmp_path / "b.db"
    generate(path_a, scale=0.01, seed=7)
    generate(path_b, scale=0.01, seed=7)
    conn_a = _conn(path_a)
    conn_b = _conn(path_b)
    rows_a = conn_a.execute("SELECT * FROM orders ORDER BY id LIMIT 100").fetchall()
    rows_b = conn_b.execute("SELECT * FROM orders ORDER BY id LIMIT 100").fetchall()
    assert rows_a == rows_b
    conn_a.close()
    conn_b.close()


def test_foreign_keys_declared(db_path):
    path, _ = db_path
    conn = _conn(path)
    n_fk = conn.execute("SELECT COUNT(*) FROM pragma_foreign_key_list('order_items')").fetchone()[0]
    assert n_fk >= 2
    conn.close()
