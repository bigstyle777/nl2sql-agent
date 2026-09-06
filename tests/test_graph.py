"""Agent 图端到端测试：注入假 LLM 客户端，不发网络请求。"""

import pytest

from data.generator import generate
from src.agent.graph import build_graph, run
from src.agent.nodes.check import sanity_issues
from src.agent.nodes.generate_sql import extract_sql
from src.db import engine


class FakeLLM:
    """按 system 提示特征返回脚本化结果，并记录全部调用。

    fixed_sql 非空时，凡是收到"带反馈的重写请求"（消息含"上一版"）就返回修正 SQL，
    用于模拟自纠错成功路径。
    """

    def __init__(
        self, sql="SELECT COUNT(*) AS n FROM orders", answer="共 500 单。", fixed_sql=None
    ):
        self.sql = sql
        self.answer = answer
        self.fixed_sql = fixed_sql
        self.calls = []

    @staticmethod
    def _resp(content):
        return type("R", (), {"content": content, "usage": {}})()

    def chat(self, messages, system=None, **kwargs):
        self.calls.append({"messages": str(messages), "system": system})
        if "SQLite 专家" in system:
            if self.fixed_sql and "上一版" in str(messages):
                return self._resp(self.fixed_sql)
            return self._resp(self.sql)
        if "数据分析助手" in system:
            return self._resp(self.answer)
        if "表清单" in system:  # 选表节点
            return self._resp("orders, users")
        return self._resp("改写后的问题")  # 理解节点


@pytest.fixture(scope="module")
def conn(tmp_path_factory):
    path = tmp_path_factory.mktemp("g") / "tiny.db"
    generate(path, scale=0.005, seed=42)
    return engine.connect(path)


def test_happy_path_single_round(conn):
    fake = FakeLLM()
    state = run(build_graph(client=fake, conn=conn, use_table_selection=False), "总共有多少订单")

    assert state["error"] == ""
    assert state["columns"] == ["n"]
    assert state["attempts"] == 1
    assert state["feedback"] == ""
    assert state["answer"] == "共 500 单。"
    # 无相对时间词 → 理解节点走快速路径，只调用 2 次 LLM（生成 + 回答）
    assert len(fake.calls) == 2
    assert state["expanded_question"] == "总共有多少订单"


def test_relative_time_triggers_rewrite(conn):
    fake = FakeLLM()
    state = run(build_graph(client=fake, conn=conn, use_table_selection=False), "上个月的订单总额")

    assert state["expanded_question"] == "改写后的问题"
    assert len(fake.calls) == 3  # 改写 + 生成 + 回答


def test_error_triggers_correction_loop(conn):
    """第一版 SQL 报错 → 带反馈回炉 → 修正后成功。"""
    fake = FakeLLM(
        sql="SELECT * FROM no_such_table",
        fixed_sql="SELECT COUNT(*) AS n FROM orders",
    )
    state = run(build_graph(client=fake, conn=conn, use_table_selection=False), "总共有多少订单")

    assert state["attempts"] == 2
    assert state["error"] == ""
    assert state["answer"] == "共 500 单。"
    # 第二次生成请求必须携带上一版 SQL 与报错反馈（calls: 生成/重生成/回答）
    assert "上一版" in fake.calls[1]["messages"]
    assert "no_such_table" in fake.calls[1]["messages"]


def test_attempts_exhausted_no_infinite_loop(conn):
    """始终报错时必须在 MAX_ATTEMPTS 轮后终止，并把失败原因交给回答节点。"""
    fake = FakeLLM(sql="SELECT * FROM no_such_table")
    state = run(
        build_graph(client=fake, conn=conn, max_attempts=3, use_table_selection=False),
        "总共有多少订单",
    )

    assert state["attempts"] == 3
    assert "no_such_table" in state["error"]
    assert state["answer"].startswith("查询执行失败")
    assert len(fake.calls) == 3  # 3 轮生成；回答节点对报错短路，不再调 LLM


