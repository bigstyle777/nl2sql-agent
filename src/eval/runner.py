"""评测批量回归 runner：跑评测集 → 逐题判定 → 汇总指标 → 输出报告。

指标定义（与 PLAN.md 对齐）：
  - exec_accuracy      最终执行准确率（允许自纠错轮次内的挽回）
  - first_round_pass   首轮通过率（第 1 轮即正确，未经回炉）
  - saved_by_correction 自纠错挽回率（首轮失败但最终正确的比例）
  - latency / tokens   端到端耗时与 Token 消耗
归因（失败原因分类）：exec_error（SQL 执行报错）/ wrong_result（执行成功但结果不符）
"""

from __future__ import annotations

import json
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from src.db import engine
from src.eval.metrics import compare_results


@dataclass
class UsageRecorder:
    """包一层 LLM 客户端，按题累计 Token 用量与调用次数。"""

    inner: object
    total_tokens: int = 0
    calls: int = 0

    def chat(self, messages, system=None, **kwargs):
        result = self.inner.chat(messages, system=system, **kwargs)
        self.total_tokens += result.usage.get("total_tokens", 0)
        self.calls += 1
        return result


@dataclass
class QuestionResult:
    qid: int
    difficulty: str
    question: str
    correct: bool
    attribution: str  # correct / exec_error / wrong_result
    attempts: int = 0
    first_round_pass: bool = False
    reason: str = ""
    latency_s: float = 0.0
    total_tokens: int = 0
    llm_calls: int = 0
    pred_sql: str = ""
    gold_sql: str = ""
    tags: list[str] = field(default_factory=list)


def load_dataset(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def evaluate_question(
    item: dict,
    base_client,
    db_path,
    max_attempts: int = 3,
    use_hints: bool = True,
    use_fewshot: bool = True,
    use_table_selection: bool = True,
) -> QuestionResult:
    """在独立连接上评测单题（sqlite 连接不可跨线程共享，按题新建）。"""
    from src.agent.graph import build_graph, run

    recorder = UsageRecorder(inner=base_client)
    conn = engine.connect(db_path)
    try:
        graph = build_graph(
            client=recorder,
            conn=conn,
            max_attempts=max_attempts,
            use_hints=use_hints,
            use_fewshot=use_fewshot,
            use_table_selection=use_table_selection,
        )
        t0 = time.monotonic()
        state = run(graph, item["question"])
        latency = time.monotonic() - t0
    finally:
        conn.close()

    res = QuestionResult(
        qid=item["id"],
        difficulty=item["difficulty"],
        question=item["question"],
        correct=False,
        attribution="exec_error",
        attempts=state.get("attempts", 0),
        latency_s=round(latency, 2),
        total_tokens=recorder.total_tokens,
        llm_calls=recorder.calls,
        pred_sql=state.get("sql", ""),
        gold_sql=item["gold_sql"],
        tags=item.get("tags", []),
    )

    if state.get("error"):
        res.reason = state["error"][:200]
        return res

    gold_conn = engine.connect(db_path)
    try:
        gold = gold_conn.execute(item["gold_sql"]).fetchall()
        gold_cols = [d[0] for d in gold_conn.execute(item["gold_sql"]).description]
    finally:
        gold_conn.close()

    ok, reason = compare_results(
        gold_columns=gold_cols,
        gold_rows=gold,
        pred_columns=state.get("columns", []),
        pred_rows=state.get("rows", []),
        gold_sql=item["gold_sql"],
    )
    res.correct = ok
    res.attribution = "correct" if ok else "wrong_result"
    res.reason = reason[:200]
    return res


def _percent(n: float, d: float) -> float:
    return round(n / d * 100, 1) if d else 0.0


def summarize(results: list[QuestionResult]) -> dict:
    total = len(results)
    correct = [r for r in results if r.correct]
    first_pass = [r for r in correct if r.attempts <= 1]
    saved = [r for r in correct if r.attempts > 1]
    failed = [r for r in results if not r.correct]
    latencies = sorted(r.latency_s for r in results)
    tokens = [r.total_tokens for r in results]

    def pct(p: float) -> float:
        idx = min(int(len(latencies) * p), len(latencies) - 1)
        return latencies[idx] if latencies else 0.0

    by_difficulty = {}
    for diff in ("easy", "medium", "hard"):
        sub = [r for r in results if r.difficulty == diff]
        by_difficulty[diff] = {
            "total": len(sub),
            "accuracy": _percent(sum(r.correct for r in sub), len(sub)),
        }

    attribution = {}
    for r in failed:
        attribution[r.attribution] = attribution.get(r.attribution, 0) + 1

    first_round_fail = total - len(first_pass)  # 首轮未通过 = 挽回 + 最终失败
    saved_base = first_round_fail
    return {
        "total": total,
        "correct": len(correct),
        "exec_accuracy": _percent(len(correct), total),
        "first_round_pass": _percent(len(first_pass), total),
        "saved_by_correction": _percent(len(saved), saved_base),
        "saved_count": len(saved),
        "first_round_fail_count": first_round_fail,
        "avg_latency_s": round(sum(latencies) / total, 1) if total else 0,
        "p50_latency_s": pct(0.5),
        "p95_latency_s": pct(0.95),
        "avg_total_tokens": round(sum(tokens) / total) if total else 0,
        "avg_llm_calls": round(sum(r.llm_calls for r in results) / total, 2) if total else 0,
        "by_difficulty": by_difficulty,
        "attribution": attribution,
    }


def run_dataset(
    dataset_path: Path,
    db_path,
    base_client,
    workers: int = 6,
    max_attempts: int = 3,
    limit: int | None = None,
    qids: list[int] | None = None,
    progress_cb=None,
    use_hints: bool = True,
    use_fewshot: bool = True,
    use_table_selection: bool = True,
) -> tuple[list[QuestionResult], dict]:
    items = load_dataset(dataset_path)
    if qids:
        items = [i for i in items if i["id"] in qids]
    if limit:
        items = items[:limit]

    results: list[QuestionResult] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(
                evaluate_question,
                it,
                base_client,
                db_path,
                max_attempts,
                use_hints,
                use_fewshot,
                use_table_selection,
            )
            for it in items
        ]
        for i, fut in enumerate(futures, 1):
            results.append(fut.result())
            if progress_cb:
                progress_cb(i, len(items))
    results.sort(key=lambda r: r.qid)
    return results, summarize(results)


def git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return "unknown"
