"""评测 runner 测试：用假 LLM 验证汇总指标计算，不发网络请求。"""

from src.eval.runner import QuestionResult, summarize


def _res(qid, correct, attempts, diff="easy", attribution=None, latency=1.0, tokens=100):
    return QuestionResult(
        qid=qid,
        difficulty=diff,
        question=f"q{qid}",
        correct=correct,
        attribution=attribution or ("correct" if correct else "wrong_result"),
        attempts=attempts,
        latency_s=latency,
        total_tokens=tokens,
    )


def test_summarize_metrics():
    results = [
        _res(1, True, 1),  # 首轮通过
        _res(2, True, 2),  # 挽回
        _res(3, False, 3, attribution="exec_error"),
        _res(4, True, 1, diff="hard"),
    ]
    s = summarize(results)
    assert s["total"] == 4
    assert s["exec_accuracy"] == 75.0
    assert s["first_round_pass"] == 50.0
    # 首轮未通过 2 题（挽回 1 + 失败 1）→ 挽回率 50%
    assert s["saved_by_correction"] == 50.0
    assert s["attribution"] == {"exec_error": 1}
    assert s["by_difficulty"]["easy"]["accuracy"] == round(2 / 3 * 100, 1)
    assert s["by_difficulty"]["hard"]["accuracy"] == 100.0


def test_summarize_empty():
    s = summarize([])
    assert s["total"] == 0 and s["exec_accuracy"] == 0.0


def test_latency_percentiles():
    results = [_res(i, True, 1, latency=float(i)) for i in range(1, 11)]
    s = summarize(results)
    assert s["p50_latency_s"] == 6.0  # 上中位数：sorted[5]（0 起始下标）
    assert s["p95_latency_s"] == 10.0