def test_sanity_case_inconsistency_triggers_correction(conn):
    """复现真实踩坑：状态大小写未归一被自检发现并回炉修正。"""
    fake = FakeLLM(
        sql="SELECT status, COUNT(*) AS n, SUM(total_amount) AS amt FROM orders GROUP BY status",
        fixed_sql=(
            "SELECT LOWER(status) AS status, COUNT(*) AS n, SUM(total_amount) AS amt "
            "FROM orders GROUP BY LOWER(status)"
        ),
    )
    state = run(
        build_graph(client=fake, conn=conn, use_table_selection=False), "各订单状态的订单数量"
    )

    assert state["attempts"] == 2
    assert "LOWER" in fake.calls[2]["messages"]  # 反馈要求归一
    assert state["feedback"] == ""  # 修正后自检通过


def test_empty_result_retries_until_exhausted(conn):
    """空结果反馈后仍为空 → 达到轮次上限后进入回答，反馈保留供说明。"""
    fake = FakeLLM(
        sql="SELECT id FROM orders WHERE 1 = 0", fixed_sql="SELECT id FROM orders WHERE 1 = 0"
    )
    state = run(
        build_graph(client=fake, conn=conn, max_attempts=2, use_table_selection=False),
        "查点不存在的东西",
    )

    assert state["attempts"] == 2
    assert state["feedback"] != ""
    assert state["answer"] != ""


def test_sanity_issues_rules():
    assert sanity_issues(["a"], [])  # 空结果
    assert sanity_issues(["a", "b"], [(None, 1)])  # 全 NULL 列
    issues = sanity_issues(["status"], [("paid",), ("PAID",), ("Paid",)])
    assert len(issues) == 1 and "LOWER" in issues[0]
    assert sanity_issues(["x"], [(1,), (2,)]) == []  # 正常数值列不误报


def test_extract_sql_handles_code_fence():
    assert extract_sql("```sql\nSELECT 1\n```") == "SELECT 1"
    assert extract_sql("SELECT 1;") == "SELECT 1"
    assert extract_sql("纯文本但没有SQL") == "纯文本但没有SQL"


def test_select_tables_node(conn):
    """选表节点应把 DDL 裁剪到选中的表。"""

    from src.agent.nodes.select_tables import make_select_tables_node
    from src.db.engine import get_ddl_by_table

    ddl_by_table = get_ddl_by_table(conn)
    fake = FakeLLM()
    # FakeLLM 对非生成/回答/理解的调用（即选表）返回表名列表
    node = make_select_tables_node(fake, ddl_by_table)
    full_ddl = "\n\n".join(ddl_by_table.values())

    state = node({"expanded_question": "各订单状态的订单数", "ddl": full_ddl})
    assert set(state["selected_tables"]) == {"orders", "users"}
    assert "CREATE TABLE orders" in state["ddl_subset"]
    assert "CREATE TABLE reviews" not in state["ddl_subset"]


def test_select_tables_fallback_on_invalid_or_all():
    from src.agent.nodes.select_tables import make_select_tables_node

    ddl_by_table = {
        "orders": "CREATE TABLE orders (id INTEGER)",
        "users": "CREATE TABLE users (id INTEGER)",
    }

    class Pick:
        def __init__(self, content):
            self.content = content

        def chat(self, messages, system=None, **kw):
            return type("R", (), {"content": self.content, "usage": {}})()

    node = make_select_tables_node(Pick("nonexistent_table"), ddl_by_table)
    state = node({"expanded_question": "q"})
    assert state["selected_tables"] == []  # 无效表名 → 全量兜底

    node2 = make_select_tables_node(Pick("orders, users"), ddl_by_table)
    state2 = node2({"expanded_question": "q"})
    assert state2["selected_tables"] == []  # 全选 = 无裁剪收益，回退全量
    assert "CREATE TABLE orders" in state2["ddl_subset"]


def test_hints_included_in_generate_prompt(conn):
    """语义增强开启时，生成 prompt 应包含枚举值与日期惯用写法提示。"""
    fake = FakeLLM()
    run(build_graph(client=fake, conn=conn, use_table_selection=False), "总共有多少订单")
    assert "on_sale" in fake.calls[0]["system"]
    assert "replace(substr" in fake.calls[0]["system"]


def test_hints_disabled(conn):
    fake = FakeLLM()
    run(
        build_graph(client=fake, conn=conn, use_table_selection=False, use_hints=False),
        "总共有多少订单",
    )
    assert "on_sale" not in fake.calls[0]["system"]
