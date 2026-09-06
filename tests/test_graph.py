"""Agent 图端到端测试：注入假 LLM 客户端，不发网络请求。"""

import pytest

from data.generator import generate
from src.agent.graph import build_graph, run
from src.agent.nodes.generate_sql import extract_sql
from src.db import engine


class FakeLLM:
    """按 system 提示特征返回脚本化结果，并记录全部调用。"""

    def __init__(self, sql="SELECT COUNT(*) AS n FROM orders", answer="共 500 单。"):
        self.sql = sql
        self.answer = answer
        self.calls = []

    def chat(self, messages, system=None, **kwargs):
        self.calls.append({"messages": messages, "system": system})
        if "SQLite 专家" in system:
            return type("R", (), {"content": self.sql, "usage": {}})()
        if "数据分析助手" in system:
            return type("R", (), {"content": self.answer, "usage": {}})()
        # 理解节点（改写）
        return type("R", (), {"content": "改写后的问题", "usage": {}})()


@pytest.fixture(scope="module")
def conn(tmp_path_factory):
    path = tmp_path_factory.mktemp("g") / "tiny.db"
    generate(path, scale=0.005, seed=42)
    return engine.connect(path)


def test_happy_path(conn):
    fake = FakeLLM()
    g = build_graph(client=fake, conn=conn)
    state = run(g, "总共有多少订单")

    assert state["error"] == ""
    assert state["columns"] == ["n"]
    assert state["answer"] == "共 500 单。"
    # 无相对时间词 → 理解节点走快速路径，只调用 2 次 LLM（生成 + 回答）
    assert len(fake.calls) == 2
    assert state["expanded_question"] == "总共有多少订单"


def test_relative_time_triggers_rewrite(conn):
    fake = FakeLLM()
    g = build_graph(client=fake, conn=conn)
    state = run(g, "上个月的订单总额")

    assert state["expanded_question"] == "改写后的问题"
    assert len(fake.calls) == 3  # 改写 + 生成 + 回答


def test_sql_error_propagates_to_answer(conn):
    fake = FakeLLM(sql="SELECT * FROM no_such_table", answer="不应该被调用")
    g = build_graph(client=fake, conn=conn)
    state = run(g, "随便查点什么")

    assert "no_such_table" in state["error"]
    assert state["answer"].startswith("查询执行失败")


def test_extract_sql_handles_code_fence():
    assert extract_sql("```sql\nSELECT 1\n```") == "SELECT 1"
    assert extract_sql("SELECT 1;") == "SELECT 1"
    assert extract_sql("纯文本但没有SQL") == "纯文本但没有SQL"
