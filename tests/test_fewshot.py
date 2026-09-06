"""few-shot 示例库与检索测试。"""

import pytest

from data.generator import generate
from src.agent.fewshot import GOLD_EXAMPLES, format_examples, retrieve_examples, similarity
from src.db import engine


def test_similarity_basic():
    assert similarity("退款金额最高的类目", "退款金额最高的类目") == 1.0
    assert similarity("退款金额最高的类目", "用户注册城市分布") < 0.2
    assert similarity("", "任意") == 0.0


def test_retrieve_refund_question():
    """退款类问题应召回退款示例（归因报告 B 簇的验证）。"""
    examples = retrieve_examples("2025-02 月发生了多少笔退款？")
    assert examples
    assert all("refunded_at" in ex["sql"] for ex in examples if "退款" in ex["question"])


def test_retrieve_category_question():
    """类目问题应召回带 L2→L1 穿越写法的示例（归因报告 A 簇的验证）。"""
    examples = retrieve_examples("每个一级类目下各有多少个商品？")
    assert examples
    joined = "\n".join(ex["sql"] for ex in examples)
    assert "parent_id" in joined


def test_retrieve_topk_and_threshold():
    assert len(retrieve_examples("随便说点什么", k=2)) == 0  # 无关问题低于阈值
    assert len(retrieve_examples("上月各类目销售额", k=2)) <= 2


def test_all_gold_examples_are_selects():
    for ex in GOLD_EXAMPLES:
        assert ex["sql"].strip().upper().startswith(("SELECT", "WITH"))
        assert "```" not in ex["sql"]


def test_format_examples_contains_header_and_sql():
    text = format_examples(GOLD_EXAMPLES[:2])
    assert "参考示例" in text and "### 示例1" in text and "### 示例2" in text
    assert "SELECT" in text


@pytest.fixture(scope="module")
def conn(tmp_path_factory):
    path = tmp_path_factory.mktemp("fs") / "tiny.db"
    generate(path, scale=0.005, seed=42)
    return engine.connect(path)


def test_gold_examples_execute_on_db(tmp_path_factory):
    """黄金示例本身必须是可执行的正确 SQL。"""
    path = tmp_path_factory.mktemp("fs") / "tiny.db"
    generate(path, scale=0.005, seed=42)
    conn = engine.connect(path)
    for ex in GOLD_EXAMPLES:
        conn.execute(ex["sql"]).fetchall()
    conn.close()


def test_graph_injects_fewshot_by_default(conn):
    from src.agent.graph import build_graph, run
    from tests.test_graph import FakeLLM

    fake = FakeLLM()
    run(
        build_graph(client=fake, conn=conn, use_table_selection=False),
        "每个一级类目下各有多少个商品？",
    )
    assert "参考示例" in fake.calls[0]["system"]
    assert "parent_id" in fake.calls[0]["system"]


def test_graph_fewshot_disabled(conn):
    from src.agent.graph import build_graph, run
    from tests.test_graph import FakeLLM

    fake = FakeLLM()
    run(
        build_graph(client=fake, conn=conn, use_table_selection=False, use_fewshot=False),
        "每个一级类目下各有多少个商品？",
    )
    assert "参考示例" not in fake.calls[0]["system"]
