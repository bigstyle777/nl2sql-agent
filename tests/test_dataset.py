"""评测集质量测试：题目数量、结构、gold SQL 全部可在库上执行。"""

from pathlib import Path

import pytest

from data.generator import generate
from src.db import engine
from src.eval.runner import load_dataset

DATASET = Path(__file__).resolve().parent.parent / "evals" / "dataset" / "v1.jsonl"


@pytest.fixture(scope="module")
def dataset():
    return load_dataset(DATASET)


def test_dataset_shape(dataset):
    assert len(dataset) == 120
    assert {e["difficulty"] for e in dataset} == {"easy", "medium", "hard"}
    counts = {"easy": 0, "medium": 0, "hard": 0}
    for e in dataset:
        counts[e["difficulty"]] += 1
        assert set(e) == {"id", "question", "gold_sql", "difficulty", "tags"}
        assert e["question"].strip() and e["gold_sql"].upper().startswith(("SELECT", "WITH"))
    assert counts == {"easy": 60, "medium": 40, "hard": 20}
    assert len({e["question"] for e in dataset}) == 120


def test_gold_sql_executes_on_tiny_db(dataset, tmp_path_factory):
    """gold SQL 与业务库 schema 绑定：在小规模库上逐题执行验证。"""
    path = tmp_path_factory.mktemp("d") / "tiny.db"
    generate(path, scale=0.005, seed=42)
    conn = engine.connect(path)
    for e in dataset:
        cursor = conn.execute(e["gold_sql"])
        cursor.fetchall()
        assert cursor.description is not None, f"id={e['id']} gold 不是查询语句"
    conn.close()


def test_multi_statement_gold_rejected(dataset):
    from src.db.engine import validate_sql

    for e in dataset:
        validate_sql(e["gold_sql"])  # 不应抛异常（单条语句约束）
