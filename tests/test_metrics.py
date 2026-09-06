"""评测判定器测试。"""

from src.eval.metrics import compare_results, is_ordered_query


def test_column_count_mismatch():
    ok, reason = compare_results(["a", "b"], [(1, 2)], ["x"], [(1,)], "")
    assert not ok and "列数" in reason


def test_row_count_mismatch():
    ok, reason = compare_results(["a"], [(1,), (2,)], ["x"], [(1,)], "")
    assert not ok and "行数" in reason


def test_set_compare_matches_different_order_same_names():
    """列名相同但顺序不同 → 自动按列名对齐后集合比较。"""
    ok, _ = compare_results(
        ["status", "cnt"],
        [("paid", 3), ("pending", 1)],
        ["cnt", "status"],
        [(1, "pending"), (3, "paid")],
        "",
    )
    assert ok


def test_positional_compare_with_different_names():
    """列名完全对不上 → 按位置比较；集合模式下行序无关。"""
    ok, _ = compare_results(["a"], [(1,), (2,)], ["x"], [(2,), (1,)], "")
    assert ok
    ok2, _ = compare_results(["a"], [(1,), (2,)], ["x"], [(3,), (1,)], "")
    assert not ok2
    assert ok


def test_numeric_tolerance_for_float_sums():
    ok, _ = compare_results(["amt"], [(26940460.33,)], ["amt"], [(26940460.325,)], "")
    assert ok
    ok2, _ = compare_results(["amt"], [(100.0,)], ["amt"], [(105.0,)], "")
    assert not ok2


def test_null_handling():
    assert compare_results(["a"], [(None,)], ["x"], [(None,)], "")[0]
    assert not compare_results(["a"], [(None,)], ["x"], [(0,)], "")[0]


def test_ordered_query_is_order_sensitive():
    ok, _ = compare_results(["a"], [(1,), (2,)], ["x"], [(2,), (1,)], "SELECT a FROM t ORDER BY a")
    assert not ok
    assert compare_results(
        ["a"], [(1,), (2,)], ["x"], [(2,), (1,)], "SELECT a FROM t ORDER BY a LIMIT 1"
    )[0]


def test_is_ordered_query():
    assert is_ordered_query("SELECT .. ORDER BY x")
    assert not is_ordered_query("SELECT .. ORDER BY x LIMIT 5")
    assert not is_ordered_query("SELECT ..")
